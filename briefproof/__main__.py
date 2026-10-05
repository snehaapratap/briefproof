from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import getpass
import json
import os
from pathlib import Path
import sys

from .core import FORUM_ACCESS_NOTICE, FetchError, Lead, PublicClient, assess, discover, verify


def demo_leads():
    """Intentionally fictional records, never presented as real payable work."""
    examples = [
        ("Demo: small paid API repair", "<p>I am stuck and happy to pay for a small API repair. My budget is USD25.</p>",
         [("DemoSeller", "<p>I can help, my quote is USD500.</p>")]),
        ("Demo: paid test already filled", "<p>We are looking for a developer for a paid test. Our budget is INR10000.</p>",
         [("DemoBuyer", "<p>The position is filled. Please do not contact us.</p>"),
          ("DemoSeller", "<p>I am available for projects.</p>")]),
        ("Demo: not yet authorized", "<p>We are looking for estimates on an API project. No paid work authorised yet.</p>", []),
        ("Demo: service advertisement", "<p>I offer automation services. Hire me. My hourly rate is USD25.</p>", []),
    ]
    result = []
    now = datetime.now(timezone.utc)
    for number, (title, body, replies) in enumerate(examples, 1):
        posts = [{"id": 1, "post_number": 1, "username": "DemoBuyer", "cooked": body,
                  "created_at": now.isoformat()}]
        for i, (author, text) in enumerate(replies, 2):
            posts.append({"id": i, "post_number": i, "username": author, "cooked": text,
                          "created_at": now.isoformat()})
        topic = {"title": title, "closed": False, "post_stream": {"stream": [p["id"] for p in posts]}}
        result.append(assess(topic, posts, f"https://example.invalid/demo/{number}", complete=True))
    return result


def display(leads):
    labels = {"candidate": "CANDIDATE — confirm hiring", "closed": "EXCLUDE — filled/closed",
              "not_authorized": "EXCLUDE — not funded/authorized", "seller_offer": "EXCLUDE — seller offer",
              "stale": "RECHECK — requester inactive", "incomplete": "RECHECK — incomplete thread",
              "unverified": "RECHECK — payment unclear"}
    for i, lead in enumerate(leads, 1):
        print(f"\n{i}. {lead.title}\n   {labels[lead.status]}")
        print(f"   {lead.source_url}\n   {lead.reason}")
        if lead.advertised_budget:
            print("   Requester amount: " + ", ".join(lead.advertised_budget))
        if lead.requester:
            print(f"   Requester: {lead.requester}; last post {lead.requester_last_post}")
        print(f"   Discussion coverage: {lead.posts_read}/{lead.total_posts} posts")
        key_evidence = [e for e in lead.evidence if e.kind in {"closed", "not_authorized", "requester_amount"}]
        selected = key_evidence[-3:] if key_evidence else lead.evidence[-2:]
        for e in selected:
            print(f"   Evidence [{e.kind}] {e.post_url}\n     {e.text}")
    print("\nNo messages sent, jobs accepted, or payments collected. A candidate is a lead, not a job.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="BriefProof — search for paid work, then check requester evidence.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run clearly marked fictional examples without a key or network.")
    check = sub.add_parser("verify", help="Unavailable: automated forum fetching is disabled.")
    check.add_argument("url")
    search = sub.add_parser("search", help="Discover unverified topic links with SerpApi Google Search.")
    search.add_argument("query", help='For example: "paid Make workflow repair"')
    search.add_argument("--limit", type=int, default=6, choices=range(1, 11), metavar="1..10")
    search.add_argument("--ask-key", action="store_true", help="Enter a key privately, without putting it in shell history.")
    for cmd in (check, search):
        cmd.add_argument("--max-posts", type=int, default=300, choices=range(20, 1001), metavar="20..1000")
        cmd.add_argument("--max-age", type=int, default=30, choices=range(1, 366), metavar="1..365")
    for cmd in (check, search, sub.choices["demo"]):
        cmd.add_argument("--output", type=Path, help="Write an evidence JSON file; never includes an API key.")
    args = parser.parse_args(argv)
    client = PublicClient()
    search_id = ""
    try:
        if args.command == "demo":
            print("BRIEFPROOF / FICTIONAL OFFLINE DEMO — these are not real clients or earnings.")
            leads = demo_leads()
        elif args.command == "verify":
            leads = [verify(args.url, client, max_posts=args.max_posts, max_age=args.max_age)]
        else:
            key = getpass.getpass("SerpApi key (hidden): ") if args.ask_key else os.environ.get("SERPAPI_API_KEY", "")
            if not key:
                parser.error("Set SERPAPI_API_KEY privately, or add --ask-key. Use demo to try without a key.")
            results, search_id = discover(args.query, key, client, limit=args.limit)
            key = ""  # Do not retain or write credentials after discovery.
            print(f"BRIEFPROOF / LIVE SERPAPI SEARCH — {len(results)} unverified links; forum fetching disabled")
            def inspect(result):
                lead = Lead(result["title"], result["url"], reason=FORUM_ACCESS_NOTICE)
                lead.discovery_query = args.query
                return lead
            with ThreadPoolExecutor(max_workers=3) as pool:
                leads = list(pool.map(inspect, results))
            leads.sort(key=lambda lead: (lead.status != "candidate", lead.requester_age_days or 0))
        display(leads)
        if args.output:
            report = {"project": "BriefProof", "mode": args.command,
                      "fictional": args.command == "demo", "created_at": datetime.now(timezone.utc).isoformat(),
                      "serpapi_search_id": search_id, "leads": [lead.to_dict() for lead in leads]}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Evidence written to {args.output}")
        return 0
    except (FetchError, ValueError, KeyError, TypeError) as exc:
        # Suppress tracebacks and credential-bearing URLs for normal data/network failures.
        print(f"BriefProof could not finish: {exc if isinstance(exc, (FetchError, ValueError)) else 'Unexpected public response shape.'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
