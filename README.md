# BriefProof

Find a paid-work request. Check whether it is actually a buyer, whether the buyer
mentions payment, and whether a later reply says the position is filled.

BriefProof is a read-only Python tool for people looking for small Make/n8n
automation projects. SerpApi Google Search supplies the current discovery results.
The tool then reads the original public community discussions, including replies
outside the initial page, before suggesting which requests deserve a manual check.

The distinction matters: a freelancer's $500 quote is not the buyer's budget;
today's seller reply does not make an old buyer active; an RFQ can explicitly say
that no paid work is authorized. A search snippet alone cannot resolve these cases.

## Run locally

Python 3.11 or later. The program has no runtime dependencies or model subscription.
From this directory, no installation is needed:

```sh
python3 -m briefproof demo
python3 -m unittest discover -s tests -v
```

The offline demo uses **fictional** requests, with no network calls and no real
earnings or client claims. It demonstrates a paid candidate, a filled position,
an unauthorized RFQ, and a seller advertisement.

For live discovery, use a verified SerpApi account and its API key:

```sh
python3 -m briefproof search "paid Make workflow repair" --ask-key --limit 6
```

`--ask-key` hides your key while typing and avoids putting it in shell history.
Alternatively set `SERPAPI_API_KEY` privately in your own environment. Do not put
a key in a screenshot, recording, repository, command argument, or report.

A single search command makes one SerpApi search, then reads up to ten public
topics. The free account advertises 250 searches monthly; account verification
and the provider's current limits apply. SerpApi is essential to discovery, rather
than a cosmetic call: its organic results determine which live discussions are
inspected. The offline demo is a separate mode and never claims to exercise SerpApi.

You can audit a known public topic without spending a SerpApi search:

```sh
python3 -m briefproof verify "https://community.make.com/t/your-topic/123"
```

Replace that illustrative URL with an actual topic. Only HTTPS topic URLs on
`community.make.com` and `community.n8n.io` are supported.

To keep an evidence record:

```sh
python3 -m briefproof search "paid n8n API integration" --ask-key --output reports/leads.json
```

Reports contain requester-authored evidence links, short excerpts, discussion
coverage and separate requester/forum activity dates. Reports do not include
the API key; the `reports/` directory is ignored by Git.

## What the decisions mean

- **Candidate:** requester expresses buying intent and payment, and the complete
  discussion was read. This is still a lead: hiring, fit, scope and payment are unconfirmed.
- **Closed:** the platform says closed/archived, or the requester says filled/resolved.
- **Not authorized:** requester says unpaid, unfunded, or no paid work authorized.
- **Seller offer:** the original author advertises services rather than commissioning them.
- **Stale:** the requester's last post is older than the chosen age limit (default 30 days).
- **Incomplete/unverified:** not enough primary evidence was read to recommend the request.

Only the original requester's posts supply budgets and closure signals. Quoted
text and code are excluded. Seller replies cannot supply a buyer budget or
refresh the buyer's activity. Reads are bounded (300 posts by default) and a
truncated discussion stays incomplete. No messages are sent and no job is accepted.

The classifier uses explicit text rules, not an LLM. It can miss phrasing, sarcasm,
negations, off-site hiring and private closures. It does not verify the buyer's
identity, funding, payment history or willingness to hire you. Review linked evidence
and agree scope, acceptance, AI use and payment before doing commissioned work.

## Architecture and checks

`core.py` holds the HTTPS client, SerpApi discovery, Discourse pagination, quote
removal and requester-only assessment. `__main__.py` adds the CLI, bounded parallel
topic inspection, offline demonstration and JSON export. The tests exercise late
closures, seller prices, stale buyers, incomplete replies, unfunded requests,
credential-safe errors and URL/redirect restrictions.

The read-only client accepts only its three known service hosts, rejects credentials
in source URLs and unexpected ports, blocks redirects to other hosts, bounds
response sizes and avoids logging credential-bearing URLs. It respects HTTP failures
instead of bypassing login or challenges. It never reads a browser session.

## SerpApi India Hackathon

Intended track: **Knowledge & Public Interest** (paid-work information literacy).
This project began on 5 October 2026 and was not a pre-existing project.

**AI disclosure:** OpenAI Codex generated and revised the Python implementation,
tests and documentation under the participant's instructions. Its use must be
disclosed in any hackathon entry. This is an AI-assisted project; no past client
deployment or human-only authorship is claimed.

Submission status: not submitted. A real SerpApi run and a public video showing
the program running locally are required before representing the entry as ready.
Winning and payment are not guaranteed.

Official references:

- [Google Search API](https://serpapi.com/search-api)
- [Event rules](https://serpapi.github.io/serpapi-india-hackathon-2026/rules.html)
- [Submission dashboard](https://serpapi.github.io/serpapi-india-hackathon-2026/submit.html)

MIT licensed.
