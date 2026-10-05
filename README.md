# BriefProof

An AI-assisted, MIT-licensed Python project for classifying paid-work evidence.
The offline examples show how to distinguish requester budgets, filled requests,
unfunded work and seller advertisements.

## Current status

Automated Make/n8n forum fetching is disabled because both forums' published
terms restrict automated access. SerpApi discovery returns **unverified links**;
it does not read the discussions or produce audited live candidates. The earlier
commercial automated-auditor offer is withdrawn.

Policy sources: [Make forum terms](https://community.make.com/tos) and
[n8n forum terms](https://community.n8n.io/tos), Acceptable Use item 5.

## Try the offline examples

Use Python 3.11 or later. The project uses the Python standard library and needs
no runtime package installation. From the repository directory:

```sh
python3 -m briefproof demo
```

The four fictional cases are:

- A requester advertises a small paid repair; a seller's larger quote does not
  replace the requester budget.
- A requester says a paid test is filled; a later seller reply does not reopen it.
- A requester asks for estimates but has not authorized paid work.
- The original author advertises a service rather than commissioning work.

These examples make no network calls. Their clients, budgets and evidence are
fictional. To export the same examples as JSON:

```sh
python3 -m briefproof demo --output reports/demo.json
```

The report identifies its mode and sets `fictional` to `true`. Its timestamps
record the demo run, not activity by real buyers.

## Local browser interface

```sh
python3 -m briefproof.web
```

Open `http://127.0.0.1:8765`. The fictional demo works without a key. The interface
can display the report and download it as JSON. The server binds to loopback and
requires same-origin requests with a token generated for each launch.

Optional search requires a SerpApi key in the Python process environment. Keep
it private; the interface does not ask you to enter it in the browser. Each
server session allows up to eight search attempts and requests up to four links
per search. These links remain unverified. The verification mode is unavailable.

## Optional SerpApi discovery

Use a verified SerpApi account with an available search allowance. Provider
limits and charges apply; no API credits are included with this project. The
CLI can prompt for the key without placing it in the command or shell history:

```sh
python3 -m briefproof search "paid automation repair" --ask-key --limit 4 --output reports/search.json
```

Alternatively, provide `SERPAPI_API_KEY` privately in the process environment.
Never put a key in a repository, screenshot, recording, command argument or
report.

Discovery searches for Make/n8n topic links through SerpApi. It returns titles,
URLs and a search identifier where available, without fetching either forum.
CLI results are limited to 1–10 links, with six by default. Search records have
`unverified` status and no requester or discussion evidence. An organic-result
title or advertised amount does not establish a current buyer, agreed budget,
funded order or payment.

The `verify` command is retained for compatibility but returns the forum-access
notice before any forum network request. Legacy `--max-posts` and `--max-age`
options do not enable fetching or turn discovery links into verified evidence.

## How the classifier works

`briefproof.core.assess` operates on evidence supplied to it. The CLI and browser
demo supply fictional records; there is no general file-import workflow.

The classifier uses explicit text rules rather than an LLM. It separates the
original requester's statements from seller replies and excludes quotations
and code from those statements. It records requester amounts, requester activity
and closure/authorization signals independently.

Possible decisions include `candidate`, `closed`, `not_authorized`,
`seller_offer`, `stale`, `incomplete` and `unverified`. A candidate means the
supplied requester evidence expresses buying intent and payment. It still
requires confirmation of availability, identity, scope, AI-use conditions and
funding. Rule-based classification can miss wording, negation or context.

The project does not contact buyers, accept jobs, verify funding or collect
payments. CSV export and saved presets proposed for a possible paid service
have not been built.

## Checks

```sh
python3 -m unittest discover -s tests -v
```

After the forum-access correction on 5 October 2026, 32 tests passed. They cover
requester evidence, later closures, seller quotes, incomplete records, credential
handling, network restrictions and local browser request boundaries. The
6 October README refresh was checked against CLI help and an actual offline
four-case JSON export. No live search or forum request was run for that refresh.

## Historical demonstration

The [v0.1.0 demo video](https://github.com/snehaapratap/briefproof/releases/download/v0.1.0/briefproof-demo.mp4)
shows behavior before the forum-access restriction was identified. It is a
historical recording, not a demonstration of the current supported workflow.
Use the corrected main branch and the instructions above.

## License

[MIT](LICENSE).
