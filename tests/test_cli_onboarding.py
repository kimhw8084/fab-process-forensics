from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fabintel.cli import main


ROOT = Path(__file__).resolve().parents[1]
SDK_AVAILABLE = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(SDK_AVAILABLE, "Install pinned offline MCP SDK candidate to run CLI integration qualification.")
class LiveOnboardingCLITests(unittest.TestCase):
    def test_unique_proposal_flows_from_metadata_review_to_bounded_investigation(self):
        sdk_path = os.environ.get("P2_TEST_SDK_PATH")
        if not sdk_path:
            self.skipTest("P2_TEST_SDK_PATH must identify the pinned offline SDK test environment.")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"P2_TEST_SDK_PATH": sdk_path}):
            base = Path(directory)
            transport_path, proposal_path = base / "transport.json", base / "proposal.json"
            decision_path, approved_path = base / "decision.json", base / "approved.json"
            scope_path, evidence_path = base / "scope.json", base / "evidence.json"
            transport = {
                "transport": {
                    "kind": "stdio", "command": sys.executable,
                    "args": ["-m", "fabintel.synthetic_mcp_server", "--tool-prefix", "cli_",
                             "--scenario", "engineer-100-alias"],
                    "cwd": str(ROOT), "environment": {"PYTHONPATH": "P2_TEST_SDK_PATH"},
                },
                "request_timeout_seconds": 10,
                "max_response_bytes": 8388608,
            }
            transport_path.write_text(json.dumps(transport), encoding="utf-8")

            with patch.object(sys, "argv", ["fabintel", "onboard-live", "--transport", str(transport_path),
                                              "--start", "2026-11-20T00:00:00Z", "--end", "2026-11-30T00:00:00Z",
                                              "--output", str(proposal_path)]):
                self.assertEqual(main(), 0)
            proposal = json.loads(proposal_path.read_text())
            self.assertTrue(proposal["metadata_only"])
            self.assertFalse(proposal["bounded_row_reads_executed"])
            proposed_events = proposal["proposal"]["source_role_proposals"]["events"]["candidates"][0]
            self.assertEqual(proposed_events["source_id"], "FABX_PROCESS_LEDGER_V7")
            self.assertEqual(proposed_events["field_mapping"]["event_time"], "processed_timestamp")
            self.assertEqual(proposed_events["field_mapping"]["chamber_id"], "chamber_asset")

            decisions = {
                "decision": "APPROVE_EXACT_PROPOSAL",
                "proposal_sha256": proposal["proposal_sha256"],
                "descriptor_capture_sha256": proposal["descriptor_capture_sha256"],
                "reviewer_id": "synthetic-cli-reviewer",
                "time_window": {"start": "2026-11-20T00:00:00Z", "end": "2026-11-30T00:00:00Z"},
                "limits": proposal["capture"]["limits"],
                "permission_scope": "SYNTHETIC_READ",
            }
            decision_path.write_text(json.dumps(decisions), encoding="utf-8")
            with patch.object(sys, "argv", ["fabintel", "onboard-review", "--proposal", str(proposal_path),
                                              "--decisions", str(decision_path), "--output", str(approved_path)]):
                self.assertEqual(main(), 0)
            approved = json.loads(approved_path.read_text())
            self.assertFalse(approved["server_authorization_established"])
            self.assertEqual(approved["review"]["decision"], "APPROVE_EXACT_PROPOSAL")

            # The target and cohort are fixture identities, provided as a separate bounded scope.
            scope_path.write_text(json.dumps({
                "target_wafer_ids": ["SYN-EW-000"],
                "cohort_wafer_ids": [f"SYN-EW-{index:03d}" for index in range(98)],
                "suspected_exposure": {"chamber_id": "SYN-C1", "start": "2026-11-21T01:25:00Z",
                                       "end": "2026-11-21T01:35:00Z"},
            }), encoding="utf-8")
            with patch.object(sys, "argv", ["fabintel", "investigate-mcp", "--proposal", str(proposal_path),
                                              "--approved-config", str(approved_path), "--transport", str(transport_path),
                                              "--scope", str(scope_path), "--output", str(evidence_path)]):
                self.assertEqual(main(), 0)
            evidence = json.loads(evidence_path.read_text())
            reads = evidence["provenance"]["mcp_integration"]["read_operations"]
            self.assertEqual({item["dataset_role"] for item in reads}, {
                "events", "outcomes", "coverage", "history_coverage", "route_definitions",
                "route_coverage", "material_relationships",
            })
            self.assertEqual(next(item["row_count"] for item in reads if item["dataset_role"] == "events"), 404)
            self.assertEqual(next(item["row_count"] for item in reads if item["dataset_role"] == "outcomes"), 98)
            self.assertTrue(all(item["query_hash"] == item["audit_query_hash"] for item in reads))
            self.assertFalse(evidence["provenance"]["mcp_integration"]["permission_scope_authenticated_for_company_use"])
            self.assertEqual({source for read in reads for source in read["source_ids"]}, {
                "FABX_PROCESS_LEDGER_V7", "FABX_WAFER_RESULTS_V2", "FABX_EXPOSURE_COVERAGE_V1",
                "FABX_HISTORY_COVERAGE_V3", "FABX_ROUTE_CATALOG_V5", "FABX_ROUTE_COVERAGE_V2",
                "FABX_MATERIAL_EDGES_V4",
            })
            journey = next(item for item in evidence["transformations"]
                           if item["id"] == "p2-journey-and-route-variants-v1")
            self.assertEqual(len(journey["journeys"]), 98)
            self.assertTrue(any(item["rework_edges"] for item in journey["journeys"]))
            exposure = next(item["exposure"] for item in evidence["transformations"]
                            if item["id"] == "p2-exposure-evidence-v1")
            self.assertEqual((len(exposure["definitely_exposed"]), len(exposure["potentially_exposed"]),
                              len(exposure["unknown"]), len(exposure["verified_unexposed"])), (24, 25, 49, 0))
            event_mapping = next(item for item in evidence["provenance"]["mcp_integration"]["reviewed_field_mappings"]
                                 if item["dataset_role"] == "events")
            self.assertEqual(event_mapping["field_mapping"]["event_time"], "processed_timestamp")
            event_relation = next(item for item in evidence["artifacts"][0]["source_relationships"]
                                  if item["id"] == "FABX_REL_PROCESS_STEP")
            self.assertIn("processed_timestamp", event_relation["source_declared_keys"])
            self.assertIn("timestamp", event_relation["keys"])
            self.assertEqual(event_relation["field_aliases"]["processed_timestamp"], "timestamp")
            self.assertEqual(evidence["counterevidence"][0]["causal_conclusion"]["status"], "NOT_ESTABLISHED")

    def test_second_schema_variant_completes_cli_discovery_review_and_investigation(self):
        sdk_path = os.environ.get("P2_TEST_SDK_PATH")
        if not sdk_path:
            self.skipTest("P2_TEST_SDK_PATH must identify the pinned offline SDK test environment.")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"P2_TEST_SDK_PATH": sdk_path}):
            base = Path(directory)
            transport_path, proposal_path = base / "transport.json", base / "proposal.json"
            decision_path, approved_path = base / "decision.json", base / "approved.json"
            scope_path, evidence_path = base / "scope.json", base / "evidence.json"
            transport = {
                "transport": {
                    "kind": "stdio", "command": sys.executable,
                    "args": ["-m", "fabintel.synthetic_mcp_server", "--tool-prefix", "cli_alt__",
                             "--scenario", "engineer-100-alt-alias"],
                    "cwd": str(ROOT), "environment": {"PYTHONPATH": "P2_TEST_SDK_PATH"},
                },
                "request_timeout_seconds": 10,
                "max_response_bytes": 8388608,
            }
            transport_path.write_text(json.dumps(transport), encoding="utf-8")
            with patch.object(sys, "argv", ["fabintel", "onboard-live", "--transport", str(transport_path),
                                              "--start", "2026-11-20T00:00:00Z", "--end", "2026-11-30T00:00:00Z",
                                              "--output", str(proposal_path)]):
                self.assertEqual(main(), 0)
            proposal = json.loads(proposal_path.read_text())
            self.assertFalse(proposal["bounded_row_reads_executed"])
            candidate = proposal["proposal"]["source_role_proposals"]["events"]["candidates"][0]
            self.assertEqual(candidate["source_id"], "PLANT7_ACTUAL_RUNS")
            self.assertEqual(candidate["field_mapping"]["event_time"], "run_completed_utc")

            decisions = {
                "decision": "APPROVE_EXACT_PROPOSAL", "proposal_sha256": proposal["proposal_sha256"],
                "descriptor_capture_sha256": proposal["descriptor_capture_sha256"],
                "reviewer_id": "synthetic-alt-cli-reviewer",
                "time_window": {"start": "2026-11-20T00:00:00Z", "end": "2026-11-30T00:00:00Z"},
                "limits": proposal["capture"]["limits"], "permission_scope": "SYNTHETIC_READ",
            }
            decision_path.write_text(json.dumps(decisions), encoding="utf-8")
            with patch.object(sys, "argv", ["fabintel", "onboard-review", "--proposal", str(proposal_path),
                                              "--decisions", str(decision_path), "--output", str(approved_path)]):
                self.assertEqual(main(), 0)
            approved = json.loads(approved_path.read_text())
            self.assertFalse(approved["server_authorization_established"])
            self.assertEqual(approved["mcp_tools"]["read_bounded"], "cli_alt__read_bounded")

            scope_path.write_text(json.dumps({
                "target_wafer_ids": ["SYN-EW-000"],
                "cohort_wafer_ids": [f"SYN-EW-{index:03d}" for index in range(98)],
                "suspected_exposure": {"chamber_id": "SYN-C1", "start": "2026-11-21T01:25:00Z",
                                       "end": "2026-11-21T01:35:00Z"},
            }), encoding="utf-8")
            with patch.object(sys, "argv", ["fabintel", "investigate-mcp", "--proposal", str(proposal_path),
                                              "--approved-config", str(approved_path), "--transport", str(transport_path),
                                              "--scope", str(scope_path), "--output", str(evidence_path)]):
                self.assertEqual(main(), 0)
            evidence = json.loads(evidence_path.read_text())
            reads = evidence["provenance"]["mcp_integration"]["read_operations"]
            self.assertEqual(len(reads), 7)
            self.assertEqual({source for read in reads for source in read["source_ids"]}, {
                "PLANT7_ACTUAL_RUNS", "QDATA_WAFER_RESULTS", "TRACE_EXPOSURE_COVERAGE",
                "TRACE_HISTORY_COVERAGE", "ROUTE_BOOK_V6", "TRACE_ROUTE_COVERAGE", "LOT_WAFER_LINEAGE",
            })
            self.assertTrue(all(read["query_hash"] == read["audit_query_hash"] for read in reads))
            self.assertFalse(evidence["provenance"]["mcp_integration"]["permission_scope_authenticated_for_company_use"])
            self.assertEqual(evidence["counterevidence"][0]["causal_conclusion"]["status"], "NOT_ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
