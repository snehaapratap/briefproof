from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from briefproof.core import (FetchError, PublicClient, SafeRedirect, assess, discover,
                             plain_text, topic_url, verify)
from briefproof.__main__ import main


NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)


def post(number, text, *, author="Buyer", age=0):
    return {"id": number, "post_number": number, "username": author, "cooked": f"<p>{text}</p>",
            "created_at": (NOW - timedelta(days=age)).isoformat()}


def analyze(posts, *, complete=True, closed=False):
    topic = {"title": "Test request", "closed": closed,
             "post_stream": {"stream": [p["id"] for p in posts]}}
    return assess(topic, posts, "https://community.make.com/t/123", complete=complete, now=NOW)


class EvidenceTests(unittest.TestCase):
    def test_seller_price_cannot_become_buyer_budget(self):
        result = analyze([post(1, "I am stuck and happy to pay for help."),
                          post(2, "I can help with this for USD500.", author="Seller")])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.advertised_budget, [])

    def test_buyer_budget_in_a_later_post_is_found(self):
        result = analyze([post(1, "We are looking for an API developer."),
                          post(2, "Our budget is USD $25 per hour.")])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.advertised_budget, ["USD $25 per hour"])

    def test_late_buyer_closure_overrides_original_offer(self):
        result = analyze([post(1, "We are looking for a developer for a paid test."),
                          post(2, "The position is filled. Please do not contact us."),
                          post(3, "I can start now.", author="Seller")])
        self.assertEqual(result.status, "closed")

    def test_paid_test_filled_and_applications_closed_are_recognized(self):
        result = analyze([post(1, "Looking for an n8n builder for a paid test project."),
                          post(2, "The paid test has been filled and applications are now closed.")])
        self.assertEqual(result.status, "closed")

    def test_excerpt_contains_the_actual_budget_when_paragraph_is_long(self):
        result = analyze([post(1, "We are looking for a developer. " + "Background information. " * 20 + "Our budget is USD25.")])
        amount = next(e for e in result.evidence if e.kind == "requester_amount")
        self.assertIn("USD25", amount.text)

    def test_seller_claim_does_not_close_the_request(self):
        result = analyze([post(1, "I am stuck and happy to pay for help."),
                          post(2, "I found someone for another job.", author="Seller")])
        self.assertEqual(result.status, "candidate")

    def test_quotes_do_not_supply_buyer_payment_or_closure(self):
        result = analyze([post(1, "We are looking for help.<blockquote>Our budget is USD900. The position is filled.</blockquote>")])
        self.assertEqual(result.status, "unverified")
        self.assertEqual(result.advertised_budget, [])

    def test_recent_seller_does_not_refresh_stale_request(self):
        result = analyze([post(1, "I am stuck and happy to pay for help.", age=45),
                          post(2, "I can help now.", author="Seller", age=0)])
        self.assertEqual(result.status, "stale")
        self.assertEqual(result.requester_age_days, 45)

    def test_incomplete_thread_cannot_be_a_candidate(self):
        result = analyze([post(1, "I am stuck and happy to pay for help.")], complete=False)
        self.assertEqual(result.status, "incomplete")

    def test_rfq_without_authorized_pay_is_excluded(self):
        result = analyze([post(1, "We are looking for estimates. No paid work authorised yet.")])
        self.assertEqual(result.status, "not_authorized")

    def test_seller_ad_is_not_a_job(self):
        result = analyze([post(1, "I offer automation services. Hire me. My hourly rate is USD25.")])
        self.assertEqual(result.status, "seller_offer")

    def test_missing_original_is_unverified(self):
        result = analyze([post(2, "I can help for USD25.", author="Seller")])
        self.assertEqual(result.status, "unverified")

    def test_explicit_reopening_after_closure(self):
        result = analyze([post(1, "I am stuck and happy to pay for help."),
                          post(2, "The position is filled."),
                          post(3, "The position is open again; still looking for help.")])
        self.assertEqual(result.status, "candidate")

    def test_platform_closed_flag_is_authoritative(self):
        result = analyze([post(1, "I am stuck and happy to pay for help.")], closed=True)
        self.assertEqual(result.status, "closed")

    def test_quoted_script_and_code_are_not_evidence(self):
        text = plain_text("<p>A real request.</p><script>position filled</script><pre>USD500</pre><p>End.</p>")
        self.assertNotIn("filled", text)
        self.assertNotIn("USD500", text)
        self.assertIn("A real request", text)


class NetworkingTests(unittest.TestCase):
    def test_forum_requests_are_blocked_before_any_network_access(self):
        for host in ("community.make.com", "community.n8n.io"):
            client = PublicClient()
            with self.subTest(host=host), patch.object(client.opener, "open") as network:
                with self.assertRaisesRegex(FetchError, "forum fetching is disabled"):
                    verify(f"https://{host}/t/123", client)
                network.assert_not_called()

    def test_topic_urls_reject_private_hosts_ports_and_credentials(self):
        bad = ["http://community.make.com/t/123", "https://localhost/t/123", "https://127.0.0.1/t/123",
               "https://community.make.com.evil.invalid/t/123", "https://user@community.make.com/t/123",
               "https://community.make.com:8443/t/123", "https://community.make.com/private"]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ValueError):
                topic_url(url)

    def test_topic_urls_canonicalize_slug_reply_and_query(self):
        self.assertEqual(topic_url("https://community.n8n.io/t/some-request/123/7?u=user"),
                         ("https://community.n8n.io", 123))

    def test_fetch_rejects_a_cross_host_url_before_requesting(self):
        with self.assertRaises(FetchError):
            PublicClient().get_json("https://localhost/private")

    def test_redirect_cannot_move_credentials_to_another_host(self):
        from urllib.request import Request
        request = Request("https://serpapi.com/search.json?api_key=PRIVATE_TEST_KEY")
        with self.assertRaises(FetchError) as exc:
            SafeRedirect().redirect_request(request, None, 302, "", {}, "https://other.invalid/")
        self.assertNotIn("PRIVATE_TEST_KEY", str(exc.exception))

    def test_discovery_deduplicates_and_ignores_unsupported_sites(self):
        class Client:
            def get_json(self, url):
                return {"organic_results": [
                    {"title": "Job", "link": "https://community.make.com/t/a/123"},
                    {"title": "Same job", "link": "https://community.make.com/t/a/123/3"},
                    {"title": "Unsupported", "link": "https://example.invalid/job"}],
                    "search_metadata": {"id": "test-search"}}
        results, search_id = discover("paid repair", "PRIVATE_TEST_KEY", Client())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://community.make.com/t/123")
        self.assertEqual(search_id, "test-search")
        self.assertNotIn("PRIVATE_TEST_KEY", json.dumps(results))

    def test_provider_error_cannot_echo_key(self):
        class Client:
            def get_json(self, url):
                return {"error": "Wrong api_key PRIVATE_TEST_KEY"}
        with self.assertRaises(FetchError) as exc:
            discover("paid repair", "PRIVATE_TEST_KEY", Client())
        self.assertNotIn("PRIVATE_TEST_KEY", str(exc.exception))

    def test_all_reply_batches_are_read_before_assessment(self):
        class Client:
            def __init__(self): self.urls = []
            def get_json(self, url):
                self.urls.append(url)
                if "posts.json" in url:
                    return {"post_stream": {"posts": [post(21, "The position is filled.")]}}
                return {"title": "Paid test", "post_stream": {"stream": [1, 21],
                    "posts": [post(1, "We are looking for a developer for a paid test.")]}}
        client = Client()
        result = verify("https://community.make.com/t/request/123", client)
        self.assertEqual(len(client.urls), 2)
        self.assertTrue(result.complete_thread)
        self.assertEqual(result.status, "closed")

    def test_posts_limit_marks_missing_closure_as_incomplete(self):
        class Client:
            def get_json(self, url):
                if "posts.json" in url:
                    return {"post_stream": {"posts": [post(i, "I can help.", author="Seller") for i in range(2, 21)]}}
                return {"title": "Paid test", "post_stream": {"stream": list(range(1, 22)),
                    "posts": [post(1, "I am stuck and happy to pay for help.")]}}
        result = verify("https://community.make.com/t/123", Client(), max_posts=20)
        self.assertFalse(result.complete_thread)
        self.assertEqual(result.status, "incomplete")


class CliTests(unittest.TestCase):
    def test_demo_report_is_explicitly_fictional_and_has_four_distinct_decisions(self):
        with tempfile.TemporaryDirectory() as tmp, patch("sys.stdout", new_callable=io.StringIO):
            path = Path(tmp) / "demo.json"
            self.assertEqual(main(["demo", "--output", str(path)]), 0)
            data = json.loads(path.read_text())
            self.assertTrue(data["fictional"])
            self.assertEqual([row["status"] for row in data["leads"]],
                             ["candidate", "closed", "not_authorized", "seller_offer"])

    def test_missing_key_fails_before_network_activity(self):
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as exc:
                main(["search", "paid repair"])
            self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
