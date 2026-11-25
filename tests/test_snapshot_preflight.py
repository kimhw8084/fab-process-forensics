"""Local snapshot preflight validates provenance and limits without analysis."""
import copy
import json
from pathlib import Path
import unittest

from fabintel.project import MAX_OUTCOMES, analyze, snapshot_preflight


ROOT = Path(__file__).resolve().parent.parent


class SnapshotPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads((ROOT / "fixtures" / "case_positive.json").read_text(encoding="utf8"))

    def test_valid_snapshot_lists_sources_relationship_usage_and_scope(self):
        result = snapshot_preflight(self.snapshot, payload_bytes=1024)
        self.assertEqual(result["status"], "READY_FOR_LOCAL_ANALYSIS")
        self.assertFalse(result["analysis_performed"])
        self.assertFalse(result["external_service_contacted"])
        self.assertEqual(result["limits"]["event_rows"], 4)
        self.assertEqual(result["limits"]["outcome_rows"], 2)
        self.assertEqual(result["scope"]["population"], ["W1", "W2"])
        self.assertFalse(result["scope"]["exposure"]["coverage_accepted"])
        self.assertEqual(result["scope"]["exposure"]["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        process_relation = next(item for item in result["relationships"] if item["id"] == "SYN_REL_WAFER_STEP")
        self.assertEqual(process_relation["event_rows"], 4)
        self.assertEqual(process_relation["outcome_rows"], 0)
        self.assertEqual(process_relation["status"], "CALLER_DECLARED_APPROVED")
        self.assertNotIn("claims", result)

    def test_tool_exposure_scope_is_explicit_in_preflight(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["suspected_exposure"] = {
            "condition_type": "MAINTENANCE", "tool_id": "T1",
            "start": "2026-11-21T00:00:00+00:00", "end": "2026-11-21T03:00:00+00:00",
        }
        result = snapshot_preflight(snapshot)
        self.assertEqual(result["status"], "READY_FOR_LOCAL_ANALYSIS")
        self.assertEqual(result["scope"]["exposure"]["scope_type"], "TOOL")
        self.assertEqual(result["scope"]["exposure"]["scope_id"], "T1")
        self.assertEqual(result["scope"]["exposure"]["tool_id"], "T1")
        self.assertEqual(result["scope"]["exposure"]["condition_context"], {
            "condition_type": "MAINTENANCE", "evidence_status": "CALLER_SUPPLIED_UNVERIFIED",
        })

    def test_preflight_refuses_invalid_condition_context_types(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["suspected_exposure"]["condition_type"] = ["MAINTENANCE"]
        result = snapshot_preflight(snapshot)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("condition_type must be PROCESS, MAINTENANCE, or CHANGE", result["reason"])

    def test_target_wafer_cohort_is_explicit_and_must_fit_population(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["target_wafer_ids"] = ["W1", "W2"]
        snapshot["wafer_id"] = "W1"
        valid = snapshot_preflight(snapshot)
        self.assertEqual(valid["status"], "READY_FOR_LOCAL_ANALYSIS")
        self.assertEqual(valid["scope"]["target_wafer_ids"], ["W1", "W2"])

        duplicate = copy.deepcopy(snapshot)
        duplicate["target_wafer_ids"] = ["W1", "W1"]
        self.assertEqual(snapshot_preflight(duplicate)["status"], "REFUSED")

        outside_cohort = copy.deepcopy(snapshot)
        outside_cohort["cohort"] = ["W1"]
        self.assertEqual(snapshot_preflight(outside_cohort)["status"], "REFUSED")

    def test_target_lot_uses_only_declared_outcome_membership_and_discloses_scope(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["target_lot_id"] = "LOT-A"

        preflight = snapshot_preflight(snapshot)
        self.assertEqual(preflight["status"], "READY_FOR_LOCAL_ANALYSIS")
        self.assertEqual(preflight["scope"]["target_lot_id"], "LOT-A")
        self.assertEqual(preflight["scope"]["target_wafer_ids"], ["W1", "W2"])
        self.assertTrue(any("snapshot completeness for that lot is not established" in item for item in preflight["limitations"]))

        result = analyze(snapshot)
        self.assertEqual(result["status"], "PARTIAL")
        artifact = result["artifacts"][0]
        self.assertEqual(artifact["scope"]["target_lot_id"], "LOT-A")
        self.assertEqual([item["wafer_id"] for item in artifact["target_outcomes"]], ["W1", "W2"])
        self.assertTrue(all(item["lot_id"] == "LOT-A" for item in artifact["target_outcomes"]))
        self.assertTrue(any("snapshot completeness for that lot is not established" in item for item in result["limitations"]))

    def test_target_lot_refuses_unrelated_or_incomplete_declared_membership(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["target_lot_id"] = "LOT-A"

        outcome_relation = next(item for item in snapshot["relationships"] if item["id"] == "SYN_REL_OUTCOME_WAFER")
        outcome_relation["keys"].remove("lot_id")
        missing_lot_key = snapshot_preflight(snapshot)
        self.assertEqual(missing_lot_key["status"], "REFUSED")
        self.assertIn("does not declare the source, lot_id, and wafer_id", missing_lot_key["reason"])

        outcome_relation["keys"].append("lot_id")
        snapshot["target_wafer_ids"] = ["W2"]
        mismatched_list = snapshot_preflight(snapshot)
        self.assertEqual(mismatched_list["status"], "REFUSED")
        self.assertIn("exactly match the wafer members", mismatched_list["reason"])

        del snapshot["target_wafer_ids"]
        for outcome in snapshot["outcomes"]:
            outcome["label"] = "NORMAL"
        no_abnormal = snapshot_preflight(snapshot)
        self.assertEqual(no_abnormal["status"], "REFUSED")
        self.assertIn("no caller-supplied ABNORMAL outcome", no_abnormal["reason"])

    def test_relationship_flag_cannot_replace_source_and_relationship_records(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["events"][0].pop("source_id")
        snapshot["events"][0].pop("relationship_id")
        result = snapshot_preflight(snapshot)
        self.assertEqual(result["status"], "REFUSED")
        self.assertFalse(result["analysis_performed"])
        self.assertIn("approved source record", result["reason"])

    def test_oversized_local_snapshot_is_refused_before_analysis(self):
        result = snapshot_preflight(self.snapshot, payload_bytes=25 * 1024 * 1024 + 1)
        self.assertEqual(result["status"], "REFUSED")
        self.assertFalse(result["analysis_performed"])
        self.assertIn("bytes", result["reason"])

    def test_oversized_outcome_population_is_refused_before_analysis(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["outcomes"] = [None] * (MAX_OUTCOMES + 1)
        result = snapshot_preflight(snapshot)
        self.assertEqual(result["status"], "REFUSED")
        self.assertFalse(result["analysis_performed"])
        self.assertIn("Outcome count", result["reason"])

    def test_engine_directly_refuses_oversized_outcome_population(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["outcomes"] = [None] * (MAX_OUTCOMES + 1)
        result = analyze(snapshot)
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["claims"], [])
        self.assertIn("Outcome count", result["limitations"][0])


if __name__ == "__main__":
    unittest.main()
