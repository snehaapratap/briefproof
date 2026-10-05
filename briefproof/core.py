"""Read public search results and public Discourse topics, without contacting anyone."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


COMMUNITIES = {"community.make.com", "community.n8n.io"}
NETWORK_HOSTS = COMMUNITIES | {"serpapi.com"}
MAX_BYTES = 5_000_000
FORUM_ACCESS_NOTICE = (
    "Automated Make/n8n forum fetching is disabled because their published terms "
    "restrict automated access. Search results remain unverified; review them manually."
)


class FetchError(RuntimeError):
    """A readable error that never includes a credential-bearing request URL."""


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlparse(req.full_url), urlparse(newurl)
        if new.scheme != "https" or new.hostname != old.hostname:
            raise FetchError("A request tried to redirect outside its original HTTPS host.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicClient:
    def __init__(self, timeout: float = 20):
        self.timeout = timeout
        self.opener = build_opener(SafeRedirect())

    def get_json(self, url: str) -> dict:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname not in NETWORK_HOSTS
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise FetchError("Only the supported public HTTPS services may be queried.")
        if parsed.hostname in COMMUNITIES:
            raise FetchError(FORUM_ACCESS_NOTICE)
        request = Request(url, headers={"User-Agent": "BriefProof/0.1 (+read-only public topic audit)",
                                        "Accept": "application/json"})
        for attempt in range(2):
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise FetchError("The public response exceeded the size limit.")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise FetchError("The service returned an unexpected JSON shape.")
                return result
            except HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(1)
                    continue
                raise FetchError(f"The service returned HTTP {exc.code}; no request URL was logged.") from None
            except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError):
                raise FetchError("The public request failed or did not return valid JSON.") from None
        raise FetchError("The service did not complete the request.")


class PlainText(HTMLParser):
    """Exclude quotations and code so another author's words cannot close a job."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"blockquote", "script", "style", "pre", "code"}:
            self.ignored.append(tag)
        if tag in {"p", "br", "li", "div", "h1", "h2", "h3"} and not self.ignored:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.ignored and tag == self.ignored[-1]:
            self.ignored.pop()
        if tag in {"p", "li", "div"} and not self.ignored:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def plain_text(html: str) -> str:
    parser = PlainText()
    parser.feed(html)
    return re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()


def topic_url(url: str) -> tuple[str, int]:
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname not in COMMUNITIES or p.username
            or p.password or p.port not in (None, 443)):
        raise ValueError("Use a public Make Community or n8n Community topic URL.")
    m = re.fullmatch(r"/t/(?:[^/]+/)?(\d+)(?:/\d+)?(?:\.json)?/?", p.path)
    if not m:
        raise ValueError("The URL is not a supported public topic.")
    return f"https://{p.hostname}", int(m.group(1))


def iso_date(value: str) -> datetime | None:
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    except (ValueError, TypeError, AttributeError):
        return None


def excerpt(text: str, match: re.Match) -> str:
    # A short, attributable fragment, rather than republishing an entire post.
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    start = max(line_start, match.start() - 60)
    if start > line_start:
        space = text.find(" ", start, match.start())
        start = space + 1 if space >= 0 else match.start()
    sentence = text[start:line_end if line_end >= 0 else len(text)]
    return ("… " if start > line_start else "") + " ".join(sentence.split()[:22])


CLOSED = re.compile(
    r"\b(?:position|role|req|requirement|job|project|(?:paid )?test|vacancy|contract)\s+(?:is\s+|has been\s+)?filled\b|"
    r"\bapplications (?:are |have been )?(?:now )?closed\b|"
    r"\b(?:we|i)\s+(?:have\s+)?(?:already\s+)?(?:found|hired)\s+(?:someone|a\s+(?:developer|freelancer))\b|"
    r"\b(?:no longer (?:hiring|looking|need)|closing this (?:request|thread|post)|"
    r"this (?:issue|problem|project|request) (?:is |has been )?(?:solved|resolved|closed))\b",
    re.I,
)
REOPENED = re.compile(r"\b(?:reopened|re-opening|still looking for help|still hiring|position is open again)\b", re.I)
UNFUNDED = re.compile(r"\b(?:no paid work (?:is |has been )?authori[sz]ed|not yet funded|"
                      r"no (?:current |existing )?clients|unpaid|volunteer(?:s|ing)?)\b", re.I)
PAYMENT = re.compile(r"\b(?:happy to pay|willing to pay|paid (?:work|test|project|trial|task|help)|"
                     r"(?:our|my|the) budget|fixed[- ]price|hourly rate|payment (?:will|is)|"
                     r"\$\s*\d|USD\s*\$?\s*\d|INR\s*\d|₹\s*\d)", re.I)
BUYER = re.compile(r"\b(?:i(?:'m| am|’m) (?:looking|stuck)|(?:we|i) (?:are |am )?looking for|"
                   r"we need|i need|we(?:'re| are|’re) hiring|we(?:'re| are|’re) looking|"
                   r"happy to pay|willing to pay|looking for (?:a|an)\b|seeking (?:a|an|help|estimates)|hiring)\b", re.I)
SELLER = re.compile(r"\b(?:i can help (?:you|with)|i offer|we offer|our services|"
                    r"available for (?:hire|projects)|hire me|i(?:'m| am|’m) available for)\b", re.I)
BUDGET = re.compile(r"(?:USD\s*\$?\s*\d[\d,.]*|US\$\s*\d[\d,.]*|"
                    r"\$\s*\d[\d,.]*|INR\s*\d[\d,.]*|₹\s*\d[\d,.]*|"
                    r"\d[\d,.]*\s*(?:USD|INR))"
                    r"(?:\s*(?:–|-|to)\s*(?:\$|₹)?\s*\d[\d,.]*)?"
                    r"(?:\s*(?:per|/)\s*(?:hour|hr|project|milestone|day))?", re.I)


@dataclass
class Evidence:
    kind: str
    text: str
    author: str
    posted_at: str
    post_url: str


@dataclass
class Lead:
    title: str
    source_url: str
    requester: str = ""
    status: str = "unverified"
    reason: str = "No primary discussion has been inspected."
    advertised_budget: list[str] = field(default_factory=list)
    requester_last_post: str = ""
    latest_forum_activity: str = ""
    requester_age_days: int | None = None
    posts_read: int = 0
    total_posts: int = 0
    complete_thread: bool = False
    evidence: list[Evidence] = field(default_factory=list)
    checks_needed: list[str] = field(default_factory=lambda: [
        "Confirm the buyer is still hiring.", "Agree scope, acceptance and payment before work.",
        "Confirm AI-assisted delivery is acceptable."])
    verified_at: str = ""
    discovery_query: str = ""

    def to_dict(self):
        return asdict(self)


def assess(topic: dict, posts: list[dict], source: str, *, complete: bool,
           now: datetime | None = None, max_age: int = 30) -> Lead:
    now = now or datetime.now(timezone.utc)
    source = source.rstrip("/")
    posts = sorted({p["id"]: p for p in posts if p.get("id") is not None}.values(),
                   key=lambda p: p.get("post_number", 0))
    op = next((p for p in posts if p.get("post_number") == 1), None)
    lead = Lead(title=topic.get("title", "Untitled topic"), source_url=source,
                posts_read=len(posts), total_posts=len(topic.get("post_stream", {}).get("stream", [])),
                complete_thread=complete, verified_at=now.isoformat())
    if not op:
        lead.reason = "The original request could not be read."
        return lead
    author = op.get("username", "")
    if not author:
        lead.reason = "The original request's author could not be identified."
        return lead
    lead.requester = author
    own_posts = [p for p in posts if p.get("username", "").casefold() == author.casefold()]
    original = plain_text(op.get("cooked", ""))
    buying = bool(BUYER.search(original))
    selling = bool(SELLER.search(original)) and not buying
    last_event = None
    paid = False
    for p in own_posts:
        text = plain_text(p.get("cooked", ""))
        timestamp = p.get("created_at", "")
        lead.requester_last_post = timestamp
        for kind, pattern in [("payment", PAYMENT), ("closed", CLOSED),
                              ("not_authorized", UNFUNDED), ("reopened", REOPENED)]:
            match = pattern.search(text)
            if match:
                lead.evidence.append(Evidence(kind, excerpt(text, match), author, timestamp,
                                              f"{source}/{p['post_number']}"))
                if kind == "payment":
                    paid = True
                elif kind in {"closed", "not_authorized"}:
                    last_event = kind
                elif kind == "reopened":
                    last_event = None
        amounts = list(BUDGET.finditer(text))
        lead.advertised_budget += [m.group(0) for m in amounts]
        if amounts:
            lead.evidence.append(Evidence("requester_amount", excerpt(text, amounts[0]), author,
                                          timestamp, f"{source}/{p['post_number']}"))
    lead.advertised_budget = list(dict.fromkeys(lead.advertised_budget))
    latest_dates = [p.get("created_at", "") for p in posts if iso_date(p.get("created_at", ""))]
    lead.latest_forum_activity = max(latest_dates, key=iso_date) if latest_dates else ""
    buyer_date = iso_date(lead.requester_last_post)
    if buyer_date:
        lead.requester_age_days = max(0, (now - buyer_date).days)
    if topic.get("closed") or topic.get("archived") or last_event == "closed":
        lead.status, lead.reason = "closed", "The topic is closed/archived or its requester says it is filled or resolved."
    elif selling:
        lead.status, lead.reason = "seller_offer", "The original author is advertising services, not commissioning work."
    elif last_event == "not_authorized":
        lead.status, lead.reason = "not_authorized", "Requester evidence indicates unpaid, unfunded or not-yet-authorized work."
    elif not complete:
        lead.status, lead.reason = "incomplete", "Some replies were not read; a later closure may be missing."
    elif buying and paid:
        lead.status, lead.reason = "candidate", "Requester expresses buying intent and payment; current hiring and payment remain unconfirmed."
    else:
        lead.reason = "No clear combination of buying intent and payment was found in requester-authored text."
    if lead.requester_age_days is not None and lead.requester_age_days > max_age and lead.status == "candidate":
        lead.status, lead.reason = "stale", "The requester's last post exceeds the chosen age limit; seller replies do not refresh it."
    if lead.advertised_budget:
        lead.checks_needed.append("Amounts are advertised requester amounts, not an accepted offer or verified payment.")
    return lead


def verify(url: str, client: PublicClient, *, max_posts: int = 300, max_age: int = 30) -> Lead:
    base, ident = topic_url(url)
    source = f"{base}/t/{ident}"
    topic = client.get_json(source + ".json")
    stream = topic.get("post_stream", {})
    ids, posts = stream.get("stream", []), stream.get("posts", [])
    have = {p.get("id") for p in posts}
    wanted = [i for i in ids[:max_posts] if i not in have]
    for offset in range(0, len(wanted), 50):
        query = urlencode([("post_ids[]", i) for i in wanted[offset:offset + 50]])
        result = client.get_json(f"{base}/t/{ident}/posts.json?{query}")
        posts += result.get("post_stream", {}).get("posts", [])
    complete = bool(ids) and set(ids).issubset({p.get("id") for p in posts})
    return assess(topic, posts, source, complete=complete, max_age=max_age)


def discover(query: str, api_key: str, client: PublicClient, *, limit: int = 6) -> tuple[list[dict], str]:
    if not api_key.strip():
        raise ValueError("A SerpApi key is required for live discovery; demo mode makes no API calls.")
    restricted_query = f"{query} (site:community.make.com/t/ OR site:community.n8n.io/t/)"
    params = {"engine": "google", "q": restricted_query, "api_key": api_key,
              "gl": "in", "hl": "en", "num": min(max(limit, 1), 10)}
    response = client.get_json("https://serpapi.com/search.json?" + urlencode(params))
    if response.get("error"):
        # Do not echo provider errors: some include the original request parameters.
        raise FetchError("SerpApi reported an error. Check account verification, key and remaining credits.")
    candidates, seen = [], set()
    for result in response.get("organic_results", []):
        try:
            base, ident = topic_url(result.get("link", ""))
        except ValueError:
            continue
        canonical = f"{base}/t/{ident}"
        if canonical not in seen:
            candidates.append({"title": result.get("title", "Untitled result"), "url": canonical})
            seen.add(canonical)
        if len(candidates) >= limit:
            break
    return candidates, response.get("search_metadata", {}).get("id", "")
