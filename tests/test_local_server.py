"""Loopback API smoke evidence with no external network calls."""
import json
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import uuid

from fabintel.server import _Handler, _LocalHTTPServer
from fabintel.project import AnalysisCancelled
from fabintel.project import MAX_OUTCOMES


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.server = _LocalHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.local_token = "test-only-token"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_serves_local_interactive_ui_and_bundled_demo(self):
        with urlopen(self.base + "/") as response:
            page = response.read().decode()
            policy = response.headers["Content-Security-Policy"]
            self.assertEqual(response.status, 200)
            self.assertIn("Run deterministic analysis", page)
            self.assertIn("Review source relationships and limits", page)
            self.assertIn("Choose a local investigation start", page)
            self.assertIn("Abnormal lot and outcome", page)
            self.assertIn("Process/maintenance/change interval", page)
            self.assertIn("SYNTHETIC / LOCAL SNAPSHOT MODE", page)
            self.assertIn("test-only-token", page)
            self.assertIn('src="/ui/app.js"', page)
            self.assertIn('href="/ui/styles.css"', page)
            self.assertNotIn("unsafe-inline", policy)
            self.assertIn("script-src 'self'", policy)
        with urlopen(self.base + "/ui/app.js") as response:
            script = response.read()
            self.assertIn(b"fabintel-local-token", script)
            self.assertIn(b"clearResults();", script)
            self.assertIn(b"max_outcome_rows", script)
            self.assertIn(b"Cancel analysis", script)
        with urlopen(self.base + "/ui/styles.css") as response:
            self.assertEqual(response.headers["Content-Type"], "text/css; charset=utf-8")
        with urlopen(self.base + "/api/demo") as response:
            self.assertEqual(json.loads(response.read())["wafer_id"], "W1")

    def test_post_returns_frozen_evidence_envelope(self):
        root = Path(__file__).resolve().parent.parent
        payload = (root / "fixtures" / "case_positive.json").read_bytes()
        request_id = str(uuid.uuid4())
        request = Request(self.base + "/api/analyze", data=payload, headers={
            "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
            "X-Fabintel-Request-ID": request_id,
        }, method="POST")
        with urlopen(request) as response:
            result = json.loads(response.read())
        self.assertEqual(result["product_id"], "p2")
        self.assertEqual(result["mode"], "SYNTHETIC_DEMO")
        self.assertEqual(result["status"], "PARTIAL")

    def test_snapshot_preflight_returns_declared_relationships_without_analysis(self):
        root = Path(__file__).resolve().parent.parent
        payload = (root / "fixtures" / "case_positive.json").read_bytes()
        request = Request(self.base + "/api/preflight", data=payload, headers={
            "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
        }, method="POST")
        with urlopen(request) as response:
            result = json.loads(response.read())
        self.assertEqual(result["status"], "READY_FOR_LOCAL_ANALYSIS")
        self.assertFalse(result["analysis_performed"])
        self.assertEqual(result["limits"]["event_rows"], 4)
        self.assertEqual(result["limits"]["outcome_rows"], 2)
        self.assertEqual(result["limits"]["max_outcome_rows"], 100000)
        self.assertFalse(result["scope"]["exposure"]["coverage_accepted"])
        self.assertEqual(result["scope"]["exposure"]["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        self.assertEqual({row["id"] for row in result["source_records"]}, {"SYN_PROCESS", "SYN_OUTCOME", "SYN_COVERAGE"})
        process_relation = next(row for row in result["relationships"] if row["id"] == "SYN_REL_WAFER_STEP")
        self.assertEqual(process_relation["event_rows"], 4)
        self.assertEqual(process_relation["status"], "CALLER_DECLARED_APPROVED")
        self.assertNotIn("claims", result)

    def test_snapshot_preflight_refuses_boolean_only_event_provenance(self):
        root = Path(__file__).resolve().parent.parent
        payload = json.loads((root / "fixtures" / "case_positive.json").read_text())
        payload["events"][0].pop("source_id")
        payload["events"][0].pop("relationship_id")
        request = Request(self.base + "/api/preflight", data=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
        }, method="POST")
        with urlopen(request) as response:
            result = json.loads(response.read())
        self.assertEqual(result["status"], "REFUSED")
        self.assertFalse(result["analysis_performed"])
        self.assertIn("approved source record", result["reason"])

    def test_api_requires_per_process_local_token(self):
        for path in ("/api/preflight", "/api/analyze", "/api/cancel"):
            request = Request(self.base + path, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 403)

    def test_api_refuses_outcome_rows_over_local_limit(self):
        payload = json.dumps({"events": [], "outcomes": [None] * (MAX_OUTCOMES + 1)}).encode()
        for path in ("/api/preflight", "/api/analyze"):
            request = Request(self.base + path, data=payload, headers={
                "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
            }, method="POST")
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 400)
            self.assertIn(b"outcomes list", caught.exception.read())

    def test_active_analysis_can_be_cancelled_without_partial_findings(self):
        request_id = str(uuid.uuid4())
        started = threading.Event()
        response_body = {}

        def cancellable_analysis(_payload, *, cancel_check):
            started.set()
            while not cancel_check():
                time.sleep(0.002)
            raise AnalysisCancelled("cancelled in test")

        root = Path(__file__).resolve().parent.parent
        payload = (root / "fixtures" / "case_positive.json").read_bytes()

        def submit_analysis():
            request = Request(self.base + "/api/analyze", data=payload, headers={
                "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
                "X-Fabintel-Request-ID": request_id,
            }, method="POST")
            try:
                with urlopen(request, timeout=3) as response:
                    response_body["status_code"] = response.status
                    response_body["body"] = json.loads(response.read())
            except HTTPError as exc:
                response_body["status_code"] = exc.code
                response_body["body"] = json.loads(exc.read())

        with patch("fabintel.server.analyze", side_effect=cancellable_analysis):
            worker = threading.Thread(target=submit_analysis)
            worker.start()
            self.assertTrue(started.wait(timeout=2), "analysis did not start")
            second = Request(self.base + "/api/analyze", data=payload, headers={
                "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
                "X-Fabintel-Request-ID": str(uuid.uuid4()),
            }, method="POST")
            with self.assertRaises(HTTPError) as busy:
                urlopen(second, timeout=2)
            self.assertEqual(busy.exception.code, 409)
            self.assertIn(b"already running", busy.exception.read())
            request = Request(self.base + "/api/cancel", data=json.dumps({"request_id": request_id}).encode(), headers={
                "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
            }, method="POST")
            with urlopen(request, timeout=2) as response:
                cancellation = json.loads(response.read())
                self.assertEqual(response.status, 202)
            worker.join(timeout=3)

        self.assertFalse(worker.is_alive(), "cancelled analysis request did not finish")
        self.assertEqual(cancellation["status"], "CANCELLATION_REQUESTED")
        self.assertEqual(response_body["status_code"], 409)
        self.assertEqual(response_body["body"]["status"], "CANCELLED")
        self.assertNotIn("claims", response_body["body"])
        self.assertNotIn("artifacts", response_body["body"])

    def test_shutdown_signals_active_analysis_threads(self):
        request_id = str(uuid.uuid4())
        started = threading.Event()
        response_body = {}

        def cancellable_analysis(_payload, *, cancel_check):
            started.set()
            while not cancel_check():
                time.sleep(0.002)
            raise AnalysisCancelled("shutdown in test")

        root = Path(__file__).resolve().parent.parent
        payload = (root / "fixtures" / "case_positive.json").read_bytes()

        def submit_analysis():
            request = Request(self.base + "/api/analyze", data=payload, headers={
                "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
                "X-Fabintel-Request-ID": request_id,
            }, method="POST")
            try:
                with urlopen(request, timeout=3) as response:
                    response_body["status_code"] = response.status
                    response_body["body"] = json.loads(response.read())
            except HTTPError as exc:
                response_body["status_code"] = exc.code
                response_body["body"] = json.loads(exc.read())

        with patch("fabintel.server.analyze", side_effect=cancellable_analysis):
            worker = threading.Thread(target=submit_analysis)
            worker.start()
            self.assertTrue(started.wait(timeout=2), "analysis did not start")
            self.server.analysis_registry.cancel_all()
            worker.join(timeout=3)

        self.assertFalse(worker.is_alive(), "shutdown cancellation did not stop the request thread")
        self.assertEqual(response_body["status_code"], 409)
        self.assertEqual(response_body["body"]["status"], "CANCELLED")
        self.assertNotIn("claims", response_body["body"])

    def test_cancel_arriving_before_analysis_is_queued_and_honored(self):
        request_id = str(uuid.uuid4())
        cancel = Request(self.base + "/api/cancel", data=json.dumps({"request_id": request_id}).encode(), headers={
            "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
        }, method="POST")
        with urlopen(cancel) as response:
            self.assertEqual(response.status, 202)

        root = Path(__file__).resolve().parent.parent
        payload = (root / "fixtures" / "case_positive.json").read_bytes()
        request = Request(self.base + "/api/analyze", data=payload, headers={
            "Content-Type": "application/json", "X-Fabintel-Token": self.server.local_token,
            "X-Fabintel-Request-ID": request_id,
        }, method="POST")
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 409)
        result = json.loads(caught.exception.read())
        self.assertEqual(result["status"], "CANCELLED")
        self.assertNotIn("claims", result)

    def test_unknown_path_is_not_served(self):
        with self.assertRaises(HTTPError):
            urlopen(self.base + "/../release/GATE_REPORT.json")


if __name__ == "__main__":
    unittest.main()
