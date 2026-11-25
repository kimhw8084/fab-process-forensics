"""Held-out fixed-answer tests for completeness and negative evidence semantics."""
import copy
import unittest

from fabintel.project import analyze


PROCESS = {
    "id": "HOLDOUT_COVERAGE_PROCESS", "approved_semantic_version": "HOLDOUT-2",
    "grain": "one process step instance", "source_hash": "a" * 64,
    "permissions_ref": "SYNTHETIC_ONLY",
}
COVERAGE = {
    "id": "HOLDOUT_COVERAGE_RECORDS", "approved_semantic_version": "HOLDOUT-2",
    "grain": "one coverage record per scoped population", "source_hash": "b" * 64,
    "permissions_ref": "SYNTHETIC_ONLY",
}
PROCESS_REL = {
    "id": "HOLDOUT_COVERAGE_PROCESS_REL", "approved": True,
    "source_ids": [PROCESS["id"]],
    "keys": ["wafer_id", "step_instance_id", "operation", "timestamp", "chamber_id", "tool_id", "lot_id"],
    "cardinality": "one step instance to one wafer", "grain": "one process step instance",
    "effective_start": "2026-11-20T00:00:00+00:00", "effective_end": "2026-11-22T00:00:00+00:00",
}
COVERAGE_REL = {
    "id": "HOLDOUT_COVERAGE_REL", "approved": True,
    "source_ids": [COVERAGE["id"]],
    "keys": ["record_id", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids",
             "covered_source_ids", "source_ids", "population_kind", "source_authority_claim",
             "window_start", "window_end", "valid_until", "missing_record_ids"],
    "cardinality": "one coverage claim to one explicit scope", "grain": "one coverage claim",
    "effective_start": "2026-11-20T00:00:00+00:00", "effective_end": "2026-11-22T00:00:00+00:00",
}
OUTCOME = {
    "id": "HOLDOUT_COVERAGE_OUTCOMES", "approved_semantic_version": "HOLDOUT-2",
    "grain": "one outcome per wafer", "source_hash": "c" * 64,
    "permissions_ref": "SYNTHETIC_ONLY",
}
OUTCOME_REL = {
    "id": "HOLDOUT_COVERAGE_OUTCOME_REL", "approved": True,
    "source_ids": [OUTCOME["id"]], "keys": ["wafer_id", "timestamp", "label", "product_id"],
    "cardinality": "one outcome to one wafer", "grain": "one outcome per wafer",
    "effective_start": "2026-11-20T00:00:00+00:00", "effective_end": "2026-11-22T00:00:00+00:00",
}
START = "2026-11-21T00:00:00+00:00"
END = "2026-11-21T03:00:00+00:00"


def fixture():
    events = [{
        "wafer_id": "W-EXPOSED", "step_instance_id": "S-EXPOSED", "operation": "ETCH",
        "timestamp": "2026-11-21T01:00:00+00:00", "chamber_id": "C-1", "tool_id": "T-1",
        "lot_id": "L-1", "source_id": PROCESS["id"], "relationship_id": PROCESS_REL["id"],
        "approved_relationship": True,
    }, {
        "wafer_id": "W-NO-ROW", "step_instance_id": "S-OTHER", "operation": "ETCH",
        "timestamp": "2026-11-21T01:30:00+00:00", "chamber_id": "C-2", "tool_id": "T-1",
        "lot_id": "L-1", "source_id": PROCESS["id"], "relationship_id": PROCESS_REL["id"],
        "approved_relationship": True,
    }]
    coverage = {
        "record_id": "COV-1", "complete": True,
        "covered_wafer_ids": ["W-EXPOSED", "W-NO-ROW"], "covered_lot_ids": ["L-1"],
        "covered_operation_ids": ["ETCH"], "population_kind": "WAFER",
        "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION",
        "covered_source_ids": [PROCESS["id"]], "source_ids": [COVERAGE["id"]],
        "relationship_id": COVERAGE_REL["id"], "window_start": START, "window_end": END,
        "valid_until": END, "missing_record_ids": [],
    }
    return {
        "events": events, "cohort": ["W-EXPOSED", "W-NO-ROW"],
        "sources": [copy.deepcopy(PROCESS), copy.deepcopy(COVERAGE)],
        "relationships": [copy.deepcopy(PROCESS_REL), copy.deepcopy(COVERAGE_REL)],
        "coverage": coverage,
        "suspected_exposure": {"chamber_id": "C-1", "start": START, "end": END},
    }


def exposure(result):
    return result["artifacts"][0]["exposure_analysis"]


class CoverageAuthorityBoundaryTests(unittest.TestCase):
    def test_payload_cannot_promote_coverage_or_join_away_the_missing_observation(self):
        data = fixture()
        data["coverage"]["coverage_evidence_level"] = "SOURCE_VERIFIED"
        data["coverage"]["source_authority"] = {"authority_id": "caller-claimed", "authorized": True}
        data["joined_table"] = [{
            "wafer_id": "W-NO-ROW", "coverage_evidence_level": "SOURCE_VERIFIED",
            "source_authority": {"authority_id": "caller-claimed", "authorized": True},
        }]
        result = analyze(data)
        observed = exposure(result)
        self.assertEqual(observed["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        self.assertEqual(observed["definitely_exposed"], ["W-EXPOSED"])
        self.assertEqual(observed["verified_unexposed"], [])
        self.assertEqual(observed["unknown"], ["W-NO-ROW"])
        self.assertEqual(result["counterevidence"][0]["normal_wafers_verified_unexposed"], [])

    def test_only_an_exact_out_of_band_authority_scope_can_verify_negative_observation(self):
        data = fixture()
        data["sources"].append(copy.deepcopy(OUTCOME))
        data["relationships"].append(copy.deepcopy(OUTCOME_REL))
        data["outcomes"] = [{
            "wafer_id": "W-NO-ROW", "label": "NORMAL", "product_id": "P-1",
            "timestamp": "2026-11-21T02:30:00+00:00", "source_id": OUTCOME["id"],
            "relationship_id": OUTCOME_REL["id"], "approved_relationship": True,
        }]
        expected_scope = {
            "record_id": "COV-1", "relationship_id": COVERAGE_REL["id"],
            "source_ids": [COVERAGE["id"]], "covered_source_ids": [PROCESS["id"]],
            "population_kind": "WAFER", "covered_wafer_ids": ["W-EXPOSED", "W-NO-ROW"],
            "covered_lot_ids": ["L-1"], "covered_operation_ids": ["ETCH"],
            "window_start": START, "window_end": END, "valid_until": END,
        }

        def authority(request):
            if request["source_authority_claim"] != "SYNTHETIC_FIXTURE_ASSERTION" or request["scope"] != expected_scope:
                return {"authorized": False}
            return {
                "authorized": True, "authority_id": "TEST_HOST_ALLOWLIST",
                "authorization_ref": "TEST_SCOPE_GRANT", "scope": expected_scope,
            }

        result = analyze(data, coverage_authority=authority)
        observed = exposure(result)
        self.assertEqual(observed["coverage_evidence_level"], "SOURCE_VERIFIED")
        self.assertEqual(observed["verified_unexposed"], ["W-NO-ROW"])
        self.assertEqual(result["counterevidence"][0]["normal_wafers_verified_unexposed"], ["W-NO-ROW"])
        self.assertEqual(observed["coverage_evidence"]["authority"]["authorization_ref"], "TEST_SCOPE_GRANT")

    def test_wrong_scope_grant_is_not_accepted(self):
        data = fixture()

        def wrong_authority(request):
            altered = dict(request["scope"], covered_wafer_ids=["W-EXPOSED"])
            return {"authorized": True, "authority_id": "TEST", "authorization_ref": "WRONG", "scope": altered}

        observed = exposure(analyze(data, coverage_authority=wrong_authority))
        self.assertEqual(observed["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        self.assertEqual(observed["verified_unexposed"], [])
        self.assertEqual(observed["unknown"], ["W-NO-ROW"])

    def test_complete_claim_with_known_missing_event_is_contradictory(self):
        data = fixture()
        data["coverage"]["missing_record_ids"] = ["MISSING-STEP-9"]
        observed = exposure(analyze(data))
        self.assertEqual(observed["coverage_evidence_level"], "CONTRADICTORY")
        self.assertEqual(observed["verified_unexposed"], [])
        self.assertEqual(observed["unknown"], ["W-NO-ROW"])

    def test_expired_or_operation_incomplete_claim_cannot_exclude_exposure(self):
        expired = fixture()
        expired["coverage"]["valid_until"] = "2026-11-21T02:00:00+00:00"
        expired_result = exposure(analyze(expired))
        self.assertEqual(expired_result["coverage_evidence_level"], "PARTIAL")
        self.assertEqual(expired_result["unknown"], ["W-NO-ROW"])

        missing_operation = fixture()
        missing_operation["coverage"]["covered_operation_ids"] = ["CMP"]
        operation_result = exposure(analyze(missing_operation))
        self.assertEqual(operation_result["coverage_evidence_level"], "CONTRADICTORY")
        self.assertEqual(operation_result["verified_unexposed"], [])

    def test_lot_scope_conflict_is_visible_and_nonmatch_stays_unknown(self):
        data = fixture()
        data["coverage"]["covered_lot_ids"] = ["L-OTHER"]
        observed = exposure(analyze(data))
        self.assertEqual(observed["coverage_evidence_level"], "CONTRADICTORY")
        self.assertEqual(observed["verified_unexposed"], [])
        self.assertEqual(observed["unknown"], ["W-NO-ROW"])


if __name__ == "__main__":
    unittest.main()
