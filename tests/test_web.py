import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from briefproof.web import make_handler


class BrowserBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("private-test-key", "local-test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, mode="demo", **overrides):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Origin": self.origin, "X-BriefProof-Token": "local-test-token", "Content-Type": "application/json"}
        headers.update(overrides)
        connection.request("POST", "/api/check", json.dumps({"mode": mode, "query": "test"}), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_same_origin_offline_demo_runs_actual_checks(self):
        status, data = self.post()
        self.assertEqual(status, 200)
        self.assertTrue(data["fictional"])
        self.assertEqual({lead["status"] for lead in data["leads"]},
                         {"candidate", "closed", "not_authorized", "seller_offer"})
        self.assertNotIn("private-test-key", json.dumps(data))

    def test_cross_origin_request_is_rejected_before_network(self):
        with patch("briefproof.web.run_check") as run:
            status, _ = self.post("search", Origin="https://untrusted.example")
            self.assertEqual(status, 403)
            run.assert_not_called()

    def test_rebound_host_and_missing_token_are_rejected(self):
        with patch("briefproof.web.run_check") as run:
            self.assertEqual(self.post(Host=f"evil.example:{self.port}")[0], 403)
            self.assertEqual(self.post(**{"X-BriefProof-Token": ""})[0], 403)
            run.assert_not_called()

    def test_local_session_caps_search_credit_spending(self):
        with patch("briefproof.web.run_check", return_value={"leads": []}) as run:
            for _ in range(8):
                self.assertEqual(self.post("search")[0], 200)
            self.assertEqual(self.post("search")[0], 429)
            self.assertEqual(run.call_count, 8)

    def test_private_key_is_absent_from_html_and_error_responses(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request("GET", "/")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertNotIn(b"private-test-key", response.read())
        connection.close()
        status, data = self.post("invalid")
        self.assertEqual(status, 400)
        self.assertNotIn("private-test-key", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
