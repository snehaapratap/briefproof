"""Optional local browser interface; keys stay in the Python process."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import os
from pathlib import Path
import secrets
import threading

from .__main__ import demo_leads
from .core import FORUM_ACCESS_NOTICE, FetchError, Lead, PublicClient, discover, verify


def run_check(payload: dict, key: str) -> dict:
    mode = payload.get("mode")
    search_id = ""
    if mode == "demo":
        leads = demo_leads()
    elif mode == "verify":
        leads = [verify(str(payload.get("url", "")), PublicClient())]
    elif mode == "search":
        query = str(payload.get("query", "")).strip()
        if not 1 <= len(query) <= 200:
            raise ValueError("Enter a search query of 1–200 characters.")
        if not key:
            raise ValueError("The server needs SERPAPI_API_KEY for live discovery. Offline demo still works.")
        results, search_id = discover(query, key, PublicClient(), limit=4)
        def inspect(result):
            lead = Lead(result["title"], result["url"], reason=FORUM_ACCESS_NOTICE)
            lead.discovery_query = query
            return lead
        with ThreadPoolExecutor(max_workers=3) as pool:
            leads = list(pool.map(inspect, results))
        leads.sort(key=lambda lead: (lead.status != "candidate", lead.requester_age_days or 0))
    else:
        raise ValueError("Choose search, verify or demo.")
    return {"mode": mode, "fictional": mode == "demo", "serpapi_search_id": search_id,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "leads": [lead.to_dict() for lead in leads]}


def make_handler(key: str, token: str):
    """Require loopback Host, same-origin POSTs and a per-launch token."""
    budget = {"searches": 0}
    lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def local_request(self):
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def send_data(self, data: bytes, status=200, kind="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def error(self, message, status=400):
            self.send_data(json.dumps({"error": message}).encode(), status)

        def do_GET(self):
            if not self.local_request():
                return self.error("Loopback host required.", 403)
            if self.path != "/":
                return self.error("Not found.", 404)
            page = Path(__file__).with_name("web.html").read_text(encoding="utf-8")
            self.send_data(page.replace("__LOCAL_TOKEN__", token).encode(), kind="text/html")

        def do_POST(self):
            origin = "http://" + self.headers.get("Host", "")
            if (not self.local_request() or self.path != "/api/check"
                    or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-BriefProof-Token", ""), token)):
                return self.error("Same-origin local browser request required.", 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 4096:
                    return self.error("Invalid request size.")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    return self.error("Expected an object.")
                if payload.get("mode") == "search":
                    with lock:
                        if budget["searches"] >= 8:
                            return self.error("Eight-search limit reached. Restart locally for another session.", 429)
                        budget["searches"] += 1
                report = run_check(payload, key)
                self.send_data(json.dumps(report).encode())
            except (FetchError, ValueError, KeyError, TypeError) as exc:
                message = str(exc) if isinstance(exc, (FetchError, ValueError)) else "Unexpected public response shape."
                self.error(message)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Run BriefProof in a local browser.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port from 1024 to 65535.")
    key = os.environ.get("SERPAPI_API_KEY", "")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(key, secrets.token_urlsafe(32)))
    print(f"BriefProof local demo: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
