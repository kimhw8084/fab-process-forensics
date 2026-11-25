"""Held-out protocol and boundary checks against the real synthetic MCP server."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
import uuid

from fabintel.mcp_adapter import (
    ConfiguredMCPAdapter,
    MCPAdapterError,
    MCPConfigurationError,
    MCPContractError,
    MCPPermissionDenied,
    MCPReadCancelled,
)
from fabintel.mcp_workflow import investigate_with_mcp


HAS_MCP_SDK = importlib.util.find_spec("mcp") is not None
ROOT = Path(__file__).resolve().parents[1]
SDK_PROTOCOL_WINDOW = {
    "start": "2026-11-21T00:00:00+00:00",
    "end": "2026-11-22T00:00:00+00:00",
}
PLAN = {
    "source_ids": ["SYN_PROCESS"],
    "relationship_ids": ["SYN_REL_WAFER_STEP"],
    "time_window": SDK_PROTOCOL_WINDOW,
    "time_field": "timestamp",
}
ENGINEER_PLAN = {
    "source_ids": ["SYN_PROCESS", "SYN_OUTCOMES", "SYN_EXPOSURE_COVERAGE", "SYN_HISTORY_COVERAGE", "SYN_ROUTE_DEFINITIONS", "SYN_ROUTE_COVERAGE"],
    "relationship_ids": ["SYN_REL_WAFER_STEP", "SYN_REL_WAFER_OUTCOME", "SYN_REL_EXPOSURE_COVERAGE", "SYN_REL_HISTORY_COVERAGE", "SYN_REL_ROUTE_DEFINITION", "SYN_REL_ROUTE_COVERAGE"],
    "time_window": SDK_PROTOCOL_WINDOW,
    "read_plans": [
        {"source_ids": ["SYN_PROCESS"], "relationship_ids": ["SYN_REL_WAFER_STEP"], "time_field": "timestamp", "dataset_role": "events"},
        {"source_ids": ["SYN_OUTCOMES"], "relationship_ids": ["SYN_REL_WAFER_OUTCOME"], "time_field": "timestamp", "dataset_role": "outcomes"},
        {"source_ids": ["SYN_EXPOSURE_COVERAGE"], "relationship_ids": ["SYN_REL_EXPOSURE_COVERAGE"], "time_field": "timestamp", "dataset_role": "coverage"},
        {"source_ids": ["SYN_HISTORY_COVERAGE"], "relationship_ids": ["SYN_REL_HISTORY_COVERAGE"], "time_field": "timestamp", "dataset_role": "history_coverage"},
        {"source_ids": ["SYN_ROUTE_DEFINITIONS"], "relationship_ids": ["SYN_REL_ROUTE_DEFINITION"], "time_field": "timestamp", "dataset_role": "route_definitions"},
        {"source_ids": ["SYN_ROUTE_COVERAGE"], "relationship_ids": ["SYN_REL_ROUTE_COVERAGE"], "time_field": "timestamp", "dataset_role": "route_coverage"},
    ],
}
ENGINEER_REFS = [
    {"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"},
    {"source_id": "SYN_OUTCOMES", "entity_type": "wafer", "entity_id": "SYN-W1"},
    {"source_id": "SYN_EXPOSURE_COVERAGE", "entity_type": "exposure_coverage", "entity_id": "SYN-COV-1"},
    {"source_id": "SYN_HISTORY_COVERAGE", "entity_type": "history_coverage", "entity_id": "SYN-HISTORY-COV-1"},
    {"source_id": "SYN_ROUTE_DEFINITIONS", "entity_type": "route_definition", "entity_id": "SYN-BASE-v1"},
    {"source_id": "SYN_ROUTE_COVERAGE", "entity_type": "route_coverage", "entity_id": "SYN-ROUTE-COV-1"},
]
ENGINEER_EXPOSURE = {
    "chamber_id": "SYN-C1",
    "start": "2026-11-21T03:00:00+00:00",
    "end": "2026-11-21T06:00:00+00:00",
}
LIMITS = {"max_rows": 10, "max_bytes": 30000, "max_seconds": 5}


def make_config(*, mutate: str | None = None, delay_ms: int = 0, timeout: float = 8, prefix: str = "", scenario: str = "legacy"):
    args = ["-m", "fabintel.synthetic_mcp_server", "--delay-ms", str(delay_ms), "--scenario", scenario]
    if mutate:
        args.extend(["--mutate", mutate])
    if prefix:
        args.extend(["--tool-prefix", prefix])
    transport = {
        "kind": "stdio", "command": sys.executable, "args": args, "cwd": str(ROOT),
    }
    if os.environ.get("P2_TEST_SDK_PATH"):
        transport["environment"] = {"PYTHONPATH": "P2_TEST_SDK_PATH"}
    return {
        "schema_version": "p2-mcp-client-config/v1",
        "transport": transport,
        "tools": {name: prefix + name for name in (
            "discover", "semantics", "relationships", "read_bounded", "cancel", "audit",
        )},
        "request_timeout_seconds": timeout,
        "max_response_bytes": 32768,
    }


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def sdk_subprocess_environment():
    environment = os.environ.copy()
    sdk_path = environment.get("P2_TEST_SDK_PATH")
    if sdk_path:
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = sdk_path + (os.pathsep + existing if existing else "")
    return environment


def make_http_config(port: int, *, timeout: float = 8):
    config = make_config(timeout=timeout)
    config["transport"] = {"kind": "streamable_http", "url": f"http://127.0.0.1:{port}/mcp"}
    return config


async def prepare(adapter: ConfiguredMCPAdapter):
    discovered = await adapter.discover()
    await adapter.semantics(["SYN_PROCESS"], "SYN-SEM-1")
    relationships = await adapter.relationships(
        [{"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"}],
        SDK_PROTOCOL_WINDOW,
    )
    return discovered, relationships


@unittest.skipUnless(HAS_MCP_SDK, "Install the pinned offline MCP SDK candidate to run protocol integration cases.")
class MCPAdapterProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_peer_read_runs_journey_exposure_and_evidence_pipeline(self):
        async with ConfiguredMCPAdapter(make_config(prefix="fixture_")) as adapter:
            evidence = await investigate_with_mcp(
                adapter,
                PLAN,
                "SYNTHETIC_READ",
                LIMITS,
                [{"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"}],
                suspected_exposure={
                    "chamber_id": "SYN-C1",
                    "start": "2026-11-21T03:00:00+00:00",
                    "end": "2026-11-21T06:00:00+00:00",
                },
            )
        self.assertEqual(evidence["mode"], "SYNTHETIC_DEMO")
        self.assertIn(evidence["status"], {"VALID", "PARTIAL"})
        self.assertEqual(evidence["transformations"][1]["journeys"][0]["wafer_id"], "SYN-W1")
        self.assertEqual(evidence["transformations"][2]["exposure"]["definitely_exposed"], ["SYN-W1"])
        self.assertEqual(evidence["transformations"][2]["exposure"]["unknown"], ["SYN-W2"])
        self.assertEqual(evidence["transformations"][2]["exposure"]["potentially_exposed"], ["SYN-W3"])
        self.assertEqual(evidence["provenance"]["mcp_integration"]["operations_completed"], [
            "discover", "semantics", "relationships", "read_bounded", "audit",
        ])
        self.assertEqual(evidence["provenance"]["mcp_integration"]["server_mode"], "SYNTHETIC_DEMO")
        self.assertFalse(evidence["provenance"]["mcp_integration"]["permission_scope_authenticated_for_company_use"])
        self.assertEqual(evidence["provenance"]["mcp_integration"]["read_query_hash"],
                         evidence["provenance"]["mcp_integration"]["audit_query_hash"])
        self.assertTrue(any("fixture approval" in line for line in evidence["limitations"]))

    async def test_engineer_workflow_traces_six_source_roles_through_counterevidence_and_provenance(self):
        async with ConfiguredMCPAdapter(make_config(scenario="engineer-complete")) as adapter:
            evidence = await investigate_with_mcp(
                adapter, ENGINEER_PLAN, "SYNTHETIC_READ",
                {"max_rows": 30, "max_bytes": 30000, "max_seconds": 5},
                ENGINEER_REFS, suspected_exposure=ENGINEER_EXPOSURE,
            )
        self.assertEqual(evidence["mode"], "SYNTHETIC_DEMO")
        self.assertEqual(evidence["status"], "PARTIAL")
        self.assertEqual({source["id"] for source in evidence["sources"]},
                         {"SYN_PROCESS", "SYN_OUTCOMES", "SYN_EXPOSURE_COVERAGE", "SYN_HISTORY_COVERAGE", "SYN_ROUTE_DEFINITIONS", "SYN_ROUTE_COVERAGE"})
        journeys = evidence["transformations"][1]["journeys"]
        self.assertEqual({item["wafer_id"] for item in journeys}, {"SYN-W1", "SYN-W2", "SYN-W3", "SYN-W4"})
        self.assertEqual(len(next(item for item in journeys if item["wafer_id"] == "SYN-W2")["steps"]), 2)
        self.assertEqual(len(next(item for item in journeys if item["wafer_id"] == "SYN-W2")["rework_edges"]), 1)
        journey_by_wafer = {item["wafer_id"]: item for item in journeys}
        self.assertTrue(all(item["history_coverage"]["status"] == "ASSERTED_UNVERIFIED" for item in journeys))
        self.assertEqual(journey_by_wafer["SYN-W1"]["history_coverage"]["source_references"], [{
            "source_id": "SYN_HISTORY_COVERAGE", "relationship_id": "SYN_REL_HISTORY_COVERAGE",
            "record_id": "SYN-HISTORY-COV-1",
        }])
        self.assertEqual({item["route_conformance"] for item in journeys}, {"COVERAGE_INCOMPLETE"})
        self.assertEqual(journey_by_wafer["SYN-W4"]["route_segments"][0]["observed_operations_excluding_explicit_rework"],
                         ["ETCH", "CMP", "CLEAN"])
        self.assertEqual(evidence["transformations"][1]["route_population_summary"]["coverage_status"],
                         "ASSERTED_UNVERIFIED")
        for journey in journeys:
            for step in journey["steps"]:
                self.assertEqual(step["source_id"], "SYN_PROCESS")
                self.assertEqual(step["relationship_id"], "SYN_REL_WAFER_STEP")
        exposure = evidence["transformations"][2]["exposure"]
        self.assertFalse(exposure["coverage_complete"])
        self.assertEqual(exposure["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        self.assertEqual(exposure["verified_unexposed"], [])
        self.assertEqual(exposure["definitely_exposed"], ["SYN-W1", "SYN-W2"])
        self.assertEqual(exposure["not_observed_exposed"], [])
        self.assertEqual(exposure["unknown"], ["SYN-W3", "SYN-W4"])
        self.assertEqual(exposure["not_observed_exposed_under_unverified_coverage"], ["SYN-W3", "SYN-W4"])
        self.assertEqual({row["source_id"] for row in exposure["evidence"]}, {"SYN_PROCESS"})
        comparison = evidence["counterevidence"][0]
        self.assertEqual(comparison["abnormal_wafers_with_exact_exposure"], ["SYN-W1"])
        self.assertEqual(comparison["normal_wafers_with_exact_exposure"], ["SYN-W2"])
        self.assertEqual(comparison["abnormal_wafers_verified_unexposed"], [])
        self.assertEqual(comparison["normal_wafers_verified_unexposed"], [])
        self.assertEqual(comparison["abnormal_wafers_not_observed_under_unverified_coverage"], ["SYN-W3"])
        self.assertEqual(comparison["normal_wafers_not_observed_under_unverified_coverage"], ["SYN-W4"])
        self.assertEqual(comparison["statistical_association"]["status"], "NOT_COMPUTED")
        self.assertEqual(comparison["causal_conclusion"]["status"], "NOT_ESTABLISHED")
        route_context = comparison["confounders"]["route"]
        self.assertEqual(route_context["statistical_association"]["status"], "NOT_COMPUTED")
        self.assertEqual(route_context["causal_conclusion"]["status"], "NOT_ESTABLISHED")
        incomplete_route = next(pattern for pattern in route_context["patterns"]
                                if pattern["wafer_ids"] == ["SYN-W3"])
        self.assertEqual(incomplete_route["route_conformance"], "COVERAGE_INCOMPLETE")
        self.assertEqual(incomplete_route["abnormal_wafer_ids"], ["SYN-W3"])
        self.assertEqual(incomplete_route["unknown_exposure_wafer_ids"], ["SYN-W3"])
        self.assertEqual(incomplete_route["route_segments"][0]["conformance_status"], "COVERAGE_INCOMPLETE")
        self.assertEqual(incomplete_route["route_segments"][0]["route_definition_evidence"], [{
            "source_id": "SYN_ROUTE_DEFINITIONS", "relationship_id": "SYN_REL_ROUTE_DEFINITION",
            "route_id": "SYN-BASE", "route_version": "v1",
        }])
        self.assertEqual(incomplete_route["route_segments"][0]["process_step_evidence"][0]["relationship_id"],
                         "SYN_REL_WAFER_STEP")
        self.assertTrue(all(row["source_id"] == "SYN_OUTCOMES" and row["relationship_id"] == "SYN_REL_WAFER_OUTCOME"
                            for row in comparison["outcome_evidence"]))
        integration = evidence["provenance"]["mcp_integration"]
        self.assertEqual([row["dataset_role"] for row in integration["read_operations"]],
                         ["events", "outcomes", "coverage", "history_coverage", "route_definitions", "route_coverage"])
        self.assertTrue(all(row["query_hash"] == row["audit_query_hash"] for row in integration["read_operations"]))
        self.assertFalse(integration["permission_scope_authenticated_for_company_use"])
        self.assertTrue(any("synthetic protocol peer" in item for item in evidence["limitations"]))

    async def test_follow_up_filters_are_pair_scoped_and_server_returns_only_the_target_memberships(self):
        async with ConfiguredMCPAdapter(make_config(scenario="engineer-followup")) as adapter:
            await adapter.discover()
            await adapter.semantics(["SYN_MATERIAL"], "SYN-SEM-1")
            await adapter.relationships(
                [{"source_id": "SYN_MATERIAL", "entity_type": "material_catalog", "entity_id": "SYN-MATERIAL"}],
                SDK_PROTOCOL_WINDOW,
            )
            plan = {
                "source_ids": ["SYN_MATERIAL"],
                "relationship_ids": ["SYN_REL_WAFER_LOT_MEMBERSHIP"],
                "time_window": SDK_PROTOCOL_WINDOW,
                "time_field": "timestamp",
                "filters": {"to_entity_id": "SYN-W1"},
            }
            bounded = await adapter.read_bounded(plan, "SYNTHETIC_READ", LIMITS)
            audit = await adapter.audit(bounded["operation_id"])
            self.assertEqual({row["record_id"] for row in bounded["typed_rows"]}, {"SYN-MEM-W1-A", "SYN-MEM-W1-B"})
            self.assertTrue(all(row["to_entity_id"] == "SYN-W1" for row in bounded["typed_rows"]))
            self.assertEqual(bounded["query_hash"], audit["query_hash"])

            invalid = {**plan, "filters": {"wafer_id": "SYN-W1"}}
            with self.assertRaisesRegex(MCPContractError, "not declared by every approved source relationship"):
                await adapter.read_bounded(invalid, "SYNTHETIC_READ", LIMITS)

    async def test_dataset_role_must_match_verified_source_record_kind(self):
        plan = {**ENGINEER_PLAN, "read_plans": [
            {**ENGINEER_PLAN["read_plans"][0], "dataset_role": "outcomes"},
            *ENGINEER_PLAN["read_plans"][1:],
        ]}
        async with ConfiguredMCPAdapter(make_config(scenario="engineer-complete")) as adapter:
            with self.assertRaisesRegex(MCPContractError, "conflicts with source"):
                await investigate_with_mcp(
                    adapter, plan, "SYNTHETIC_READ",
                    {"max_rows": 30, "max_bytes": 30000, "max_seconds": 5}, ENGINEER_REFS,
                    suspected_exposure=ENGINEER_EXPOSURE,
                )

    async def test_multigrain_workflow_cancellation_returns_no_partial_result_and_recovers(self):
        async with ConfiguredMCPAdapter(make_config(scenario="engineer-complete", delay_ms=500)) as adapter:
            original_audit = adapter.audit
            audit_count = 0
            first_read_audited = asyncio.Event()

            async def signal_after_audit(operation_id):
                nonlocal audit_count
                result = await original_audit(operation_id)
                audit_count += 1
                if audit_count == 1:
                    first_read_audited.set()
                return result

            adapter.audit = signal_after_audit
            task = asyncio.create_task(investigate_with_mcp(
                adapter, ENGINEER_PLAN, "SYNTHETIC_READ",
                {"max_rows": 30, "max_bytes": 30000, "max_seconds": 5}, ENGINEER_REFS,
                suspected_exposure=ENGINEER_EXPOSURE,
            ))
            await asyncio.wait_for(first_read_audited.wait(), timeout=4)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(audit_count, 1)
            recovered = await investigate_with_mcp(
                adapter, ENGINEER_PLAN, "SYNTHETIC_READ",
                {"max_rows": 30, "max_bytes": 30000, "max_seconds": 5}, ENGINEER_REFS,
                suspected_exposure=ENGINEER_EXPOSURE,
            )
            self.assertEqual(audit_count, 7)
        self.assertEqual(recovered["status"], "PARTIAL")
        self.assertEqual(recovered["counterevidence"][0]["causal_conclusion"]["status"], "NOT_ESTABLISHED")

    async def test_real_streamable_http_transport_completes_all_logical_operations(self):
        port = available_port()
        process = subprocess.Popen(
            [sys.executable, "-m", "fabintel.synthetic_mcp_server", "--transport", "streamable-http", "--port", str(port)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=sdk_subprocess_environment(),
        )
        try:
            deadline = time.monotonic() + 8
            ready = False
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        ready = True
                        break
                except OSError:
                    await asyncio.sleep(0.05)
            self.assertTrue(ready, "synthetic Streamable HTTP server did not start")
            async with ConfiguredMCPAdapter(make_http_config(port)) as adapter:
                discovered, relationships = await prepare(adapter)
                self.assertEqual(adapter._client.protocol_version, "2026-07-28")
                self.assertEqual(discovered["mode"], "SYNTHETIC_DEMO")
                self.assertTrue(relationships["relationships"][0]["approved"])
                result = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
                self.assertEqual(len(result["typed_rows"]), 3)
                audit = await adapter.audit(result["operation_id"])
                self.assertEqual(audit["query_hash"], result["query_hash"])
        finally:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)

    async def test_streamable_http_denial_bounds_cancellation_and_recovery(self):
        port = available_port()
        process = subprocess.Popen(
            [sys.executable, "-m", "fabintel.synthetic_mcp_server", "--transport", "streamable-http",
             "--port", str(port), "--delay-ms", "900"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=sdk_subprocess_environment(),
        )
        try:
            deadline = time.monotonic() + 8
            ready = False
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        ready = True
                        break
                except OSError:
                    await asyncio.sleep(0.05)
            self.assertTrue(ready, "synthetic Streamable HTTP server did not start")
            async with ConfiguredMCPAdapter(make_http_config(port)) as adapter:
                await prepare(adapter)
                with self.assertRaises(MCPPermissionDenied):
                    await adapter.semantics(["SYN_NOT_AUTHORIZED"])
                denied = await adapter._client.call_tool("read_bounded", {
                    "approved_plan": PLAN, "permission_context": "SYNTHETIC_ADMIN",
                    "limits": LIMITS, "operation_id": str(uuid.uuid4()),
                })
                self.assertTrue(denied.is_error)
                over_bound = await adapter._client.call_tool("read_bounded", {
                    "approved_plan": PLAN, "permission_context": "SYNTHETIC_READ",
                    "limits": {**LIMITS, "max_rows": 101}, "operation_id": str(uuid.uuid4()),
                })
                self.assertTrue(over_bound.is_error)

                operation_id = str(uuid.uuid4())
                pending = asyncio.create_task(adapter.read_bounded(
                    PLAN, "SYNTHETIC_READ", LIMITS, operation_id=operation_id,
                ))
                await asyncio.sleep(0.15)
                cancelled = await adapter.cancel(operation_id)
                self.assertTrue(cancelled["confirmed_stopped"])
                with self.assertRaises(MCPReadCancelled):
                    await pending

                recovered = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
                self.assertEqual(len(recovered["typed_rows"]), 3)
                audit = await adapter.audit(recovered["operation_id"])
                self.assertEqual(audit["query_hash"], recovered["query_hash"])
        finally:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)

    async def test_real_stdio_transport_negotiates_and_completes_all_logical_operations(self):
        async with ConfiguredMCPAdapter(make_config(prefix="fixture_")) as adapter:
            discovered, relationships = await prepare(adapter)
            self.assertEqual(adapter._client.protocol_version, "2026-07-28")
            self.assertEqual(discovered["mode"], "SYNTHETIC_DEMO")
            self.assertEqual(set(discovered["capabilities"]), {
                "discover", "semantics", "relationships", "read_bounded", "cancel", "audit",
            })
            self.assertTrue(relationships["relationships"][0]["approved"])
            result = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
            self.assertEqual(len(result["typed_rows"]), 3)
            self.assertEqual(result["typed_rows"][0]["grain"], "one process step instance")
            self.assertEqual(result["source_ids"], ["SYN_PROCESS"])
            self.assertEqual(result["relationship_ids"], ["SYN_REL_WAFER_STEP"])
            audit = await adapter.audit(result["operation_id"])
            self.assertEqual(audit["permission_scope"], "SYNTHETIC_READ")
            self.assertEqual(audit["query_hash"], result["query_hash"])

    async def test_server_enforces_source_and_permission_denial(self):
        async with ConfiguredMCPAdapter(make_config()) as adapter:
            await adapter.discover()
            with self.assertRaises(MCPPermissionDenied):
                await adapter.semantics(["SYN_NOT_AUTHORIZED"])
            raw = await adapter._client.call_tool("read_bounded", {
                "approved_plan": PLAN,
                "permission_context": "SYNTHETIC_ADMIN",
                "limits": LIMITS,
                "operation_id": str(uuid.uuid4()),
            })
            self.assertTrue(raw.is_error)

    async def test_server_enforces_query_row_limit_even_if_client_check_is_bypassed(self):
        async with ConfiguredMCPAdapter(make_config()) as adapter:
            await prepare(adapter)
            with self.assertRaises(MCPContractError):
                await adapter.read_bounded(PLAN, "SYNTHETIC_READ", {**LIMITS, "max_rows": 101})
            raw = await adapter._client.call_tool("read_bounded", {
                "approved_plan": PLAN,
                "permission_context": "SYNTHETIC_READ",
                "limits": {**LIMITS, "max_rows": 101},
                "operation_id": str(uuid.uuid4()),
            })
            self.assertTrue(raw.is_error)

    async def test_server_truncates_to_the_full_bounded_response_byte_limit(self):
        async with ConfiguredMCPAdapter(make_config()) as adapter:
            await prepare(adapter)
            bounded = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", {**LIMITS, "max_bytes": 1024})
            encoded_size = len(json.dumps(bounded, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            self.assertLessEqual(encoded_size, 1024)
            self.assertTrue(bounded["truncated"])

    async def test_unapproved_relationship_is_never_promoted_for_a_read(self):
        async with ConfiguredMCPAdapter(make_config()) as adapter:
            await adapter.discover()
            await adapter.semantics(["SYN_PROCESS"], "SYN-SEM-1")
            result = await adapter.relationships(
                [{"source_id": "SYN_PROCESS", "relationship_id": "SYN_UNAPPROVED"}],
                SDK_PROTOCOL_WINDOW,
            )
            self.assertFalse(result["relationships"][1]["approved"])
            plan = {**PLAN, "relationship_ids": ["SYN_UNAPPROVED"]}
            with self.assertRaises(MCPContractError):
                await adapter.read_bounded(plan, "SYNTHETIC_READ", LIMITS)

    async def test_effective_time_and_source_relationship_provenance_are_checked(self):
        async with ConfiguredMCPAdapter(make_config(mutate="relationship_hash")) as adapter:
            await adapter.discover()
            await adapter.semantics(["SYN_PROCESS"], "SYN-SEM-1")
            with self.assertRaises(MCPContractError):
                await adapter.relationships(
                    [{"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"}],
                    SDK_PROTOCOL_WINDOW,
                )
        async with ConfiguredMCPAdapter(make_config()) as adapter:
            await adapter.discover()
            await adapter.semantics(["SYN_PROCESS"], "SYN-SEM-1")
            with self.assertRaises(MCPContractError):
                await adapter.relationships(
                    [{"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"}],
                    {"start": "2026-11-22T00:00:00+00:00", "end": "2026-11-23T00:00:00+00:00"},
                )

    async def test_relationship_ids_and_join_keys_are_unambiguous_and_source_declared(self):
        for mutation in ("duplicate_relationship_id", "undeclared_relation_key"):
            async with ConfiguredMCPAdapter(make_config(mutate=mutation)) as adapter:
                await adapter.discover()
                await adapter.semantics(["SYN_PROCESS"], "SYN-SEM-1")
                with self.subTest(mutation=mutation), self.assertRaises(MCPContractError):
                    await adapter.relationships(
                        [{"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"}],
                        SDK_PROTOCOL_WINDOW,
                    )

    async def test_duplicate_source_semantics_records_are_rejected(self):
        async with ConfiguredMCPAdapter(make_config(mutate="duplicate_semantics_source")) as adapter:
            await adapter.discover()
            with self.assertRaises(MCPContractError):
                await adapter.semantics(["SYN_PROCESS"], "SYN-SEM-1")

    async def test_row_grain_time_and_relationship_are_independently_checked(self):
        for mutation in ("grain", "time", "provenance", "source_version", "source_ids"):
            async with ConfiguredMCPAdapter(make_config(mutate=mutation)) as adapter:
                await prepare(adapter)
                with self.subTest(mutation=mutation), self.assertRaises(MCPContractError):
                    await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)

    async def test_each_typed_row_is_included_in_response_relationships_and_time_semantics(self):
        for mutation in ("omit_source_references", "omit_relationship_references", "relationship_time_key"):
            async with ConfiguredMCPAdapter(make_config(mutate=mutation)) as adapter:
                await prepare(adapter)
                with self.subTest(mutation=mutation), self.assertRaises(MCPContractError):
                    await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)

    async def test_result_and_audit_hashes_and_response_bytes_are_checked(self):
        async with ConfiguredMCPAdapter(make_config(mutate="audit_hash")) as adapter:
            await prepare(adapter)
            with self.assertRaises(MCPContractError):
                await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
        async with ConfiguredMCPAdapter(make_config(mutate="oversize")) as adapter:
            await prepare(adapter)
            with self.assertRaises(MCPContractError):
                await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
        async with ConfiguredMCPAdapter(make_config(mutate="audit_scope")) as adapter:
            await prepare(adapter)
            result = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
            with self.assertRaises(MCPContractError):
                await adapter.audit(result["operation_id"])
        async with ConfiguredMCPAdapter(make_config(mutate="audit_time")) as adapter:
            await prepare(adapter)
            result = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
            with self.assertRaises(MCPContractError):
                await adapter.audit(result["operation_id"])

    async def test_cancellation_is_confirmed_and_session_recovers(self):
        async with ConfiguredMCPAdapter(make_config(delay_ms=1000)) as adapter:
            await prepare(adapter)
            operation_id = str(uuid.uuid4())
            pending = asyncio.create_task(adapter.read_bounded(
                PLAN, "SYNTHETIC_READ", LIMITS, operation_id=operation_id,
            ))
            await asyncio.sleep(0.1)
            cancelled = await adapter.cancel(operation_id)
            self.assertTrue(cancelled["confirmed_stopped"])
            with self.assertRaises(MCPReadCancelled):
                await pending
            recovered = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
            self.assertEqual(len(recovered["typed_rows"]), 3)

    async def test_server_query_timeout_does_not_poison_next_request(self):
        async with ConfiguredMCPAdapter(make_config(delay_ms=200)) as adapter:
            await prepare(adapter)
            with self.assertRaises(MCPAdapterError):
                await adapter.read_bounded(PLAN, "SYNTHETIC_READ", {**LIMITS, "max_seconds": 0.05})
            recovered = await adapter.read_bounded(PLAN, "SYNTHETIC_READ", LIMITS)
            self.assertEqual(len(recovered["typed_rows"]), 3)


class MCPAdapterConfigTests(unittest.TestCase):
    def test_rejects_remote_plain_http_and_inline_credentials(self):
        config = make_config()
        config["transport"] = {"kind": "streamable_http", "url": "http://service.example/mcp"}
        with self.assertRaises(MCPConfigurationError):
            ConfiguredMCPAdapter(config)
        config["transport"] = {"kind": "streamable_http", "url": "https://user:secret@service.example/mcp"}
        with self.assertRaises(MCPConfigurationError):
            ConfiguredMCPAdapter(config)

    def test_stdio_accepts_only_argument_vectors_and_named_environment_sources(self):
        config = make_config()
        config["transport"]["args"] = "-m fabintel.synthetic_mcp_server"
        with self.assertRaises(MCPConfigurationError):
            ConfiguredMCPAdapter(config)
        config = make_config()
        config["transport"]["environment"] = {"TOKEN": "literal-secret"}
        with self.assertRaises(MCPConfigurationError):
            ConfiguredMCPAdapter(config)


if __name__ == "__main__":
    unittest.main()
