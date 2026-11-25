from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

from fabintel.onboarding import propose_mappings
from fabintel.onboarding_pipeline import (
    materialize_live_review, propose_from_live_mcp_metadata, verify_materialized_config,
)
from fabintel.mcp_adapter import ConfiguredMCPAdapter
from fabintel.mcp_workflow import investigate_with_mcp


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "qualification/fixtures/onboarding_descriptor_capture_synthetic_v1.json"
SDK_AVAILABLE = importlib.util.find_spec("mcp") is not None
ROLES = ("events", "outcomes", "coverage", "history_coverage", "route_definitions",
         "route_coverage", "material_relationships")
OPS = ("discover", "semantics", "relationships", "read_bounded", "cancel", "audit")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _capture_hash(capture: dict) -> str:
    return _hash(json.dumps(capture, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _compatible(candidate):
    return candidate.get("candidate_state") in {
        "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED", "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED",
    }


class AdversarialDescriptorEnvironments(unittest.TestCase):
    """Expected classifications are fixed from descriptor facts, not mapper output."""

    def setUp(self):
        self.capture = json.loads(CAPTURE.read_text())

    def test_record_ingestion_time_cannot_substitute_for_process_event_time(self):
        source = next(item for item in self.capture["sources"] if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        source["column_definitions"]["processed_at"]["meaning"] = "record ingestion time"
        report = propose_mappings(self.capture)
        role = report["source_role_proposals"]["events"]
        self.assertEqual(role["candidate_state"], "NO_STRUCTURALLY_COMPATIBLE_SOURCE")
        decoy = next(item for item in role["candidates"] if item["source_id"] == source["source_id"])
        self.assertIn("event_time", decoy["missing_required_fields"])
        self.assertEqual(decoy["diagnostics"][0]["code"], "EVENT_TIME_NOT_ESTABLISHED")

    def test_equipment_group_does_not_become_exact_chamber_identity(self):
        source = next(item for item in self.capture["sources"] if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        source["column_definitions"].pop("chamber_asset")
        source["column_definitions"].pop("tool_asset")
        source["column_definitions"]["equipment_group"] = {"type": "identifier", "entity": "equipment_group"}
        relation = next(item for item in self.capture["relationships"] if item["source_ids"] == [source["source_id"]])
        relation["keys"] = [key for key in relation["keys"] if key not in {"chamber_asset", "tool_asset"}]
        relation["source_reference"]["source_hash"] = source["source_hash"]
        report = propose_mappings(self.capture)
        candidates = report["source_role_proposals"]["events"]["candidates"]
        candidate = next(item for item in candidates if item.get("source_id") == source["source_id"])
        self.assertEqual(candidate["candidate_state"], "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED")
        self.assertIsNone(candidate["field_mapping"]["chamber_id"])
        self.assertIn("chamber_id", candidate["missing_optional_fields"])
        self.assertEqual(candidate["diagnostics"][0]["code"], "EXACT_CHAMBER_NOT_ESTABLISHED")

    def test_static_membership_does_not_support_historical_membership(self):
        source = next(item for item in self.capture["sources"] if item["record_kind"] == "MATERIAL_RELATIONSHIP")
        for field in ("valid_from", "valid_to"):
            source["column_definitions"].pop(field)
        relation = next(item for item in self.capture["relationships"] if item["source_ids"] == [source["source_id"]])
        relation["keys"] = [key for key in relation["keys"] if key not in {"valid_from", "valid_to"}]
        report = propose_mappings(self.capture)
        role = report["source_role_proposals"]["material_relationships"]
        self.assertEqual(role["candidate_state"], "NO_STRUCTURALLY_COMPATIBLE_SOURCE")
        source_candidate = next(item for item in role["candidates"] if item.get("source_id") == source["source_id"])
        self.assertTrue(any(item["code"] == "TIME_SCOPED_MEMBERSHIP_NOT_ESTABLISHED"
                            for item in source_candidate["diagnostics"]))

    def test_two_versioned_compatible_sources_remain_ambiguous(self):
        source = next(item for item in self.capture["sources"] if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        relation = next(item for item in self.capture["relationships"] if item["source_ids"] == [source["source_id"]])
        duplicate = copy.deepcopy(source)
        duplicate["source_id"] = "OLDER_VERSION_EVENT_SOURCE"
        duplicate["semantic_version"] = "site-sem-2025.1"
        duplicate["source_hash"] = _hash("older-event-source")
        self.capture["sources"].append(duplicate)
        duplicate_relation = copy.deepcopy(relation)
        duplicate_relation["id"] = "OLDER_VERSION_EVENT_REL"
        duplicate_relation["source_ids"] = [duplicate["source_id"]]
        duplicate_relation["source_reference"] = {
            "source_ids": [duplicate["source_id"]], "source_hash": duplicate["source_hash"],
            "semantic_version": duplicate["semantic_version"],
        }
        self.capture["relationships"].append(duplicate_relation)
        report = propose_mappings(self.capture)
        role = report["source_role_proposals"]["events"]
        self.assertEqual(role["candidate_state"], "AMBIGUOUS")
        self.assertEqual(role["ranked_candidate_source_ids"][0], "OLDER_VERSION_EVENT_SOURCE")
        self.assertTrue(all(item["requires_authorized_review"] for item in role["candidates"]))

    def test_combined_untyped_history_and_misleading_name_abstain(self):
        source = next(item for item in self.capture["sources"] if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        source["source_id"] = "SUPER_COMPLETE_MANUFACTURING_EVENTS_AND_OUTCOMES"
        source["record_kind"] = "PROCESS_AND_OUTCOME"
        relation = next(item for item in self.capture["relationships"] if item["source_ids"] == ["SITE_EVENTS_ALIAS"])
        relation["source_ids"] = [source["source_id"]]
        relation["source_reference"]["source_ids"] = [source["source_id"]]
        relation["source_reference"]["source_hash"] = source["source_hash"]
        report = propose_mappings(self.capture)
        self.assertEqual(report["source_role_proposals"]["events"]["candidate_state"], "NO_STRUCTURALLY_COMPATIBLE_SOURCE")
        outcome_ids = {item.get("source_id") for item in report["source_role_proposals"]["outcomes"]["candidates"]}
        self.assertNotIn("SUPER_COMPLETE_MANUFACTURING_EVENTS_AND_OUTCOMES", outcome_ids)
        self.assertEqual(report["source_role_proposals"]["outcomes"]["candidate_state"], "UNIQUE_REVIEW_REQUIRED")

    def test_split_merge_relationship_is_not_misread_as_wafer_membership(self):
        source = next(item for item in self.capture["sources"] if item["record_kind"] == "MATERIAL_RELATIONSHIP")
        relation = next(item for item in self.capture["relationships"] if item["source_ids"] == [source["source_id"]])
        relation["relationship_type"] = "LOT_SPLIT"
        report = propose_mappings(self.capture)
        role = report["source_role_proposals"]["material_relationships"]
        self.assertEqual(role["candidate_state"], "NO_STRUCTURALLY_COMPATIBLE_SOURCE")
        candidate = next(item for item in role["candidates"] if item.get("source_id") == source["source_id"])
        self.assertTrue(any(item["code"] == "MATERIAL_LINEAGE_RELATIONSHIP_UNMAPPED"
                            for item in candidate["diagnostics"]))


class ReviewedPlanBoundaryTests(unittest.TestCase):
    def test_digest_bound_exact_proposal_review_reduces_manual_selection_fields(self):
        capture = json.loads(CAPTURE.read_text())
        event_source = next(item for item in capture["sources"]
                            if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        event_source["column_definitions"]["operation_instance"]["meaning"] = "actual operation instance"
        event_source["column_definitions"].update({
            "recorded_at": {"type": "timestamp", "timezone_required": True,
                             "meaning": "record ingestion time", "nullable": True},
            "time_uncertainty_seconds": {"type": "number", "meaning": "event-time uncertainty in seconds",
                                         "nullable": True},
            "rework_of_step_instance_id": {"type": "identifier", "entity": "process_step_instance",
                                            "meaning": "prior step instance", "nullable": True},
            "route_id": {"type": "identifier", "entity": "route", "nullable": True},
            "route_version": {"type": "identifier", "entity": "route_version", "nullable": True},
        })
        event_relationship = next(item for item in capture["relationships"]
                                  if item["source_ids"] == [event_source["source_id"]])
        event_relationship["keys"].extend([
            "recorded_at", "time_uncertainty_seconds", "rework_of_step_instance_id",
            "route_id", "route_version",
        ])
        event_source["source_hash"] = _hash("complete-event-role-descriptor")
        event_relationship["source_reference"]["source_hash"] = event_source["source_hash"]
        proposal = propose_mappings(capture)
        proposal_hash = _hash(json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        capture_hash = _capture_hash(capture)
        report = {"schema_version": "p2-live-onboarding-proposal/v1", "metadata_only": True,
                  "bounded_row_reads_executed": False, "capture": capture, "proposal": proposal,
                  "proposal_sha256": proposal_hash, "descriptor_capture_sha256": capture_hash}
        config = materialize_live_review(report, {
            "decision": "APPROVE_EXACT_PROPOSAL", "proposal_sha256": proposal_hash,
            "descriptor_capture_sha256": capture_hash,
            "reviewer_id": "synthetic-batch-reviewer",
            "time_window": {"start": "2026-11-21T00:00:00Z", "end": "2026-11-22T00:00:00Z"},
            "limits": {"max_rows": 50, "max_bytes": 16000, "max_seconds": 4},
            "permission_scope": "SYNTHETIC_READ",
        })
        verify_materialized_config(config, proposal)
        self.assertEqual(config["review"]["decision"], "APPROVE_EXACT_PROPOSAL")
        self.assertEqual(len(config["reviewed_decisions"]["selected_tools"]), len(OPS))
        self.assertEqual(len(config["reviewed_decisions"]["selected_sources"]), len(ROLES))
        self.assertFalse(config["server_authorization_established"])

    def test_exact_proposal_approval_abstains_on_ambiguous_source_role(self):
        capture = json.loads(CAPTURE.read_text())
        source = next(item for item in capture["sources"] if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        relation = next(item for item in capture["relationships"] if item["source_ids"] == [source["source_id"]])
        duplicate = copy.deepcopy(source)
        duplicate["source_id"] = "SECOND_COMPATIBLE_EVENT_SOURCE"
        duplicate["source_hash"] = _hash("second-compatible-source")
        capture["sources"].append(duplicate)
        duplicate_relation = copy.deepcopy(relation)
        duplicate_relation["id"] = "SECOND_COMPATIBLE_EVENT_REL"
        duplicate_relation["source_ids"] = [duplicate["source_id"]]
        duplicate_relation["source_reference"] = {
            "source_ids": [duplicate["source_id"]], "source_hash": duplicate["source_hash"],
            "semantic_version": duplicate["semantic_version"],
        }
        capture["relationships"].append(duplicate_relation)
        proposal = propose_mappings(capture)
        proposal_hash = _hash(json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        capture_hash = _capture_hash(capture)
        report = {"schema_version": "p2-live-onboarding-proposal/v1", "metadata_only": True,
                  "bounded_row_reads_executed": False, "capture": capture, "proposal": proposal,
                  "proposal_sha256": proposal_hash, "descriptor_capture_sha256": capture_hash}
        with self.assertRaisesRegex(ValueError, "one reviewed-compatible source for events"):
            materialize_live_review(report, {
                "decision": "APPROVE_EXACT_PROPOSAL", "proposal_sha256": proposal_hash,
                "descriptor_capture_sha256": capture_hash,
                "reviewer_id": "synthetic-batch-reviewer",
                "time_window": {"start": "2026-11-21T00:00:00Z", "end": "2026-11-22T00:00:00Z"},
                "limits": {"max_rows": 50, "max_bytes": 16000, "max_seconds": 4},
                "permission_scope": "SYNTHETIC_READ",
            })

    def test_exact_proposal_cannot_silently_acknowledge_partial_source_role(self):
        capture = json.loads(CAPTURE.read_text())
        source = next(item for item in capture["sources"]
                      if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        relation = next(item for item in capture["relationships"]
                        if item["source_ids"] == [source["source_id"]])
        source["column_definitions"].pop("tool_asset")
        source["column_definitions"].pop("chamber_asset")
        source["source_hash"] = _hash("partial-source-requires-human-acknowledgement")
        relation["source_reference"]["source_hash"] = source["source_hash"]
        proposal = propose_mappings(capture)
        proposal_hash = _hash(json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        capture_hash = _capture_hash(capture)
        report = {"schema_version": "p2-live-onboarding-proposal/v1", "metadata_only": True,
                  "bounded_row_reads_executed": False, "capture": capture, "proposal": proposal,
                  "proposal_sha256": proposal_hash, "descriptor_capture_sha256": capture_hash}
        base_decision = {
            "reviewer_id": "synthetic-reviewer-partial-source",
            "proposal_sha256": proposal_hash,
            "descriptor_capture_sha256": capture_hash,
            "time_window": {"start": "2026-11-21T00:00:00Z", "end": "2026-11-22T00:00:00Z"},
            "limits": capture["limits"], "permission_scope": "SYNTHETIC_READ",
        }
        with self.assertRaisesRegex(ValueError, "cannot acknowledge partial source role events"):
            materialize_live_review(report, {**base_decision, "decision": "APPROVE_EXACT_PROPOSAL"})

        selected_sources = {}
        for role in ROLES:
            candidate = next(item for item in proposal["source_role_proposals"][role]["candidates"]
                             if _compatible(item))
            selected_sources[role] = {
                "source_id": candidate["source_id"],
                "relationship_id": candidate["relationship_id"],
                "acknowledge_missing_optional": candidate.get("missing_optional_fields", []),
            }
        selected_tools = {
            operation: proposal["operation_proposals"][operation]["candidate_tool_names"][0]
            for operation in OPS
        }
        explicit = materialize_live_review(report, {
            **base_decision, "decision": "APPROVE", "selected_sources": selected_sources,
            "selected_tools": selected_tools,
        })
        verify_materialized_config(explicit, proposal)
        event_plan = next(item for item in explicit["approved_plan"]["read_plans"]
                          if item["dataset_role"] == "events")
        self.assertTrue({"tool_id", "chamber_id"}.issubset(set(event_plan["missing_optional_fields"])))
        self.assertEqual(set(explicit["reviewed_decisions"]["selected_sources"]["events"][
            "acknowledge_missing_optional"]), set(event_plan["missing_optional_fields"]))
        self.assertFalse(explicit["server_authorization_established"])

    def test_review_rejects_descriptor_capture_changes_before_materialization(self):
        capture = json.loads(CAPTURE.read_text())
        proposal = propose_mappings(capture)
        proposal_hash = _hash(json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        capture_hash = _capture_hash(capture)
        report = {"schema_version": "p2-live-onboarding-proposal/v1", "metadata_only": True,
                  "bounded_row_reads_executed": False, "capture": capture, "proposal": proposal,
                  "proposal_sha256": proposal_hash, "descriptor_capture_sha256": capture_hash}
        decision = {
            "decision": "APPROVE_EXACT_PROPOSAL", "proposal_sha256": proposal_hash,
            "descriptor_capture_sha256": capture_hash, "reviewer_id": "synthetic-reviewer-capture-pin",
            "time_window": {"start": "2026-11-21T00:00:00Z", "end": "2026-11-22T00:00:00Z"},
            "limits": capture["limits"], "permission_scope": "SYNTHETIC_READ",
        }
        stale_capture = copy.deepcopy(capture)
        event_source = next(item for item in stale_capture["sources"]
                            if item["record_kind"] == "PROCESS_STEP_INSTANCE")
        event_source["column_definitions"]["processed_at"]["meaning"] = "record ingestion time"
        with self.assertRaisesRegex(ValueError, "Descriptor capture changed after the mapping proposal"):
            materialize_live_review({**report, "capture": stale_capture}, decision)

        rehashed_capture = _capture_hash(stale_capture)
        changed_report = {**report, "capture": stale_capture,
                          "descriptor_capture_sha256": rehashed_capture}
        with self.assertRaisesRegex(ValueError, "Mapping proposal no longer matches its descriptor capture"):
            materialize_live_review(changed_report, {
                **decision, "descriptor_capture_sha256": rehashed_capture,
            })

    def test_explicit_review_materializes_pinned_plan_and_detects_mutation(self):
        capture = json.loads(CAPTURE.read_text())
        proposal = propose_mappings(capture)
        capture_hash = _capture_hash(capture)
        proposal_hash = _hash(json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        report = {"schema_version": "p2-live-onboarding-proposal/v1", "metadata_only": True,
                  "bounded_row_reads_executed": False, "capture": capture, "proposal": proposal,
                  "proposal_sha256": proposal_hash, "descriptor_capture_sha256": capture_hash}
        selected_sources = {}
        for role in ROLES:
            candidate = next(item for item in proposal["source_role_proposals"][role]["candidates"]
                             if _compatible(item))
            selected_sources[role] = {
                "source_id": candidate["source_id"], "relationship_id": candidate["relationship_id"],
                "acknowledge_missing_optional": candidate.get("missing_optional_fields", []),
            }
        selected_tools = {op: proposal["operation_proposals"][op]["candidate_tool_names"][0] for op in OPS}
        decisions = {
            "decision": "APPROVE", "reviewer_id": "synthetic-reviewer-1",
            "descriptor_capture_sha256": capture_hash,
            "selected_tools": selected_tools, "selected_sources": selected_sources,
            "time_window": {"start": "2026-11-21T00:00:00Z", "end": "2026-11-22T00:00:00Z"},
            "limits": {"max_rows": 50, "max_bytes": 16000, "max_seconds": 4},
            "permission_scope": "SYNTHETIC_READ",
        }
        config = materialize_live_review(report, decisions)
        verify_materialized_config(config, proposal)
        self.assertFalse(config["server_authorization_established"])
        self.assertFalse(config["company_qualified"])
        self.assertEqual(len(config["approved_plan"]["read_plans"]), 7)
        stale = copy.deepcopy(config)
        stale["approved_plan"]["read_plans"][0]["source_ids"] = ["DIFFERENT_SOURCE"]
        with self.assertRaisesRegex(ValueError, "changed after review"):
            verify_materialized_config(stale, proposal)

    def test_discovery_or_mapping_cannot_be_materialized_without_explicit_approval(self):
        with self.assertRaisesRegex(ValueError, "explicitly set decision=APPROVE"):
            materialize_live_review({"schema_version": "p2-live-onboarding-proposal/v1",
                                     "metadata_only": True, "bounded_row_reads_executed": False,
                                     "capture": {}, "proposal": {}}, {"decision": "PROPOSE"})


@unittest.skipUnless(SDK_AVAILABLE, "Install pinned offline MCP SDK candidate to run SDK discovery qualification.")
class LiveSyntheticDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_sdk_discovers_metadata_without_executing_rows(self):
        sdk_path = os.environ.get("P2_TEST_SDK_PATH")
        if not sdk_path:
            self.skipTest("P2_TEST_SDK_PATH must identify the pinned offline SDK test environment.")
        transport = {
            "kind": "stdio", "command": sys.executable,
            "args": ["-m", "fabintel.synthetic_mcp_server", "--tool-prefix", "onboard_"],
            "cwd": str(ROOT),
            "environment": {"PYTHONPATH": "P2_TEST_SDK_PATH"},
        }
        report = await propose_from_live_mcp_metadata(
            transport, time_window={"start": "2026-11-21T00:00:00Z", "end": "2026-11-22T00:00:00Z"},
            environment={"P2_TEST_SDK_PATH": sdk_path},
        )
        self.assertTrue(report["metadata_only"])
        self.assertFalse(report["bounded_row_reads_executed"])
        self.assertEqual(report["proposal"]["operation_proposals"]["read_bounded"]["candidate_tool_names"],
                         ["onboard_read_bounded"])
        self.assertEqual(report["proposal"]["source_role_proposals"]["events"]["candidate_state"],
                         "UNIQUE_REVIEW_REQUIRED")
        self.assertEqual(report["capture"]["capture_mode"], "LIVE_MCP_METADATA_ONLY_UNVERIFIED_ORIGIN")

    async def test_official_sdk_batches_13008_source_catalog_without_mapping_decoys(self):
        sdk_path = os.environ.get("P2_TEST_SDK_PATH")
        if not sdk_path:
            self.skipTest("P2_TEST_SDK_PATH must identify the pinned offline SDK test environment.")
        transport = {
            "kind": "stdio", "command": sys.executable,
            "args": ["-m", "fabintel.synthetic_mcp_server", "--tool-prefix", "catalog13k__",
                     "--scenario", "engineer-100-alt-alias-13k"],
            "cwd": str(ROOT), "environment": {"PYTHONPATH": "P2_TEST_SDK_PATH"},
        }
        report = await propose_from_live_mcp_metadata(
            transport, time_window={"start": "2026-11-20T00:00:00Z", "end": "2026-11-30T00:00:00Z"},
            max_response_bytes=8 * 1024 * 1024,
            environment={"P2_TEST_SDK_PATH": sdk_path},
        )
        capture, proposal = report["capture"], report["proposal"]
        self.assertEqual(capture["metadata_source_count"], 13008)
        self.assertEqual(capture["metadata_semantics_batch_size"], 64)
        self.assertEqual(capture["metadata_semantics_batch_count"], 204)
        self.assertEqual(capture["metadata_relationship_source_count"], 7)
        self.assertEqual(len(capture["sources"]), 13008)
        self.assertEqual(len(capture["relationships"]), 7)
        self.assertTrue(report["metadata_only"])
        self.assertFalse(report["bounded_row_reads_executed"])
        self.assertEqual(report["mcp_protocol_version"], capture["protocol_version"])
        timings = report["performance_metrics"]
        self.assertIn("source_semantics_ms", timings)
        self.assertIn("metadata_capture_total_ms", timings)
        self.assertIn("source_mapping_ms", timings)
        self.assertTrue(all(isinstance(timings[key], (int, float)) and timings[key] >= 0
                            for key in ("tool_descriptor_inspection_ms", "mcp_discover_ms",
                                        "source_semantics_ms", "source_relationships_ms",
                                        "metadata_capture_total_ms", "source_mapping_ms")))

        expected_sources = {
            "events": "PLANT7_ACTUAL_RUNS",
            "outcomes": "QDATA_WAFER_RESULTS",
            "coverage": "TRACE_EXPOSURE_COVERAGE",
            "history_coverage": "TRACE_HISTORY_COVERAGE",
            "route_definitions": "ROUTE_BOOK_V6",
            "route_coverage": "TRACE_ROUTE_COVERAGE",
            "material_relationships": "LOT_WAFER_LINEAGE",
        }
        for role, source_id in expected_sources.items():
            role_proposal = proposal["source_role_proposals"][role]
            self.assertEqual(role_proposal["candidate_state"], "UNIQUE_REVIEW_REQUIRED", role)
            self.assertEqual(role_proposal["preferred_candidate_source_id"], source_id, role)
            self.assertEqual(role_proposal["ranked_candidate_source_ids"], [source_id], role)
        self.assertFalse(any(source["record_kind"] != "UNCLASSIFIED" for source in capture["sources"]
                             if source["source_id"].startswith("OPAQUE_CATALOG_ENTRY_")))

        window = {"start": "2026-11-20T00:00:00Z", "end": "2026-11-30T00:00:00Z"}
        capture_hash = _capture_hash(capture)
        reviewed = materialize_live_review(report, {
            "decision": "APPROVE_EXACT_PROPOSAL", "reviewer_id": "synthetic-13k-reviewer",
            "proposal_sha256": report["proposal_sha256"], "time_window": window,
            "descriptor_capture_sha256": capture_hash,
            "limits": capture["limits"], "permission_scope": "SYNTHETIC_READ",
        })
        verify_materialized_config(reviewed, proposal)
        selected = reviewed["reviewed_decisions"]["selected_sources"]
        source_refs = [{"source_id": item["source_id"], "entity_type": "source",
                        "entity_id": item["source_id"]} for item in selected.values()]
        client_config = {
            "schema_version": "p2-mcp-client-config/v1", "transport": transport,
            "tools": reviewed["mcp_tools"], "request_timeout_seconds": 10,
            "max_response_bytes": 8 * 1024 * 1024,
        }
        async with ConfiguredMCPAdapter(
                client_config, environment={"P2_TEST_SDK_PATH": sdk_path}) as adapter:
            evidence = await investigate_with_mcp(
                adapter, reviewed["approved_plan"], reviewed["permission_scope"],
                reviewed["limits"], source_refs,
                suspected_exposure={
                    "chamber_id": "SYN-C1", "start": "2026-11-21T01:25:00Z",
                    "end": "2026-11-21T01:35:00Z", "condition_type": "MAINTENANCE",
                },
            )
        self.assertNotEqual(evidence["status"], "REFUSED")
        self.assertEqual(evidence["uncertainty"]["causal_identifiability"], "NOT_ESTABLISHED")
        self.assertEqual(len(evidence["provenance"]["mcp_integration"]["read_operations"]), 7)
        operations = evidence["provenance"]["mcp_integration"]["read_operations"]
        self.assertTrue(all(item["query_hash"] == item["audit_query_hash"] for item in operations))
        self.assertEqual(next(item["row_count"] for item in operations if item["dataset_role"] == "events"), 404)
        self.assertEqual(len(evidence["transformations"][1]["journeys"]), 98)
        self.assertTrue(evidence["transformations"][1]["route_variants"])
        exposure = evidence["transformations"][2]["exposure"]
        self.assertIsNotNone(exposure)
        self.assertEqual(exposure["condition_context"]["evidence_status"],
                         "CALLER_SUPPLIED_UNVERIFIED")
        self.assertEqual(exposure["coverage_evidence_level"], "CONTRADICTORY")
        self.assertEqual((len(exposure["definitely_exposed"]), len(exposure["potentially_exposed"]),
                          len(exposure["unknown"])), (24, 25, 49))
        self.assertEqual(exposure["not_observed_exposed"], [])
        self.assertIn("counterevidence", evidence)
        next_check = evidence["counterevidence"][0]["next_authorized_verification"]
        self.assertTrue(next_check["proposed_not_executed"])
        self.assertTrue(any(item["category"] == "LOT_MEMBERSHIP_CONFLICT"
                            for item in next_check["candidates"]))
        self.assertFalse(evidence["provenance"]["mcp_integration"]["permission_scope_authenticated_for_company_use"])

    async def test_reviewed_config_runs_six_source_mcp_to_evidence_pipeline(self):
        sdk_path = os.environ.get("P2_TEST_SDK_PATH")
        if not sdk_path:
            self.skipTest("P2_TEST_SDK_PATH must identify the pinned offline SDK test environment.")
        transport = {
            "kind": "stdio", "command": sys.executable,
            "args": ["-m", "fabintel.synthetic_mcp_server", "--tool-prefix", "onboard_",
                     "--scenario", "engineer-100"],
            "cwd": str(ROOT), "environment": {"PYTHONPATH": "P2_TEST_SDK_PATH"},
        }
        window = {"start": "2026-11-20T00:00:00Z", "end": "2026-11-30T00:00:00Z"}
        report = await propose_from_live_mcp_metadata(
            transport, time_window=window, environment={"P2_TEST_SDK_PATH": sdk_path},
        )
        proposal = report["proposal"]
        decisions = {
            "decision": "APPROVE_EXACT_PROPOSAL", "reviewer_id": "synthetic-explicit-review",
            "proposal_sha256": report["proposal_sha256"], "time_window": window,
            "descriptor_capture_sha256": _capture_hash(report["capture"]),
            "limits": report["capture"]["limits"],
            "permission_scope": "SYNTHETIC_READ",
        }
        approved = materialize_live_review(report, decisions)
        verify_materialized_config(approved, proposal)
        chosen = approved["reviewed_decisions"]["selected_sources"]
        config = {
            "schema_version": "p2-mcp-client-config/v1", "transport": transport,
            "tools": approved["mcp_tools"], "request_timeout_seconds": 10,
            "max_response_bytes": 8388608,
        }
        refs = [{"source_id": selected["source_id"], "entity_type": "source",
                 "entity_id": selected["source_id"]} for selected in chosen.values()]
        async with ConfiguredMCPAdapter(config, environment={"P2_TEST_SDK_PATH": sdk_path}) as adapter:
            evidence = await investigate_with_mcp(
                adapter, approved["approved_plan"], approved["permission_scope"],
                approved["limits"], refs,
            )
        self.assertNotEqual(evidence.get("status"), "REFUSED", json.dumps(evidence, sort_keys=True)[:5000])
        self.assertIn("provenance", evidence)
        read_records = evidence["provenance"]["mcp_integration"]["read_operations"]
        self.assertEqual({item["dataset_role"] for item in read_records}, set(ROLES))
        self.assertTrue(all(item["query_hash"] == item["audit_query_hash"] for item in read_records))
        self.assertEqual(next(item["row_count"] for item in read_records if item["dataset_role"] == "events"), 404)
        self.assertEqual(next(item["row_count"] for item in read_records if item["dataset_role"] == "outcomes"), 98)
        self.assertFalse(evidence["provenance"]["mcp_integration"]["permission_scope_authenticated_for_company_use"])


if __name__ == "__main__":
    unittest.main()
