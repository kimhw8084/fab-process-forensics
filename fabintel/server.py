"""Loopback-only UI/API host for local evidence snapshots."""
from __future__ import annotations

import json
import mimetypes
import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit
import uuid

from fabintel.contracts import validate_envelope
from fabintel.project import AnalysisCancelled, MAX_EVENTS, MAX_OUTCOMES, analyze, snapshot_preflight

BASE = Path(__file__).resolve().parent.parent
MAX_BODY_BYTES = 25 * 1024 * 1024
MAX_PENDING_CANCELLATIONS = 32
PENDING_CANCELLATION_TTL_SECONDS = 60
RECENT_ANALYSIS_IDS = 128
MAX_ACTIVE_ANALYSES = 1
MAX_CONCURRENT_API_REQUESTS = 2


@dataclass
class _AnalysisRecord:
    cancel_event: threading.Event
    active: bool
    created_at: float


class _AnalysisRegistry:
    """Bounded, per-server cancellation state; IDs are client-generated UUIDs."""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: dict[str, _AnalysisRecord] = {}
        self._completed_order: deque[str] = deque()
        self._completed: set[str] = set()

    def _prune(self, now: float) -> None:
        expired = [
            key for key, record in self._records.items()
            if not record.active and now - record.created_at > PENDING_CANCELLATION_TTL_SECONDS
        ]
        for key in expired:
            self._records.pop(key, None)

    def begin(self, request_id: str) -> threading.Event:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if request_id in self._completed:
                raise ValueError("This analysis request ID has already completed.")
            record = self._records.get(request_id)
            if record is not None and record.active:
                raise ValueError("This analysis request ID is already active.")
            if sum(item.active for item in self._records.values()) >= MAX_ACTIVE_ANALYSES:
                raise ValueError("Another local analysis is already running; wait for it to finish or cancel it.")
            if record is None:
                record = _AnalysisRecord(threading.Event(), True, now)
                self._records[request_id] = record
            else:
                record.active = True
            return record.cancel_event

    def cancel(self, request_id: str) -> str:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if request_id in self._completed:
                return "NOT_ACTIVE"
            record = self._records.get(request_id)
            if record is None:
                pending = sum(not item.active for item in self._records.values())
                if pending >= MAX_PENDING_CANCELLATIONS:
                    return "BUSY"
                record = _AnalysisRecord(threading.Event(), False, now)
                self._records[request_id] = record
            record.cancel_event.set()
            return "REQUESTED"

    def finish(self, request_id: str) -> None:
        with self._lock:
            self._records.pop(request_id, None)
            if request_id not in self._completed:
                self._completed.add(request_id)
                self._completed_order.append(request_id)
                while len(self._completed_order) > RECENT_ANALYSIS_IDS:
                    self._completed.discard(self._completed_order.popleft())

    def cancel_all(self) -> None:
        with self._lock:
            for record in self._records.values():
                record.cancel_event.set()


def _valid_request_id(value) -> str:
    if not isinstance(value, str):
        raise ValueError("Analysis request ID must be a UUID.")
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Analysis request ID must be a UUID.") from exc


class _LocalHTTPServer(ThreadingHTTPServer):
    # Wait for bounded work to observe cancellation before the local process exits.
    daemon_threads = False

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.local_token = secrets.token_urlsafe(32)
        self.analysis_registry = _AnalysisRegistry()
        self.request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_API_REQUESTS)
        self.follow_up_lock = threading.Lock()
        self.follow_up_decisions: deque[dict] = deque(maxlen=128)

    def record_follow_up_decision(self, candidate: dict, decision: str, request_id: str | None, status: str, audit_ids: list[str] | None = None):
        canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        row = {
            "correlation_id": str(uuid.uuid4()),
            "candidate_sha256": hashlib.sha256(canonical).hexdigest(),
            "candidate_category": candidate.get("category"),
            "decision": decision,
            "request_id": request_id,
            "status": status,
            "mcp_audit_ids": list(audit_ids or []),
        }
        with self.follow_up_lock:
            self.follow_up_decisions.append(row)
        return row


class _Handler(BaseHTTPRequestHandler):
    server_version = "FabIntelLocal/0.2"

    def log_message(self, format, *args):
        # Keep request content and potentially sensitive local data out of logs.
        return

    def _send(self, status, content_type, body):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/reference" or route == "/reference/":
            dist = BASE / "ui" / "reference-host" / "dist" / "index.html"
            if not dist.is_file():
                self._send(503, "application/json; charset=utf-8", '{"error":"Reference host assets are not built. Run the documented offline host build."}')
                return
            page = dist.read_text(encoding="utf-8").replace("__LOCAL_TOKEN__", self.server.local_token)
            self._send(200, "text/html; charset=utf-8", page)
            return
        if route.startswith("/reference/"):
            root = (BASE / "ui" / "reference-host" / "dist").resolve()
            candidate = (root / route.removeprefix("/reference/")).resolve()
            if root not in candidate.parents or not candidate.is_file():
                self._send(404, "application/json; charset=utf-8", '{"error":"not found"}')
                return
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            if content_type in {"text/javascript", "text/css", "text/html"}:
                content_type += "; charset=utf-8"
            self._send(200, content_type, candidate.read_bytes())
            return
        if route == "/api/reference/options":
            if self.headers.get("X-Fabintel-Token") != self.server.local_token:
                self._send(403, "application/json; charset=utf-8", '{"error":"local session token required"}')
                return
            try:
                from fabintel.reference_workflow import run_reference_options
                result = run_reference_options()
                self._send(200, "application/json; charset=utf-8", json.dumps(result, sort_keys=True))
            except Exception as exc:
                self._send(502, "application/json; charset=utf-8", json.dumps({
                    "error": f"Configured synthetic MCP options failed ({type(exc).__name__}).",
                }))
            return
        if self.path in ("/", "/ui/index.html"):
            page = (BASE / "ui" / "index.html").read_text(encoding="utf8").replace("__LOCAL_TOKEN__", self.server.local_token)
            self._send(200, "text/html; charset=utf-8", page)
            return
        if self.path == "/ui/app.js":
            self._send(200, "text/javascript; charset=utf-8", (BASE / "ui" / "app.js").read_text(encoding="utf8"))
            return
        if self.path == "/ui/p2-panels.js":
            self._send(200, "text/javascript; charset=utf-8", (BASE / "ui" / "p2-panels.js").read_text(encoding="utf8"))
            return
        if self.path == "/ui/styles.css":
            self._send(200, "text/css; charset=utf-8", (BASE / "ui" / "styles.css").read_text(encoding="utf8"))
            return
        if self.path == "/api/demo":
            body = (BASE / "fixtures" / "case_positive.json").read_text(encoding="utf8")
            self._send(200, "application/json; charset=utf-8", body)
            return
        self._send(404, "application/json; charset=utf-8", '{"error":"not found"}')

    def do_POST(self):
        if self.path == "/api/cancel":
            self._handle_post()
            return
        if not self.server.request_slots.acquire(blocking=False):
            self._send(429, "application/json; charset=utf-8", '{"error":"Too many local API requests are already active."}')
            return
        try:
            self._handle_post()
        finally:
            self.server.request_slots.release()

    def _handle_post(self):
        route = urlsplit(self.path).path
        if route not in ("/api/preflight", "/api/analyze", "/api/cancel", "/api/reference/investigate", "/api/reference/follow-up"):
            self._send(404, "application/json; charset=utf-8", '{"error":"not found"}')
            return
        if self.headers.get("X-Fabintel-Token") != self.server.local_token:
            self._send(403, "application/json; charset=utf-8", '{"error":"local session token required"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError(f"Request body must be between 0 and {MAX_BODY_BYTES} bytes.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/cancel":
                if not isinstance(payload, dict):
                    raise ValueError("Cancellation body must be a JSON object.")
                request_id = _valid_request_id(payload.get("request_id"))
                state = self.server.analysis_registry.cancel(request_id)
                if state == "REQUESTED":
                    self._send(202, "application/json; charset=utf-8", json.dumps({
                        "status": "CANCELLATION_REQUESTED", "request_id": request_id,
                    }))
                elif state == "BUSY":
                    self._send(429, "application/json; charset=utf-8", json.dumps({
                        "error": "Too many pending cancellation requests.",
                    }))
                else:
                    self._send(409, "application/json; charset=utf-8", json.dumps({
                        "status": "NOT_ACTIVE", "request_id": request_id,
                    }))
                return
            follow_up_candidate = None
            follow_up_decision = None
            if route == "/api/reference/follow-up":
                if not isinstance(payload, dict):
                    raise ValueError("Follow-up body must be a JSON object.")
                follow_up_decision = payload.get("decision")
                follow_up_candidate = payload.get("candidate")
                if (follow_up_decision not in {"AUTHORIZE_SYNTHETIC_READ", "DENY"}
                        or not isinstance(follow_up_candidate, dict)
                        or follow_up_candidate.get("category") != "LOT_MEMBERSHIP_CONFLICT"
                        or follow_up_candidate.get("proposed_not_executed") is not True):
                    raise ValueError("Follow-up requires an explicit decision for an unexecuted source-linked lot-membership proposal.")
                if follow_up_decision == "DENY":
                    raw_request_id = self.headers.get("X-Fabintel-Request-ID")
                    denied = self.server.record_follow_up_decision(
                        follow_up_candidate, "DENY", raw_request_id, "DENIED_WITHOUT_MCP_READ",
                    )
                    self._send(200, "application/json; charset=utf-8", json.dumps({
                        "status": "DENIED", "read_executed": False, "decision_audit": denied,
                    }, sort_keys=True))
                    return
                payload = payload.get("request")

            if route in ("/api/reference/investigate", "/api/reference/follow-up"):
                request_id = _valid_request_id(self.headers.get("X-Fabintel-Request-ID"))
                if not isinstance(payload, dict):
                    raise ValueError("Reference investigation body must be a JSON object.")
                targets = payload.get("target_wafer_ids")
                cohort = payload.get("cohort_wafer_ids")
                suspected = payload.get("suspected_exposure")
                time_window = payload.get("time_window")
                mock_delay_ms = payload.get("mock_peer_delay_ms", 0)
                if not isinstance(mock_delay_ms, int) or isinstance(mock_delay_ms, bool) or not 0 <= mock_delay_ms <= 1000:
                    raise ValueError("Mock peer delay must be an integer between 0 and 1000 milliseconds.")
                if (not isinstance(targets, list) or not 1 <= len(targets) <= 10
                        or any(not isinstance(value, str) or not value for value in targets)
                        or len(targets) != len(set(targets))):
                    raise ValueError("Choose between 1 and 10 distinct source-observed abnormal wafer identities.")
                if (not isinstance(cohort, list) or not 1 <= len(cohort) <= MAX_OUTCOMES
                        or any(not isinstance(value, str) or not value for value in cohort)
                        or len(cohort) != len(set(cohort)) or not set(targets).issubset(cohort)):
                    raise ValueError("The comparison cohort must contain distinct observed wafer identities and every target.")
                if not isinstance(suspected, dict) or set(suspected) - {"chamber_id", "tool_id", "start", "end"}:
                    raise ValueError("Suspected exposure must use one configured equipment identity and a bounded time interval.")
                scope_keys = [key for key in ("chamber_id", "tool_id") if isinstance(suspected.get(key), str) and suspected.get(key)]
                if len(scope_keys) != 1:
                    raise ValueError("Choose exactly one chamber or equipment identity from source-backed options.")
                if not isinstance(time_window, dict) or set(time_window) != {"start", "end"}:
                    raise ValueError("Investigation time_window must have start and end timestamps.")
                from datetime import datetime
                def parse_time(value, label):
                    if not isinstance(value, str):
                        raise ValueError(f"{label} must be a timezone-aware ISO timestamp.")
                    try:
                        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise ValueError(f"{label} must be a valid ISO timestamp.") from exc
                    if parsed.tzinfo is None or parsed.utcoffset() is None:
                        raise ValueError(f"{label} must include a timezone.")
                    return parsed
                window_start, window_end = (parse_time(time_window[key], f"time_window.{key}") for key in ("start", "end"))
                scope_start, scope_end = (parse_time(suspected.get(key), f"suspected_exposure.{key}") for key in ("start", "end"))
                if window_end <= window_start or scope_end <= scope_start:
                    raise ValueError("Investigation and suspected exposure windows must have positive duration.")
                if (scope_start.astimezone(timezone.utc) != window_start.astimezone(timezone.utc)
                        or scope_end.astimezone(timezone.utc) != window_end.astimezone(timezone.utc)):
                    raise ValueError("The investigation time_window must exactly match the suspected exposure interval.")
                normalized = {
                    "target_wafer_ids": targets,
                    "cohort_wafer_ids": cohort,
                    "suspected_exposure": suspected,
                    "time_window": time_window,
                }
                try:
                    cancellation = self.server.analysis_registry.begin(request_id)
                except ValueError as exc:
                    self._send(409, "application/json; charset=utf-8", json.dumps({"error": str(exc)}))
                    return
                try:
                    from fabintel.reference_workflow import run_reference_investigation
                    result = run_reference_investigation(
                        normalized, cancellation, operation_id=request_id, delay_ms=mock_delay_ms,
                        follow_up_proposal=(
                            {"candidate": follow_up_candidate}
                            if follow_up_decision == "AUTHORIZE_SYNTHETIC_READ" else None
                        ),
                    )
                    if cancellation.is_set():
                        raise AnalysisCancelled("Investigation cancelled by the operator.")
                    if follow_up_decision == "AUTHORIZE_SYNTHETIC_READ":
                        follow_up = result.get("provenance", {}).get("mcp_integration", {}).get("follow_up", {})
                        audit_ids = [item.get("audit_id") for item in follow_up.get("read_operations", []) if item.get("audit_id")]
                        decision_audit = self.server.record_follow_up_decision(
                            follow_up_candidate, follow_up_decision, request_id,
                            follow_up.get("status", "READ_COMPLETED"), audit_ids,
                        )
                        follow_up["decision_audit"] = decision_audit
                    validate_envelope(result)
                    self._send(200, "application/json; charset=utf-8", json.dumps(result, sort_keys=True))
                except AnalysisCancelled:
                    if follow_up_decision == "AUTHORIZE_SYNTHETIC_READ":
                        self.server.record_follow_up_decision(
                            follow_up_candidate, follow_up_decision, request_id, "CANCELLED",
                        )
                    self._send(409, "application/json; charset=utf-8", json.dumps({
                        "status": "CANCELLED",
                        "reason": "The MCP investigation stopped; no partial evidence was returned.",
                    }))
                except Exception as exc:
                    if follow_up_decision == "AUTHORIZE_SYNTHETIC_READ":
                        self.server.record_follow_up_decision(
                            follow_up_candidate, follow_up_decision, request_id, f"FAILED:{type(exc).__name__}",
                        )
                    self._send(502, "application/json; charset=utf-8", json.dumps({
                        "error": f"Configured synthetic MCP investigation failed ({type(exc).__name__}).",
                    }))
                finally:
                    self.server.analysis_registry.finish(request_id)
                return
            rows = payload.get("events", []) if isinstance(payload, dict) else None
            outcomes = payload.get("outcomes", []) if isinstance(payload, dict) else None
            if not isinstance(rows, list) or len(rows) > MAX_EVENTS:
                raise ValueError(f"Expected an object with at most {MAX_EVENTS} event rows.")
            if not isinstance(outcomes, list) or len(outcomes) > MAX_OUTCOMES:
                raise ValueError(f"Expected an outcomes list with at most {MAX_OUTCOMES} rows.")
            if self.path == "/api/preflight":
                result = snapshot_preflight(payload, payload_bytes=length)
                self._send(200, "application/json; charset=utf-8", json.dumps(result, sort_keys=True))
                return
            request_id = _valid_request_id(self.headers.get("X-Fabintel-Request-ID"))
            try:
                cancellation = self.server.analysis_registry.begin(request_id)
            except ValueError as exc:
                self._send(409, "application/json; charset=utf-8", json.dumps({"error": str(exc)}))
                return
            try:
                result = analyze(payload, cancel_check=cancellation.is_set)
                if cancellation.is_set():
                    raise AnalysisCancelled("Analysis was cancelled by the operator.")
                validate_envelope(result)
                self._send(200, "application/json; charset=utf-8", json.dumps(result, sort_keys=True))
            except AnalysisCancelled:
                self._send(409, "application/json; charset=utf-8", json.dumps({
                    "status": "CANCELLED",
                    "reason": "Analysis stopped at a cancellation checkpoint; no partial findings were returned.",
                }))
            finally:
                self.server.analysis_registry.finish(request_id)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send(400, "application/json; charset=utf-8", json.dumps({"error": str(exc)}))


def serve_local(host="127.0.0.1", port=8765):
    if host != "127.0.0.1" or not 1 <= port <= 65535:
        raise ValueError("The UI host must bind to loopback at a valid port.")
    server = _LocalHTTPServer((host, port), _Handler)
    print(f"Fab Process Forensics local UI: http://{host}:{port}/ (Ctrl-C stops the server)")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.analysis_registry.cancel_all()
        server.server_close()
