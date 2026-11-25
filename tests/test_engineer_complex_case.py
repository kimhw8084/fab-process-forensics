"""Independent fixed-answer oracle for the phase-one synthetic engineer task."""
import json
from pathlib import Path
import unittest

from fabintel.project import analyze


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "qualification/fixtures/complex_engineer_investigation_v1.json"


def expected_populations():
    wafers = [f"SYN-EW-{index:03d}" for index in range(100)]
    definite = [wafer for index, wafer in enumerate(wafers) if index % 4 == 0 and index != 4]
    possible = sorted([wafer for index, wafer in enumerate(wafers) if index % 4 == 2 and index not in {98}] + ["SYN-EW-004"])
    unknown = [wafer for wafer in wafers if wafer not in set(definite) | set(possible)]
    return wafers, definite, possible, unknown


class ComplexEngineerCaseOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.result = analyze(cls.snapshot)
        cls.journey_result = next(
            item for item in cls.result.get("transformations", [])
            if item.get("id") == "p2-journey-and-route-variants-v1"
        )
        cls.exposure = cls.result["artifacts"][0]["exposure_analysis"]

    def test_exact_chamber_time_and_unknown_populations_match_independent_oracle(self):
        wafers, definite, possible, unknown = expected_populations()
        self.assertEqual(self.result["status"], "PARTIAL")
        self.assertEqual(self.exposure["population"], wafers)
        self.assertEqual(self.exposure["definitely_exposed"], definite)
        self.assertEqual(self.exposure["potentially_exposed"], possible)
        self.assertEqual(self.exposure["unknown"], unknown)
        self.assertEqual(self.exposure["verified_unexposed"], [])
        self.assertEqual(self.exposure["coverage_evidence_level"], "CONTRADICTORY")

    def test_uncertainty_reasons_are_preserved_at_event_grain(self):
        evidence = self.exposure["evidence"]
        chamber_unknown = {row["wafer_id"] for row in evidence if row["classification"] == "UNKNOWN_CHAMBER"}
        clock_boundary = {row["wafer_id"] for row in evidence if row["classification"] == "TIME_BOUNDARY_UNCERTAIN"}
        self.assertEqual(len(chamber_unknown), 24)
        self.assertEqual(clock_boundary, {"SYN-EW-004"})
        self.assertTrue(all(row.get("source_id") and row.get("relationship_id") for row in evidence))

    def test_route_history_duplicate_and_maintenance_counterchecks_remain_conservative(self):
        self.assertEqual(len(self.journey_result["journeys"]), 98)
        self.assertEqual(sum(len(item["steps"]) for item in self.journey_result["journeys"]), 403)
        self.assertEqual(len(self.journey_result["route_variants"]), 6)
        self.assertEqual(self.result["uncertainty"]["collapsed_duplicate_source_records"], 1)
        self.assertEqual(self.journey_result["route_population_summary"]["declared_covered_wafer_ids_without_event_rows"],
                         ["SYN-EW-098", "SYN-EW-099"])
        ambiguous = next(item for item in self.journey_result["journeys"] if item["wafer_id"] == "SYN-EW-043")
        self.assertTrue(any(step.get("order_uncertain_with") for step in ambiguous["steps"]))
        condition = self.exposure["condition_event_evidence"]
        self.assertIn("OVERLAPS_SUSPECTED_WINDOW", {item["temporal_context"] for item in condition})
        counter = self.result["counterevidence"][0]
        self.assertEqual(counter["statistical_association"]["status"], "NOT_COMPUTED")
        self.assertEqual(counter["causal_conclusion"]["status"], "NOT_ESTABLISHED")

    def test_next_verification_is_ranked_source_grounded_and_not_executed(self):
        counter = self.result["counterevidence"][0]
        proposal = counter["next_authorized_verification"]
        candidates = proposal["candidates"]
        self.assertEqual([item["rank"] for item in candidates], list(range(1, len(candidates) + 1)))
        self.assertEqual(candidates[0]["category"], "EXPOSURE_COVERAGE")
        self.assertEqual(candidates[0]["maximum_directly_addressed_members"], 51)
        self.assertEqual(candidates[0]["coverage_record_ids"], ["SYN-EW-EXP-COV"])
        self.assertEqual(candidates[0]["missing_record_ids"], ["GAP-ETCH-044", "GAP-ETCH-077"])
        self.assertEqual(candidates[0]["review_factors"]["affected_wafer_count"], 51)
        self.assertEqual(candidates[0]["review_factors"]["coverage_evidence_level"], "CONTRADICTORY")
        self.assertEqual(candidates[0]["review_factors"]["negative_evidence_interpretation_risk"], "HIGH")
        self.assertEqual(candidates[0]["review_factors"]["bounded_read_request_count_proxy"], 1)
        self.assertIn("not measured query latency", candidates[0]["review_factors"]["cost_limit"])
        self.assertEqual(candidates[1]["category"], "UNKNOWN_CHAMBER")
        self.assertEqual(candidates[1]["maximum_directly_addressed_members"], 24)
        self.assertIn("chamber_id", candidates[1]["requested_declared_keys"])
        self.assertTrue(candidates[1]["step_instance_refs"])
        clock_check = next(item for item in candidates if item["category"] == "TIME_BOUNDARY_UNCERTAIN")
        self.assertEqual(clock_check["target_wafer_ids"], ["SYN-EW-004"])
        self.assertIn("time_uncertainty_seconds", clock_check["requested_declared_keys"])
        self.assertTrue(all(item["proposed_not_executed"] for item in candidates))
        self.assertTrue(all(
            item["authorization_status"] == "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER"
            for item in candidates
        ))
        self.assertIn("not causal probability", proposal["selection_rule"])

        declared_pairs = {
            (source_id, relation["id"])
            for relation in self.snapshot["relationships"]
            for source_id in relation["source_ids"]
        }
        for item in candidates:
            self.assertTrue(set((ref["source_id"], ref["relationship_id"]) for ref in item["source_relationships"]).issubset(declared_pairs))


if __name__ == "__main__":
    unittest.main()
