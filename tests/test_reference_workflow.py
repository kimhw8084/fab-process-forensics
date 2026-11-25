"""Real loopback reference-host checks over the pinned MCP SDK transport."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import threading
import time
import unittest
import urllib.error
from urllib.request import Request, urlopen
import uuid
from unittest.mock import patch

from fabintel import server as local_server
from fabintel.mcp_adapter import ConfiguredMCPAdapter
from fabintel.reference_workflow import synthetic_adapter_config


HAS_MCP = importlib.util.find_spec("mcp") is not None
PAYLOAD = {
    "target_wafer_ids": ["SYN-W1", "SYN-W3"],
    "cohort_wafer_ids": ["SYN-W1", "SYN-W2", "SYN-W3", "SYN-W4"],
    "time_window": {
        "start": "2026-11-21T03:00:00+00:00",
        "end": "2026-11-21T06:00:00+00:00",
    },
    "suspected_exposure": {
        "chamber_id": "SYN-C1",
        "start": "2026-11-21T03:00:00+00:00",
        "end": "2026-11-21T06:00:00+00:00",
    },
}


@unittest.skipUnless(HAS_MCP, "Install the pinned offline MCP SDK candidate to run reference-host protocol integration cases.")
class ReferenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.server = local_server._LocalHTTPServer(("127.0.0.1", 0), local_server._Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.analysis_registry.cancel_all()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, *, method="GET", payload=None, token=True, request_id=None):
        headers = {}
        if token:
            headers["X-Fabintel-Token"] = self.server.local_token
        if request_id:
            headers["X-Fabintel-Request-ID"] = request_id
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        req = Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=15) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            return response.code, json.loads(response.read())

    def test_browser_module_assets_are_built_and_session_bound_option_reads_work(self):
        with urlopen(self.base + "/reference/", timeout=10) as response:
            self.assertEqual(response.status, 200)
            page = response.read().decode()
        self.assertNotIn("/src/main.tsx", page)
        self.assertIn("fabintel-local-token", page)
        self.assertIn("/reference/assets/", page)

        script_path = page.split('src="', 1)[1].split('"', 1)[0]
        with urlopen(self.base + script_path, timeout=10) as response:
            script = response.read()
        self.assertIn(b"Wafer and lot journey", script)
        self.assertIn(b"Exposure evidence and comparator populations", script)

        status, denied = self.request("/api/reference/options", token=False)
        self.assertEqual(status, 403)
        self.assertIn("token", denied["error"])
        status, options = self.request("/api/reference/options")
        self.assertEqual(status, 200)
        self.assertFalse(options["company_source_authorized"])
        self.assertTrue(options["mock_peer_permission_enforced"])
        self.assertEqual(set(options["abnormal_wafer_ids"]), {"SYN-W1", "SYN-W3"})
        self.assertEqual(len(options["audited_reads"]), 2)

    def test_complete_seven_source_engineer_workflow_preserves_counterevidence_and_lineage(self):
        status, evidence = self.request(
            "/api/reference/investigate", method="POST", payload=PAYLOAD, request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 200, evidence)
        self.assertEqual({source["id"] for source in evidence["sources"]}, {
            "SYN_PROCESS", "SYN_OUTCOMES", "SYN_EXPOSURE_COVERAGE",
            "SYN_HISTORY_COVERAGE", "SYN_ROUTE_DEFINITIONS", "SYN_ROUTE_COVERAGE", "SYN_MATERIAL",
        })
        reads = evidence["provenance"]["mcp_integration"]["read_operations"]
        self.assertEqual({read["dataset_role"] for read in reads}, {
            "events", "outcomes", "coverage", "history_coverage", "route_definitions", "route_coverage",
            "material_relationships",
        })
        self.assertTrue(all(read["query_hash"] == read["audit_query_hash"] for read in reads))

        artifact = next(item for item in evidence["artifacts"] if item["kind"] == "investigation_snapshot")
        journeys = {journey["wafer_id"]: journey for journey in artifact["journey"]["journeys"]}
        self.assertEqual([step["step_instance_id"] for step in journeys["SYN-W2"]["steps"]], ["SYN-S3", "SYN-S4"])
        self.assertTrue(journeys["SYN-W2"]["rework_edges"])
        self.assertEqual(journeys["SYN-W2"]["history_status"], "COVERAGE_ASSERTED_UNVERIFIED")
        self.assertEqual(artifact["exposure_analysis"]["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        self.assertEqual(artifact["exposure_analysis"]["definitely_exposed"], ["SYN-W1", "SYN-W2"])
        self.assertEqual(artifact["exposure_analysis"]["not_observed_exposed"], [])
        self.assertEqual(set(artifact["exposure_analysis"]["not_observed_exposed_under_unverified_coverage"]), {"SYN-W3", "SYN-W4"})
        self.assertTrue(evidence["counterevidence"])
        self.assertEqual(evidence["provenance"]["mcp_integration"]["permission_scope_authenticated_for_company_use"], False)
        self.assertTrue(evidence["provenance"]["input_sha256"])

        event_rows = [step for journey in journeys.values() for step in journey["steps"]]
        self.assertTrue(all(step["source_id"] == "SYN_PROCESS" for step in event_rows))
        self.assertTrue(all(step["relationship_id"] == "SYN_REL_WAFER_STEP" for step in event_rows))
        self.assertTrue(all(step["timestamp"] for step in event_rows))
        # The legacy fixture has process event time but no ingestion-time or
        # uncertainty observations. Those remain unknown; the mock relationship
        # must not make optional metadata mandatory for an actual step identity.
        async def check_optional_time_fields():
            async with ConfiguredMCPAdapter(synthetic_adapter_config()) as adapter:
                await adapter.discover()
                semantic = await adapter.semantics(["SYN_PROCESS"])
                self.assertTrue(semantic["sources"][0]["column_definitions"]["recorded_at"]["nullable"])
                self.assertTrue(semantic["sources"][0]["column_definitions"]["time_uncertainty_seconds"]["nullable"])
                relation = (await adapter.relationships(
                    [{"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"}],
                    {"start": "2026-11-21T00:00:00+00:00", "end": "2026-11-22T00:00:00+00:00"},
                ))["relationships"][0]
                self.assertNotIn("recorded_at", relation["keys"])
                self.assertNotIn("time_uncertainty_seconds", relation["keys"])
        asyncio.run(check_optional_time_fields())

    def test_100_wafer_mcp_browser_contract_uses_valid_defaults_and_preserves_searchable_history(self):
        with patch.dict(os.environ, {"P2_REFERENCE_SYNTHETIC_SCENARIO": "engineer-100"}):
            status, options = self.request("/api/reference/options")
            self.assertEqual(status, 200, options)
            self.assertEqual(len(options["abnormal_wafer_ids"]), 45)
            self.assertEqual(len(options["cohort_wafer_ids"]), 98)
            self.assertEqual(options["default_suspected_exposure"], {
                "chamber_id": "SYN-C1", "start": "2026-11-21T01:25:00+00:00",
                "end": "2026-11-21T01:35:00+00:00",
            })
            interval = options["default_suspected_exposure"]
            payload = {
                "target_wafer_ids": options["abnormal_wafer_ids"][:10],
                "cohort_wafer_ids": options["cohort_wafer_ids"],
                "time_window": {"start": interval["start"], "end": interval["end"]},
                "suspected_exposure": interval,
            }
            status, evidence = self.request(
                "/api/reference/investigate", method="POST", payload=payload, request_id=str(uuid.uuid4()),
            )
            candidates = [candidate for case in evidence.get("counterevidence", [])
                          for candidate in case.get("next_authorized_verification", {}).get("candidates", [])]
            candidate = next(item for item in candidates if item["category"] == "LOT_MEMBERSHIP_CONFLICT")
            denied_id = str(uuid.uuid4())
            denied_status, denied = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "DENY", "candidate": candidate, "request": payload},
                request_id=denied_id,
            )
            allowed_id = str(uuid.uuid4())
            refreshed_status, refreshed = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "AUTHORIZE_SYNTHETIC_READ", "candidate": candidate, "request": payload},
                request_id=allowed_id,
            )
        self.assertEqual(status, 200, evidence)
        self.assertEqual(denied_status, 200, denied)
        self.assertFalse(denied["read_executed"])
        self.assertEqual(denied["decision_audit"]["request_id"], denied_id)
        self.assertEqual(refreshed_status, 200, refreshed)
        follow_up = refreshed["provenance"]["mcp_integration"]["follow_up"]
        self.assertEqual(follow_up["status"], "AUTHORIZED_SYNTHETIC_READ_COMPLETED")
        self.assertTrue(follow_up["decision_audit"]["correlation_id"])
        self.assertEqual(len(follow_up["read_operations"]), 2)
        self.assertTrue(all(row["query_hash"] == row["audit_query_hash"] for row in follow_up["read_operations"]))
        integration = evidence["provenance"]["mcp_integration"]
        reads = integration["read_operations"]
        self.assertEqual(len(reads), 7)
        self.assertTrue(all(row["query_hash"] == row["audit_query_hash"] for row in reads))
        self.assertEqual(next(row["row_count"] for row in reads if row["dataset_role"] == "events"), 404)
        self.assertEqual(next(row["row_count"] for row in reads if row["dataset_role"] == "outcomes"), 98)
        artifact = next(item for item in evidence["artifacts"] if item["kind"] == "investigation_snapshot")
        journeys = {item["wafer_id"]: item for item in artifact["journey"]["journeys"]}
        self.assertIn("SYN-EW-010", journeys)
        self.assertEqual(journeys["SYN-EW-010"]["history_status"], "INCOMPLETE")
        self.assertIn("CONFLICTS_WITH_EVENT_ROW_LOT_ID", {
            step["membership_state"] for step in journeys["SYN-EW-010"]["steps"]
        })
        proposals = [candidate for case in evidence["counterevidence"]
                     for candidate in case.get("next_authorized_verification", {}).get("candidates", [])]
        self.assertIn("LOT_MEMBERSHIP_CONFLICT", {item["category"] for item in proposals})
        self.assertFalse(integration["permission_scope_authenticated_for_company_use"])

    def test_membership_conflict_follow_up_requires_explicit_authorization_and_refreshes_mcp_evidence(self):
        request = {**PAYLOAD, "target_wafer_ids": ["SYN-W1"]}
        status, initial = self.request(
            "/api/reference/investigate", method="POST", payload=request, request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 200, initial)
        candidate = next(
            item
            for investigation in initial["counterevidence"]
            for item in investigation["next_authorized_verification"]["candidates"]
            if item["category"] == "LOT_MEMBERSHIP_CONFLICT"
        )
        self.assertTrue(candidate["proposed_not_executed"])
        self.assertEqual(candidate["target_wafer_ids"], ["SYN-W1"])
        keys_by_source = {item["source_id"]: item["requested_declared_keys"] for item in candidate["source_relationships"]}
        self.assertEqual(set(keys_by_source), {"SYN_PROCESS", "SYN_MATERIAL"})
        self.assertEqual(set(keys_by_source["SYN_PROCESS"]), {"wafer_id", "step_instance_id", "lot_id", "timestamp"})
        self.assertEqual(set(keys_by_source["SYN_MATERIAL"]), {"from_entity_id", "from_entity_type", "to_entity_id", "to_entity_type"})

        denied_id = str(uuid.uuid4())
        status, denied = self.request(
            "/api/reference/follow-up", method="POST",
            payload={"decision": "DENY", "candidate": candidate, "request": request}, request_id=denied_id,
        )
        self.assertEqual(status, 200, denied)
        self.assertEqual(denied["status"], "DENIED")
        self.assertFalse(denied["read_executed"])
        self.assertEqual(denied["decision_audit"]["status"], "DENIED_WITHOUT_MCP_READ")
        self.assertEqual(denied["decision_audit"]["request_id"], denied_id)

        allowed_id = str(uuid.uuid4())
        status, refreshed = self.request(
            "/api/reference/follow-up", method="POST",
            payload={"decision": "AUTHORIZE_SYNTHETIC_READ", "candidate": candidate, "request": request}, request_id=allowed_id,
        )
        self.assertEqual(status, 200, refreshed)
        self.assertEqual(refreshed["provenance"]["mcp_integration"]["follow_up"]["status"], "AUTHORIZED_SYNTHETIC_READ_COMPLETED")
        follow_up = refreshed["provenance"]["mcp_integration"]["follow_up"]
        reads = follow_up["read_operations"]
        self.assertEqual({read["dataset_role"] for read in reads}, {"events", "material_relationships"})
        self.assertTrue(all(read["query_hash"] == read["audit_query_hash"] for read in reads))
        self.assertEqual(
            {read["filters"]["wafer_id"][0] for read in reads if read["dataset_role"] == "events"},
            {"SYN-W1"},
        )
        self.assertEqual(
            {read["filters"]["to_entity_id"][0] for read in reads if read["dataset_role"] == "material_relationships"},
            {"SYN-W1"},
        )
        self.assertTrue(all(read["source_versions"] for read in reads))
        self.assertTrue(follow_up["decision_audit"]["correlation_id"])
        self.assertEqual(len(follow_up["decision_audit"]["mcp_audit_ids"]), 2)
        artifact = next(item for item in refreshed["artifacts"] if item["kind"] == "investigation_snapshot")
        wafer = next(item for item in artifact["journey"]["journeys"] if item["wafer_id"] == "SYN-W1")
        step = next(item for item in wafer["steps"] if item["step_instance_id"] == "SYN-S1")
        self.assertEqual(step["membership_state"], "AMBIGUOUS_MULTIPLE_TIME_SCOPED_MEMBERSHIPS")
        self.assertEqual(set(step["time_scoped_material_relationship_ids"]), {"SYN-MEM-W1-A", "SYN-MEM-W1-B"})
        self.assertEqual(refreshed["counterevidence"][0]["causal_conclusion"]["status"], "NOT_ESTABLISHED")

    def test_unseen_alias_schema_onboards_then_runs_100_wafer_browser_workflow(self):
        with patch.dict(os.environ, {"P2_REFERENCE_SYNTHETIC_SCENARIO": "engineer-100-alias"}):
            status, options = self.request("/api/reference/options")
            self.assertEqual(status, 200, options)
            self.assertEqual(len(options["cohort_wafer_ids"]), 98)
            self.assertEqual(len(options["abnormal_wafer_ids"]), 45)
            self.assertIsInstance(options["protocol_version"], str)
            self.assertTrue(options["protocol_version"])
            onboarding = options["onboarding"]
            self.assertEqual(onboarding["decision"], "APPROVE_EXACT_PROPOSAL")
            self.assertFalse(onboarding["server_authorization_established"])
            self.assertFalse(onboarding["company_qualified"])
            self.assertEqual({item["source_id"] for item in onboarding["source_role_mappings"]}, {
                "FABX_PROCESS_LEDGER_V7", "FABX_WAFER_RESULTS_V2", "FABX_EXPOSURE_COVERAGE_V1",
                "FABX_HISTORY_COVERAGE_V3", "FABX_ROUTE_CATALOG_V5", "FABX_ROUTE_COVERAGE_V2",
                "FABX_MATERIAL_EDGES_V4",
            })
            process_map = next(item for item in onboarding["source_role_mappings"]
                               if item["dataset_role"] == "events")
            self.assertEqual(process_map["field_mapping"]["event_time"], "processed_timestamp")
            self.assertEqual(process_map["field_mapping"]["step_instance_id"], "step_occurrence_id")

            interval = options["default_suspected_exposure"]
            request = {
                "target_wafer_ids": options["abnormal_wafer_ids"][:10],
                "cohort_wafer_ids": options["cohort_wafer_ids"],
                "time_window": {"start": interval["start"], "end": interval["end"]},
                "suspected_exposure": interval,
            }
            status, evidence = self.request(
                "/api/reference/investigate", method="POST", payload=request,
                request_id=str(uuid.uuid4()),
            )
            self.assertEqual(status, 200, evidence)
            integration = evidence["provenance"]["mcp_integration"]
            self.assertEqual(integration["onboarding"]["proposal_sha256"], onboarding["proposal_sha256"])
            self.assertFalse(integration["permission_scope_authenticated_for_company_use"])
            reads = integration["read_operations"]
            self.assertEqual(len(reads), 7)
            self.assertTrue(all(item["query_hash"] == item["audit_query_hash"] for item in reads))
            self.assertEqual(next(item["row_count"] for item in reads if item["dataset_role"] == "events"), 404)
            self.assertEqual(next(item["row_count"] for item in reads if item["dataset_role"] == "outcomes"), 98)
            self.assertEqual(len(evidence["artifacts"][0]["journey"]["journeys"]), 98)
            exposure = evidence["artifacts"][0]["exposure_analysis"]
            self.assertEqual(exposure["coverage_evidence_level"], "CONTRADICTORY")
            self.assertEqual(len(exposure["definitely_exposed"]), 24)
            self.assertEqual(len(exposure["potentially_exposed"]), 25)
            self.assertEqual(len(exposure["unknown"]), 49)
            self.assertEqual(exposure["not_observed_exposed"], [])
            candidates = [candidate for case in evidence["counterevidence"]
                          for candidate in case["next_authorized_verification"].get("candidates", [])]
            candidate = next(item for item in candidates if item["category"] == "LOT_MEMBERSHIP_CONFLICT")
            self.assertEqual(candidate["target_wafer_ids"], ["SYN-EW-010"])

            denied_id = str(uuid.uuid4())
            status, denied = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "DENY", "candidate": candidate, "request": request},
                request_id=denied_id,
            )
            self.assertEqual(status, 200, denied)
            self.assertFalse(denied["read_executed"])
            self.assertEqual(denied["decision_audit"]["request_id"], denied_id)

            authorized_id = str(uuid.uuid4())
            status, refreshed = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "AUTHORIZE_SYNTHETIC_READ", "candidate": candidate, "request": request},
                request_id=authorized_id,
            )
            self.assertEqual(status, 200, refreshed)
            follow_up = refreshed["provenance"]["mcp_integration"]["follow_up"]
            self.assertEqual(follow_up["status"], "AUTHORIZED_SYNTHETIC_READ_COMPLETED")
            self.assertTrue(follow_up["decision_audit"]["correlation_id"])
            self.assertEqual(len(follow_up["read_operations"]), 2)
            follow_reads = {item["dataset_role"]: item for item in follow_up["read_operations"]}
            self.assertEqual(set(follow_reads["events"]["filters"]), {
                "wafer_identifier", "step_occurrence_id",
            })
            self.assertEqual(set(follow_reads["material_relationships"]["filters"]), {
                "member_wafer_identifier",
            })
            self.assertTrue(all(item["query_hash"] == item["audit_query_hash"]
                                for item in follow_up["read_operations"]))
            self.assertTrue(follow_up["refresh_interpretation"].startswith("Re-analysis uses rows returned"))
            self.assertTrue(refreshed["provenance"]["input_sha256"])
            self.assertEqual(refreshed["provenance"]["mcp_integration"]["onboarding"]["company_qualified"], False)

    def test_second_mcp_schema_variant_completes_reviewed_100_wafer_investigation(self):
        with patch.dict(os.environ, {"P2_REFERENCE_SYNTHETIC_SCENARIO": "engineer-100-alt-alias"}):
            status, options = self.request("/api/reference/options")
            self.assertEqual(status, 200, options)
            self.assertTrue(options["protocol_version"])
            self.assertEqual(len(options["cohort_wafer_ids"]), 98)
            mappings = {item["dataset_role"]: item for item in options["onboarding"]["source_role_mappings"]}
            self.assertEqual(mappings["events"]["source_id"], "PLANT7_ACTUAL_RUNS")
            self.assertEqual(mappings["events"]["field_mapping"]["wafer_id"], "substrate_tag")
            self.assertEqual(mappings["events"]["field_mapping"]["event_time"], "run_completed_utc")
            self.assertEqual(mappings["material_relationships"]["source_id"], "LOT_WAFER_LINEAGE")
            interval = options["default_suspected_exposure"]
            request = {
                "target_wafer_ids": options["abnormal_wafer_ids"][:10],
                "cohort_wafer_ids": options["cohort_wafer_ids"],
                "time_window": {"start": interval["start"], "end": interval["end"]},
                "suspected_exposure": interval,
            }
            status, evidence = self.request(
                "/api/reference/investigate", method="POST", payload=request,
                request_id=str(uuid.uuid4()),
            )
            self.assertEqual(status, 200, evidence)
            integration = evidence["provenance"]["mcp_integration"]
            self.assertEqual(len(integration["read_operations"]), 7)
            self.assertEqual(next(item["row_count"] for item in integration["read_operations"]
                                  if item["dataset_role"] == "events"), 404)
            exposure = evidence["artifacts"][0]["exposure_analysis"]
            self.assertEqual((len(exposure["definitely_exposed"]), len(exposure["potentially_exposed"]),
                              len(exposure["unknown"])), (24, 25, 49))
            candidates = [candidate for case in evidence["counterevidence"]
                          for candidate in case["next_authorized_verification"].get("candidates", [])]
            candidate = next(item for item in candidates if item["category"] == "LOT_MEMBERSHIP_CONFLICT")
            status, denied = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "DENY", "candidate": candidate, "request": request},
                request_id=str(uuid.uuid4()),
            )
            self.assertEqual(status, 200, denied)
            self.assertFalse(denied["read_executed"])
            status, refreshed = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "AUTHORIZE_SYNTHETIC_READ", "candidate": candidate, "request": request},
                request_id=str(uuid.uuid4()),
            )
        self.assertEqual(status, 200, refreshed)
        follow_up = refreshed["provenance"]["mcp_integration"]["follow_up"]
        follow_reads = {item["dataset_role"]: item for item in follow_up["read_operations"]}
        self.assertEqual(set(follow_reads["events"]["filters"]), {"substrate_tag", "run_occurrence"})
        self.assertEqual(set(follow_reads["material_relationships"]["filters"]), {"member_id"})
        self.assertTrue(all(item["query_hash"] == item["audit_query_hash"]
                            for item in follow_up["read_operations"]))
        journey = next(item for item in refreshed["transformations"][1]["journeys"]
                       if item["wafer_id"] == "SYN-EW-010")
        self.assertIn("MATERIAL_MEMBERSHIP_AMBIGUOUS", journey["history_flags"])
        self.assertEqual({item["record_id"] for item in journey["material_relationships"]}, {
            "SYN-MEM-010-A", "SYN-MEM-010-B", "SYN-MEM-010-C",
        })
        self.assertFalse(refreshed["provenance"]["mcp_integration"]["onboarding"]["company_qualified"])

    def test_13k_unseen_catalog_runs_through_standalone_host_investigation_contract(self):
        with patch.dict(os.environ, {"P2_REFERENCE_SYNTHETIC_SCENARIO": "engineer-100-alt-alias-13k"}):
            status, options = self.request("/api/reference/options")
            self.assertEqual(status, 200, options)
            self.assertEqual(len(options["cohort_wafer_ids"]), 98)
            self.assertEqual(len(options["abnormal_wafer_ids"]), 45)
            onboarding = options["onboarding"]
            self.assertTrue(options["protocol_version"])
            self.assertEqual(onboarding["decision"], "APPROVE_EXACT_PROPOSAL")
            self.assertFalse(onboarding["server_authorization_established"])
            self.assertEqual(onboarding["source_role_mappings"][0]["source_id"], "PLANT7_ACTUAL_RUNS")

            interval = options["default_suspected_exposure"]
            request = {
                "target_wafer_ids": options["abnormal_wafer_ids"][:10],
                "cohort_wafer_ids": options["cohort_wafer_ids"],
                "time_window": {"start": interval["start"], "end": interval["end"]},
                "suspected_exposure": interval,
            }
            status, evidence = self.request(
                "/api/reference/investigate", method="POST", payload=request,
                request_id=str(uuid.uuid4()),
            )
            self.assertEqual(status, 200, evidence)
            integration = evidence["provenance"]["mcp_integration"]
            self.assertEqual(integration["onboarding"]["proposal_sha256"], onboarding["proposal_sha256"])
            self.assertEqual(len(integration["read_operations"]), 7)
            self.assertTrue(all(item["query_hash"] == item["audit_query_hash"]
                                for item in integration["read_operations"]))
            self.assertEqual(len(evidence["artifacts"][0]["journey"]["journeys"]), 98)
            exposure = evidence["artifacts"][0]["exposure_analysis"]
            self.assertEqual(exposure["coverage_evidence_level"], "CONTRADICTORY")
            self.assertEqual((len(exposure["definitely_exposed"]), len(exposure["potentially_exposed"]),
                              len(exposure["unknown"])), (24, 25, 49))
            self.assertEqual(exposure["not_observed_exposed"], [])
            candidates = [candidate for case in evidence["counterevidence"]
                          for candidate in case["next_authorized_verification"].get("candidates", [])]
            self.assertTrue(any(item["category"] == "LOT_MEMBERSHIP_CONFLICT"
                                for item in candidates))
            self.assertEqual(evidence["uncertainty"]["causal_identifiability"], "NOT_ESTABLISHED")

            candidate = next(item for item in candidates if item["category"] == "LOT_MEMBERSHIP_CONFLICT")
            status, denied = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "DENY", "candidate": candidate, "request": request},
                request_id=str(uuid.uuid4()),
            )
            self.assertEqual(status, 200, denied)
            self.assertFalse(denied["read_executed"])
            status, refreshed = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "AUTHORIZE_SYNTHETIC_READ", "candidate": candidate, "request": request},
                request_id=str(uuid.uuid4()),
            )
            self.assertEqual(status, 200, refreshed)
            follow_up = refreshed["provenance"]["mcp_integration"]["follow_up"]
            self.assertEqual(follow_up["status"], "AUTHORIZED_SYNTHETIC_READ_COMPLETED")
            self.assertEqual({item["dataset_role"] for item in follow_up["read_operations"]},
                             {"events", "material_relationships"})
            self.assertTrue(all(item["query_hash"] == item["audit_query_hash"]
                                for item in follow_up["read_operations"]))
            journey = next(item for item in refreshed["transformations"][1]["journeys"]
                           if item["wafer_id"] == "SYN-EW-010")
            self.assertEqual({item["record_id"] for item in journey["material_relationships"]},
                             {"SYN-MEM-010-A", "SYN-MEM-010-B", "SYN-MEM-010-C"})
    def test_invalid_targets_fail_before_a_partial_evidence_envelope(self):
        payload = {**PAYLOAD, "target_wafer_ids": ["CALLER-INVENTED"]}
        status, result = self.request(
            "/api/reference/investigate", method="POST", payload=payload, request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 400)
        self.assertIn("target", result["error"])
        self.assertNotIn("artifacts", result)

    def test_mismatched_or_timezone_naive_exposure_scope_is_refused(self):
        mismatched = {**PAYLOAD, "suspected_exposure": {
            **PAYLOAD["suspected_exposure"], "end": "2026-11-21T07:00:00+00:00",
        }}
        status, result = self.request(
            "/api/reference/investigate", method="POST", payload=mismatched, request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 400)
        self.assertIn("exactly match", result["error"])
        self.assertNotIn("artifacts", result)

        naive = {**PAYLOAD, "time_window": {"start": "2026-11-21T03:00:00", "end": "2026-11-21T06:00:00"}}
        status, result = self.request(
            "/api/reference/investigate", method="POST", payload=naive, request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 400)
        self.assertIn("timezone", result["error"])

    def test_cancellation_aborts_mock_mcp_reads_and_allows_a_fresh_request(self):
        request_id = str(uuid.uuid4())
        payload = {**PAYLOAD, "mock_peer_delay_ms": 250}
        result_box = {}

        def investigate():
            result_box["response"] = self.request(
                "/api/reference/investigate", method="POST", payload=payload, request_id=request_id,
            )

        worker = threading.Thread(target=investigate, daemon=True)
        worker.start()
        time.sleep(0.12)
        cancel_status, cancel_result = self.request(
            "/api/cancel", method="POST", payload={"request_id": request_id},
        )
        self.assertEqual(cancel_status, 202, cancel_result)
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive(), "cancel did not return control from the active mock MCP read")
        status, cancelled = result_box["response"]
        self.assertEqual(status, 409, cancelled)
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertNotIn("artifacts", cancelled)

        status, recovery = self.request(
            "/api/reference/investigate", method="POST", payload=PAYLOAD, request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 200, recovery)
        self.assertIn("artifacts", recovery)

    def test_authorized_follow_up_can_be_cancelled_without_partial_refresh_and_retried(self):
        request = {**PAYLOAD, "target_wafer_ids": ["SYN-W1"]}
        status, initial = self.request(
            "/api/reference/investigate", method="POST", payload=request, request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 200, initial)
        candidate = next(
            item
            for investigation in initial["counterevidence"]
            for item in investigation["next_authorized_verification"]["candidates"]
            if item["category"] == "LOT_MEMBERSHIP_CONFLICT"
        )
        follow_up_id = str(uuid.uuid4())
        delayed_request = {**request, "mock_peer_delay_ms": 500}
        response_box = {}

        def follow_up():
            response_box["response"] = self.request(
                "/api/reference/follow-up", method="POST",
                payload={"decision": "AUTHORIZE_SYNTHETIC_READ", "candidate": candidate, "request": delayed_request},
                request_id=follow_up_id,
            )

        worker = threading.Thread(target=follow_up, daemon=True)
        worker.start()
        time.sleep(0.15)
        cancel_status, cancel_result = self.request(
            "/api/cancel", method="POST", payload={"request_id": follow_up_id},
        )
        self.assertEqual(cancel_status, 202, cancel_result)
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive(), "follow-up cancellation did not stop the active bounded MCP read")
        status, cancelled = response_box["response"]
        self.assertEqual(status, 409, cancelled)
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertNotIn("artifacts", cancelled)

        status, recovery = self.request(
            "/api/reference/follow-up", method="POST",
            payload={"decision": "AUTHORIZE_SYNTHETIC_READ", "candidate": candidate, "request": request},
            request_id=str(uuid.uuid4()),
        )
        self.assertEqual(status, 200, recovery)
        self.assertEqual(recovery["provenance"]["mcp_integration"]["follow_up"]["status"], "AUTHORIZED_SYNTHETIC_READ_COMPLETED")


if __name__ == "__main__":
    unittest.main()
