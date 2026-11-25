"""Independent challenge oracles for the P2 deterministic event baseline."""
import copy
import random
import unittest
from datetime import datetime, timedelta, timezone

from fabintel.project import analyze


SOURCE = {
    "id": "SYN_PROCESS",
    "approved_semantic_version": "SYNTHETIC-ORACLE-1",
    "grain": "one process step instance",
    "source_hash": "a" * 64,
    "permissions_ref": "SYNTHETIC-ONLY",
}
RELATIONSHIP = {
    "id": "SYN_REL_WAFER_STEP",
    "approved": True,
    "source_ids": [SOURCE["id"]],
    "keys": ["wafer_id", "step_instance_id", "timestamp", "tool_id", "chamber_id", "lot_id", "route_id", "route_version"],
    "cardinality": "one process step instance to one wafer identity",
    "grain": "one process step instance",
    "effective_start": "2026-11-20T00:00:00+00:00",
    "effective_end": "2026-11-22T00:00:00+00:00",
}
OUTCOME_SOURCE = {
    "id": "SYN_OUTCOME",
    "approved_semantic_version": "SYNTHETIC-ORACLE-1",
    "grain": "one outcome per wafer",
    "source_hash": "c" * 64,
    "permissions_ref": "SYNTHETIC-ONLY",
}
OUTCOME_RELATIONSHIP = {
    "id": "SYN_REL_OUTCOME_WAFER",
    "approved": True,
    "source_ids": [OUTCOME_SOURCE["id"]],
    "keys": ["wafer_id", "timestamp"],
    "cardinality": "one outcome to one wafer identity",
    "grain": "one outcome per wafer",
    "effective_start": "2026-11-20T00:00:00+00:00",
    "effective_end": "2026-11-22T00:00:00+00:00",
}
COVERAGE_SOURCE = {
    "id": "SYN_COVERAGE", "approved_semantic_version": "SYNTHETIC-ORACLE-1",
    "grain": "one coverage record per population and time window",
    "source_hash": "e" * 64, "permissions_ref": "SYNTHETIC-ONLY",
}
COVERAGE_RELATIONSHIP = {
    "id": "SYN_REL_COVERAGE", "approved": True,
    "source_ids": [COVERAGE_SOURCE["id"]],
    "keys": ["record_id", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids", "covered_source_ids", "population_kind", "source_authority_claim", "window_start", "window_end", "valid_until", "missing_record_ids"],
    "cardinality": "one coverage record to an explicitly listed wafer population and time window",
    "grain": "one coverage record per population and time window",
    "effective_start": "2026-11-20T00:00:00+00:00",
    "effective_end": "2026-11-22T00:00:00+00:00",
}
ROUTE_SOURCE = {
    "id": "SYN_ROUTE_CATALOG", "approved_semantic_version": "SYNTHETIC-ORACLE-1",
    "grain": "one approved route definition per route version",
    "source_hash": "f" * 64, "permissions_ref": "SYNTHETIC-ONLY",
}
ROUTE_RELATIONSHIP = {
    "id": "SYN_REL_ROUTE_DEFINITION", "approved": True,
    "source_ids": [ROUTE_SOURCE["id"]],
    "keys": ["route_id", "route_version", "approved", "operations", "allowed_sequences"],
    "cardinality": "one approved route definition to one route version",
    "grain": "one approved route definition per route version",
    "effective_start": "2026-11-20T00:00:00+00:00",
    "effective_end": "2026-11-22T00:00:00+00:00",
}
CONDITION_SOURCE = {
    "id": "SYN_CONDITION",
    "approved_semantic_version": "SYNTHETIC-ORACLE-1",
    "grain": "one equipment condition event",
    "source_hash": "d" * 64,
    "permissions_ref": "SYNTHETIC-ONLY",
}
CONDITION_RELATIONSHIP = {
    "id": "SYN_REL_CONDITION_EQUIPMENT",
    "approved": True,
    "source_ids": [CONDITION_SOURCE["id"]],
    "keys": ["condition_event_id", "condition_type", "equipment_type", "equipment_id", "event_start", "event_end"],
    "cardinality": "one equipment condition event to one equipment identity",
    "grain": "one equipment condition event",
    "effective_start": "2026-11-20T00:00:00+00:00",
    "effective_end": "2026-11-22T00:00:00+00:00",
}


def event(wafer, step, operation="ETCH", timestamp="2026-11-21T01:00:00+00:00", chamber="C1", **extra):
    row = {
        "wafer_id": wafer, "step_instance_id": step, "operation": operation,
        "timestamp": timestamp, "chamber_id": chamber, "source_id": SOURCE["id"],
        "tool_id": None, "lot_id": None, "route_id": None, "route_version": None,
        "relationship_id": RELATIONSHIP["id"], "approved_relationship": True,
    }
    row.update(extra)
    return row


def coverage(wafer_ids, start="2026-11-21T00:00:00+00:00", end="2026-11-21T03:00:00+00:00", *, operations=None, lots=None):
    return {
        "complete": True, "covered_wafer_ids": list(wafer_ids),
        "covered_lot_ids": list(lots or []), "covered_operation_ids": list(operations or ["ETCH", "CLEAN", "CMP", "MET"]),
        "population_kind": "WAFER", "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION",
        "source_ids": [COVERAGE_SOURCE["id"]], "relationship_id": COVERAGE_RELATIONSHIP["id"],
        "covered_source_ids": [SOURCE["id"]], "record_id": "SYN_COVERAGE_RECORD",
        "missing_record_ids": [],
        "window_start": start, "window_end": end, "valid_until": end,
    }


def route_coverage(wafer_ids, covered_source_ids):
    return {
        "complete": True, "covered_wafer_ids": list(wafer_ids),
        "covered_lot_ids": [], "covered_operation_ids": ["ETCH", "CLEAN", "CMP", "MET"],
        "population_kind": "WAFER", "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION",
        "source_ids": [COVERAGE_SOURCE["id"]],
        "covered_source_ids": list(covered_source_ids),
        "missing_record_ids": [],
        "relationship_id": COVERAGE_RELATIONSHIP["id"],
        "record_id": "SYN_ROUTE_COVERAGE_RECORD",
        "window_start": "2026-11-20T00:00:00+00:00",
        "window_end": "2026-11-22T00:00:00+00:00", "valid_until": "2026-11-22T00:00:00+00:00",
    }


def investigation(events, cohort, **extra):
    result = {
        "events": events, "cohort": cohort,
        "sources": [copy.deepcopy(SOURCE), copy.deepcopy(COVERAGE_SOURCE)],
        "relationships": [copy.deepcopy(RELATIONSHIP), copy.deepcopy(COVERAGE_RELATIONSHIP)],
        "suspected_exposure": {
            "chamber_id": "C1", "tool_id": "T1",
            "start": "2026-11-21T00:00:00+00:00", "end": "2026-11-21T03:00:00+00:00",
        },
        "coverage": coverage(
            cohort,
            operations=sorted({row.get("operation") for row in events if row.get("operation")}),
            lots=sorted({row.get("lot_id") for row in events if row.get("lot_id")}),
        ),
    }
    result.update(extra)
    return result


def exposure(result):
    return result["artifacts"][0]["exposure_analysis"]


def synthetic_coverage_authority(request):
    """Test-only host policy; never loaded from the evidence snapshot."""
    scope = request.get("scope", {})
    if (request.get("source_authority_claim") != "SYNTHETIC_FIXTURE_ASSERTION"
            or not scope.get("source_ids")
            or not all(source.startswith("SYN_") for source in scope["source_ids"])):
        return {"authorized": False}
    return {
        "authorized": True, "authority_id": "TEST_ALLOWLISTED_SOURCE_AUTHORITY",
        "authorization_ref": "TEST_POLICY_SCOPE_MATCH", "scope": scope,
    }


class P2ChallengeTests(unittest.TestCase):
    def test_p2_01_repeated_operation_keeps_distinct_step_instances(self):
        result = analyze({"wafer_id": "W1", "events": [
            event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00"),
            event("W1", "S2", timestamp="2026-11-21T02:00:00+00:00"),
        ], "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        journey = result["transformations"][1]["journeys"][0]["steps"]
        self.assertEqual([s["step_instance_id"] for s in journey], ["S1", "S2"])
        self.assertEqual([s["operation"] for s in journey], ["ETCH", "ETCH"])

    def test_p2_02_same_hour_wrong_chamber_remains_unknown_under_asserted_coverage(self):
        data = investigation([
            event("W1", "S1", chamber="C1"),
            event("W2", "S2", chamber="C2", tool_id="T2"),
        ], ["W1", "W2"])
        result = analyze(data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(exposure(result)["definitely_exposed"], ["W1"])
        self.assertEqual(exposure(result)["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        self.assertEqual(exposure(result)["verified_unexposed"], [])
        self.assertEqual(exposure(result)["not_observed_exposed_under_unverified_coverage"], ["W2"])
        self.assertEqual(exposure(result)["unknown"], ["W2"])

    def test_p2_03_unapproved_relationship_refuses_path(self):
        row = event("W1", "S1")
        row["approved_relationship"] = False
        result = analyze({"wafer_id": "W1", "events": [row]})
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["claims"], [])

    def test_p2_04_missing_chamber_on_known_tool_is_unknown(self):
        data = investigation([event("W1", "S1", chamber=None, tool_id="T1")], ["W1"])
        result = analyze(data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(exposure(result)["definitely_exposed"], [])
        self.assertEqual(exposure(result)["possibly_exposed"], ["W1"])
        self.assertEqual(exposure(result)["verified_unexposed"], [])

    def test_exact_tool_window_uses_tool_id_without_inferring_chamber_membership(self):
        rows = [
            event("W1", "T1_MATCH", chamber="C1", tool_id="T1"),
            event("W2", "OTHER_TOOL", chamber="C1", tool_id="T2"),
            event("W3", "MISSING_TOOL", chamber="C1", tool_id=None),
        ]
        data = investigation(rows, ["W1", "W2", "W3"])
        data["suspected_exposure"] = {
            "condition_type": "MAINTENANCE", "tool_id": "T1",
            "start": "2026-11-21T00:00:00+00:00", "end": "2026-11-21T03:00:00+00:00",
        }
        result = analyze(data)
        observed = exposure(result)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(observed["scope_type"], "TOOL")
        self.assertEqual(observed["scope_id"], "T1")
        self.assertEqual(observed["definitely_exposed"], ["W1"])
        self.assertEqual(observed["potentially_exposed"], ["W3"])
        self.assertEqual(observed["verified_unexposed"], [])
        self.assertEqual(observed["not_observed_exposed_under_unverified_coverage"], ["W2"])
        self.assertEqual(observed["unknown"], ["W2"])
        self.assertEqual(observed["condition_context"], {
            "condition_type": "MAINTENANCE", "evidence_status": "CALLER_SUPPLIED_UNVERIFIED",
        })
        evidence_by_wafer = {item["wafer_id"]: item for item in observed["evidence"]}
        self.assertEqual(evidence_by_wafer["W1"]["classification"], "EXACT_TOOL_WINDOW_MATCH")
        self.assertEqual(evidence_by_wafer["W3"]["classification"], "UNKNOWN_TOOL")
        self.assertEqual(evidence_by_wafer["W3"]["scope_id"], "T1")

    def test_invalid_maintenance_context_is_refused_as_unverified_input(self):
        data = investigation([event("W1", "S1", tool_id="T1")], ["W1"])
        data["suspected_exposure"] = {
            "condition_type": ["MAINTENANCE"], "tool_id": "T1",
            "start": "2026-11-21T00:00:00+00:00", "end": "2026-11-21T03:00:00+00:00",
        }
        result = analyze(data)
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["claims"], [])
        self.assertIn("condition_type must be PROCESS, MAINTENANCE, or CHANGE", result["limitations"][0])

    def test_100_seeded_cohorts_match_independent_exact_tool_oracle(self):
        rng = random.Random(20261126)
        start = "2026-11-21T00:00:00+00:00"
        end = "2026-11-21T03:00:00+00:00"
        for case_no in range(100):
            wafers = [f"ET{case_no}-{index}" for index in range(rng.randint(3, 10))]
            rows = []
            exact = set()
            possible = set()
            for index, wafer_id in enumerate(wafers):
                hour = rng.randint(0, 5)
                minute = rng.randint(0, 59)
                tool_id = rng.choice(["T1", "T1", "T2", None])
                chamber = rng.choice(["C1", "C2", None])
                timestamp = f"2026-11-21T{hour:02d}:{minute:02d}:00+00:00"
                rows.append(event(wafer_id, f"ET{case_no}-S{index}", chamber=chamber,
                                  tool_id=tool_id, timestamp=timestamp))
                in_window = start <= timestamp < end
                if tool_id == "T1" and in_window:
                    exact.add(wafer_id)
                elif tool_id is None and in_window:
                    possible.add(wafer_id)

            data = investigation(rows, wafers)
            data["suspected_exposure"] = {"tool_id": "T1", "start": start, "end": end}
            result = analyze(data)
            observed = exposure(result)
            self.assertEqual(observed["definitely_exposed"], sorted(exact), f"exact tool case {case_no}")
            self.assertEqual(observed["potentially_exposed"], sorted(possible), f"unknown tool case {case_no}")
            self.assertEqual(observed["verified_unexposed"], [], f"unverified coverage cannot confirm tool nonexposure case {case_no}")
            self.assertEqual(observed["not_observed_exposed_under_unverified_coverage"], sorted(set(wafers) - exact - possible), f"asserted nonmatch case {case_no}")

    def test_p2_05_naive_timestamp_refuses_order(self):
        row = event("W1", "S1", timestamp="2026-11-21T01:00:00")
        self.assertEqual(analyze({"events": [row]})["status"], "REFUSED")

    def test_p2_06_namespaced_wafer_aliases_are_not_merged(self):
        result = analyze({"events": [
            event("FAB-A:W1", "A1", timestamp="2026-11-21T01:00:00+00:00", alias="W1"),
            event("FAB-B:W1", "B1", timestamp="2026-11-21T02:00:00+00:00", alias="W1"),
        ], "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        self.assertEqual([j["wafer_id"] for j in result["transformations"][1]["journeys"]], ["FAB-A:W1", "FAB-B:W1"])

    def test_same_wafer_token_across_sources_requires_explicit_identity_approval(self):
        source_b = {**SOURCE, "id": "SYN_PROCESS_B", "source_hash": "b" * 64}
        left = event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00")
        right = event("W1", "S2", timestamp="2026-11-21T02:00:00+00:00")
        right["source_id"] = source_b["id"]
        shared = {**RELATIONSHIP, "source_ids": [SOURCE["id"], source_b["id"]]}
        data = {"events": [left, right], "sources": [SOURCE, source_b], "relationships": [shared]}
        refused = analyze(data)
        self.assertEqual(refused["status"], "REFUSED")
        self.assertIn("without an approved identity relationship", refused["limitations"][0])
        approved = {**shared, "entity_identity": True}
        for row in (left, right):
            row["identity_relationship_id"] = approved["id"]
        data["relationships"] = [approved]
        result = analyze(data)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(len(result["transformations"][1]["journeys"]), 1)
        self.assertEqual(len(result["transformations"][1]["journeys"][0]["steps"]), 2)

    def test_p2_07_outside_maintenance_window_is_not_exposed(self):
        data = investigation([
            event("W1", "BEFORE", timestamp="2026-11-20T23:59:59+00:00"),
            event("W1", "AFTER", timestamp="2026-11-21T03:00:00+00:00"),
        ], ["W1"])
        result = analyze(data)
        self.assertEqual(exposure(result)["definitely_exposed"], [])
        self.assertEqual(exposure(result)["verified_unexposed"], [])
        self.assertEqual(exposure(result)["not_observed_exposed_under_unverified_coverage"], ["W1"])

    def test_p2_08_incomplete_events_do_not_become_route_violation(self):
        result = analyze({"wafer_id": "W1", "events": [event("W1", "S1")], "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        text = str(result["transformations"][1]["route_variants"])
        self.assertNotIn("violation", text.lower())
        self.assertIn("only against an approved expected route", text)

    def test_approved_route_comparison_requires_coverage_and_reports_mismatch_carefully(self):
        rows = [
            event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00", route_id="R1", route_version="v1"),
            event("W1", "S2", operation="MET", timestamp="2026-11-21T02:00:00+00:00", route_id="R1", route_version="v1"),
        ]
        data = {
            "wafer_id": "W1", "events": rows, "sources": [SOURCE, ROUTE_SOURCE], "relationships": [RELATIONSHIP, ROUTE_RELATIONSHIP],
            "expected_routes": [{"route_id": "R1", "route_version": "v1", "approved": True,
                                 "source_id": ROUTE_SOURCE["id"], "relationship_id": ROUTE_RELATIONSHIP["id"],
                                 "operations": ["ETCH"]}],
        }
        incomplete = analyze(data)
        self.assertEqual(incomplete["status"], "PARTIAL")
        self.assertEqual(incomplete["transformations"][1]["journeys"][0]["route_conformance"], "COVERAGE_INCOMPLETE")
        data["sources"].append(COVERAGE_SOURCE)
        data["relationships"].append(COVERAGE_RELATIONSHIP)
        data["route_coverage"] = route_coverage(["W1"], [SOURCE["id"], ROUTE_SOURCE["id"]])
        compared = analyze(data, coverage_authority=synthetic_coverage_authority)
        self.assertEqual(compared["status"], "VALID")
        self.assertEqual(compared["transformations"][1]["journeys"][0]["route_conformance"], "EXPECTED_ROUTE_MISMATCH")
        self.assertTrue(any("not classified as a process violation" in note for note in compared["limitations"]))

    def test_explicit_rework_link_is_retained_and_removed_from_base_route_comparison(self):
        rework_relationship = {
            **RELATIONSHIP,
            "id": "SYN_REL_EXPLICIT_REWORK",
            "keys": [*RELATIONSHIP["keys"], "rework_of_step_instance_id"],
        }
        data = {
            "wafer_id": "W1", "events": [
                event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00", route_id="R1", route_version="v1"),
                event("W1", "S2", timestamp="2026-11-21T02:00:00+00:00", route_id="R1", route_version="v1",
                      rework_of_step_instance_id="S1", relationship_id=rework_relationship["id"]),
            ],
            "sources": [SOURCE, COVERAGE_SOURCE, ROUTE_SOURCE], "relationships": [RELATIONSHIP, rework_relationship, COVERAGE_RELATIONSHIP, ROUTE_RELATIONSHIP],
            "expected_routes": [{"route_id": "R1", "route_version": "v1", "approved": True,
                                 "source_id": ROUTE_SOURCE["id"], "relationship_id": ROUTE_RELATIONSHIP["id"],
                                 "operations": ["ETCH"]}],
            "route_coverage": route_coverage(["W1"], [SOURCE["id"], ROUTE_SOURCE["id"]]),
        }
        result = analyze(data, coverage_authority=synthetic_coverage_authority)
        self.assertEqual(result["transformations"][1]["journeys"][0]["route_conformance"], "EXPECTED_ROUTE_MATCH")
        self.assertEqual(result["transformations"][1]["journeys"][0]["steps"][1]["rework_of_step_instance_id"], "S1")

    def test_rework_relationship_carries_step_instance_provenance(self):
        data = {
            "wafer_id": "W1", "events": [
                event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00"),
                event("W1", "S2", timestamp="2026-11-21T02:00:00+00:00",
                      rework_of_step_instance_id="S1", relationship_id="SYN_REL_EXPLICIT_REWORK"),
            ], "sources": [SOURCE], "relationships": [
                RELATIONSHIP,
                {**RELATIONSHIP, "id": "SYN_REL_EXPLICIT_REWORK",
                 "keys": ["wafer_id", "step_instance_id", "timestamp", "rework_of_step_instance_id"]},
            ],
        }
        result = analyze(data)
        journey = result["transformations"][1]["journeys"][0]
        edge = journey["rework_edges"][0]
        self.assertEqual(edge["relationship_type"], "EXPLICIT_REWORK_REFERENCE")
        self.assertEqual(edge["to_step_instance"], {"source_id": SOURCE["id"], "step_instance_id": "S1"})
        self.assertEqual({ref.get("relationship_id") for ref in edge["provenance"] if "relationship_id" in ref},
                         {RELATIONSHIP["id"], "SYN_REL_EXPLICIT_REWORK"})

    def test_exact_duplicate_rows_are_counted_once_and_conflicts_refuse(self):
        row = event("W1", "S1")
        result = analyze({"wafer_id": "W1", "events": [copy.deepcopy(row), copy.deepcopy(row)],
                          "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        journey = result["transformations"][1]["journeys"][0]
        self.assertEqual(len(journey["steps"]), 1)
        self.assertEqual(journey["steps"][0]["duplicate_record_copies_collapsed"], 1)
        self.assertEqual(result["uncertainty"]["collapsed_duplicate_source_records"], 1)
        conflicting = copy.deepcopy(row)
        conflicting["operation"] = "CMP"
        refused = analyze({"wafer_id": "W1", "events": [row, conflicting],
                           "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        self.assertEqual(refused["status"], "REFUSED")
        self.assertIn("Conflicting duplicate", refused["limitations"][0])

    def test_operation_definitions_are_distinct_from_step_instances(self):
        event_relationship = {
            **RELATIONSHIP, "id": "SYN_REL_STEP_WITH_OPERATION_DEFINITION",
            "keys": ["wafer_id", "step_instance_id", "timestamp", "operation_definition_id"],
        }
        definition_relationship = {
            **RELATIONSHIP, "id": "SYN_REL_OPERATION_DEFINITION",
            "keys": ["operation_definition_id", "operation"],
        }
        row = event("W1", "INSTANCE-77", operation="ETCH", operation_definition_id="OP-ETCH-v2",
                    relationship_id=event_relationship["id"])
        definition = {
            "operation_definition_id": "OP-ETCH-v2", "operation": "ETCH", "approved": True,
            "source_id": SOURCE["id"], "semantic_version": SOURCE["approved_semantic_version"],
            "relationship_id": definition_relationship["id"],
            "effective_start": "2026-11-20T00:00:00+00:00", "effective_end": "2026-11-22T00:00:00+00:00",
        }
        result = analyze({"wafer_id": "W1", "events": [row], "sources": [SOURCE],
                          "relationships": [event_relationship, definition_relationship],
                          "operation_definitions": [definition]})
        step = result["transformations"][1]["journeys"][0]["steps"][0]
        self.assertEqual(step["step_instance_id"], "INSTANCE-77")
        self.assertEqual(step["operation_definition_id"], "OP-ETCH-v2")
        self.assertEqual(step["operation_definition_status"], "SOURCE_LINKED_APPROVED")
        bad = copy.deepcopy(definition)
        bad["operation"] = "CMP"
        refused = analyze({"wafer_id": "W1", "events": [row], "sources": [SOURCE],
                           "relationships": [event_relationship, definition_relationship],
                           "operation_definitions": [bad]})
        self.assertEqual(refused["status"], "REFUSED")

    def test_time_scoped_membership_split_and_merge_links_keep_source_provenance(self):
        material_source = {
            "id": "SYN_MATERIAL", "approved_semantic_version": "SYNTHETIC-ORACLE-1",
            "grain": "one material relationship record", "source_hash": "d" * 64,
            "permissions_ref": "SYNTHETIC-ONLY",
        }
        endpoint_keys = ["from_entity_id", "from_entity_type", "to_entity_id", "to_entity_type"]
        material_relationships = [
            {**RELATIONSHIP, "id": "SYN_REL_LOT_MEMBERSHIP", "source_ids": [material_source["id"]],
             "keys": endpoint_keys, "relationship_type": "LOT_MEMBERSHIP"},
            {**RELATIONSHIP, "id": "SYN_REL_LOT_SPLIT", "source_ids": [material_source["id"]],
             "keys": endpoint_keys, "relationship_type": "SPLIT_FROM"},
            {**RELATIONSHIP, "id": "SYN_REL_LOT_MERGE", "source_ids": [material_source["id"]],
             "keys": endpoint_keys, "relationship_type": "MERGED_FROM"},
        ]
        def material_edge(record_id, kind, source, target, rel_id, start, end):
            return {
                "record_id": record_id, "relationship_type": kind, "source_id": material_source["id"],
                "relationship_id": rel_id, "from_entity": source, "to_entity": target,
                "key_values": {"from_entity_id": source["id"], "from_entity_type": source["type"],
                               "to_entity_id": target["id"], "to_entity_type": target["type"]},
                "effective_start": start, "effective_end": end, "observed_at": "2026-11-21T02:00:00+00:00",
            }
        data = {
            "wafer_id": "W1", "sources": [SOURCE, material_source],
            "relationships": [RELATIONSHIP, *material_relationships],
            "events": [
                event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00", lot_id="L1"),
                event("W1", "S2", timestamp="2026-11-21T02:00:00+00:00", lot_id="L2"),
            ],
            "material_relationships": [
                material_edge("MEM-1", "LOT_MEMBERSHIP", {"type": "lot", "id": "L1"}, {"type": "wafer", "id": "W1"}, "SYN_REL_LOT_MEMBERSHIP", "2026-11-21T00:00:00+00:00", "2026-11-21T02:00:00+00:00"),
                material_edge("MEM-2", "LOT_MEMBERSHIP", {"type": "lot", "id": "L2"}, {"type": "wafer", "id": "W1"}, "SYN_REL_LOT_MEMBERSHIP", "2026-11-21T02:00:00+00:00", "2026-11-21T03:00:00+00:00"),
                material_edge("SPLIT-1", "SPLIT_FROM", {"type": "lot", "id": "L1"}, {"type": "lot", "id": "L2"}, "SYN_REL_LOT_SPLIT", "2026-11-21T02:00:00+00:00", "2026-11-21T03:00:00+00:00"),
                material_edge("MERGE-1", "MERGED_FROM", {"type": "lot", "id": "L3"}, {"type": "lot", "id": "L2"}, "SYN_REL_LOT_MERGE", "2026-11-21T02:00:00+00:00", "2026-11-21T03:00:00+00:00"),
            ],
        }
        result = analyze(data)
        self.assertEqual(result["status"], "VALID")
        journey = result["transformations"][1]["journeys"][0]
        self.assertEqual([step["membership_state"] for step in journey["steps"]], [
            "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP", "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP",
        ])
        edges = result["transformations"][1]["material_relationships"]
        self.assertEqual({edge["relationship_type"] for edge in edges}, {"LOT_MEMBERSHIP", "SPLIT_FROM", "MERGED_FROM"})
        self.assertTrue(all(edge["provenance"]["source_id"] == material_source["id"] for edge in edges))

    def test_history_coverage_states_are_explicit_and_missing_records_remain_incomplete(self):
        coverage_source = {
            "id": "SYN_COVERAGE", "approved_semantic_version": "SYNTHETIC-ORACLE-1",
            "grain": "one query coverage record", "source_hash": "e" * 64,
            "permissions_ref": "SYNTHETIC-ONLY",
        }
        coverage_relationship = {
            **RELATIONSHIP, "id": "SYN_REL_COVERAGE", "source_ids": [coverage_source["id"]],
            "keys": ["record_id", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids",
                     "covered_source_ids", "population_kind", "source_authority_claim",
                     "window_start", "window_end", "valid_until", "missing_record_ids"],
        }
        history = {
            "complete": True, "covered_wafer_ids": ["W1"], "covered_lot_ids": [],
            "covered_operation_ids": ["ETCH"], "population_kind": "WAFER",
            "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION", "source_ids": [coverage_source["id"]],
            "covered_source_ids": [SOURCE["id"]],
            "relationship_id": coverage_relationship["id"], "record_id": "COV-1",
            "window_start": "2026-11-20T00:00:00+00:00", "window_end": "2026-11-22T00:00:00+00:00",
            "valid_until": "2026-11-22T00:00:00+00:00",
            "missing_record_ids": [],
        }
        base = {"wafer_id": "W1", "events": [event("W1", "S1")],
                "sources": [SOURCE, coverage_source], "relationships": [RELATIONSHIP, coverage_relationship]}
        complete = analyze({**base, "history_coverage": history})
        self.assertEqual(complete["transformations"][1]["journeys"][0]["history_status"], "COVERAGE_ASSERTED_UNVERIFIED")
        self.assertEqual(complete["transformations"][1]["journeys"][0]["history_coverage"]["coverage_evidence_level"], "ASSERTED_UNVERIFIED")
        incomplete = analyze({**base, "history_coverage": {**history, "missing_record_ids": ["MISSING-1"]}})
        self.assertEqual(incomplete["transformations"][1]["journeys"][0]["history_status"], "INCOMPLETE")
        unknown = analyze(base)
        self.assertEqual(unknown["transformations"][1]["journeys"][0]["history_status"], "COVERAGE_UNKNOWN")

        other_source = {**SOURCE, "id": "SYN_PROCESS_B", "source_hash": "b" * 64}
        other_relationship = {
            **RELATIONSHIP, "id": "SYN_REL_WAFER_STEP_B", "source_ids": [other_source["id"]],
        }
        other_event = {
            **event("W2", "S2", timestamp="2026-11-21T02:00:00+00:00"),
            "source_id": other_source["id"], "relationship_id": other_relationship["id"],
        }
        omitted_source_coverage = {
            **history, "covered_wafer_ids": ["W1", "W2"],
            "covered_source_ids": [SOURCE["id"]],
        }
        incomplete_sources = analyze({
            **base, "events": [event("W1", "S1"), other_event],
            "sources": [SOURCE, other_source, coverage_source],
            "relationships": [RELATIONSHIP, other_relationship, coverage_relationship],
            "history_coverage": omitted_source_coverage,
        })
        self.assertEqual(
            {journey["history_status"] for journey in incomplete_sources["transformations"][1]["journeys"]},
            {"INCOMPLETE"},
        )

    def test_ordered_history_edges_include_both_event_relationships(self):
        result = analyze({"wafer_id": "W1", "events": [
            event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00"),
            event("W1", "S2", timestamp="2026-11-21T02:00:00+00:00"),
        ], "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        edge = result["transformations"][1]["journeys"][0]["sequence_edges"][0]
        self.assertEqual(edge["relationship_type"], "OBSERVED_CHRONOLOGICAL_ADJACENCY")
        self.assertEqual(edge["ordering_margin_seconds"], 3600)
        self.assertEqual({item["step_instance_id"] for item in edge["provenance"]}, {"S1", "S2"})
        self.assertEqual({item["relationship_id"] for item in edge["provenance"]}, {RELATIONSHIP["id"]})

    def test_route_version_changes_and_explicit_allowed_exceptions_are_supported(self):
        rows = [
            event("W1", "S1", operation="ETCH", timestamp="2026-11-21T01:00:00+00:00", route_id="R1", route_version="v1"),
            event("W1", "S2", operation="CMP", timestamp="2026-11-21T02:00:00+00:00", route_id="R2", route_version="v2"),
        ]
        data = {
            "wafer_id": "W1", "events": rows, "sources": [SOURCE, COVERAGE_SOURCE, ROUTE_SOURCE], "relationships": [RELATIONSHIP, COVERAGE_RELATIONSHIP, ROUTE_RELATIONSHIP],
            "expected_routes": [
                {"route_id": "R1", "route_version": "v1", "approved": True, "source_id": ROUTE_SOURCE["id"], "relationship_id": ROUTE_RELATIONSHIP["id"], "operations": ["ETCH"]},
                {"route_id": "R2", "route_version": "v2", "approved": True, "source_id": ROUTE_SOURCE["id"], "relationship_id": ROUTE_RELATIONSHIP["id"], "operations": ["CMP"]},
            ],
            "route_coverage": route_coverage(["W1"], [SOURCE["id"], ROUTE_SOURCE["id"]]),
        }
        changed = analyze(data, coverage_authority=synthetic_coverage_authority)
        journey = changed["transformations"][1]["journeys"][0]
        self.assertEqual(journey["route_conformance"], "EXPECTED_ROUTE_MATCH")
        self.assertEqual([(item["route_id"], item["route_version"]) for item in journey["route_segments"]], [("R1", "v1"), ("R2", "v2")])
        exception_data = {
            "wafer_id": "W1", "events": [
                event("W1", "S1", operation="ETCH", timestamp="2026-11-21T01:00:00+00:00", route_id="R1", route_version="v1"),
                event("W1", "S2", operation="CMP", timestamp="2026-11-21T02:00:00+00:00", route_id="R1", route_version="v1"),
            ], "sources": [SOURCE, COVERAGE_SOURCE, ROUTE_SOURCE], "relationships": [RELATIONSHIP, COVERAGE_RELATIONSHIP, ROUTE_RELATIONSHIP],
            "expected_routes": [{"route_id": "R1", "route_version": "v1", "approved": True,
                                 "source_id": ROUTE_SOURCE["id"], "relationship_id": ROUTE_RELATIONSHIP["id"],
                                 "operations": ["ETCH"], "allowed_sequences": [["ETCH", "CMP"]]}],
            "route_coverage": route_coverage(["W1"], [SOURCE["id"], ROUTE_SOURCE["id"]]),
        }
        exception = analyze(exception_data, coverage_authority=synthetic_coverage_authority)
        self.assertEqual(exception["transformations"][1]["journeys"][0]["route_conformance"], "EXPECTED_ROUTE_MATCH")

    def test_p2_09_lot_membership_is_retained_at_each_event(self):
        result = analyze({"wafer_id": "W1", "events": [
            event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00", lot_id="L1"),
            event("W2", "S2", timestamp="2026-11-21T01:00:00+00:00", lot_id="L1"),
            event("W1", "S3", timestamp="2026-11-21T02:00:00+00:00", lot_id="L2"),
            event("W2", "S4", timestamp="2026-11-21T02:00:00+00:00", lot_id="L3"),
            event("W1", "S5", timestamp="2026-11-21T03:00:00+00:00", lot_id="L4"),
            event("W2", "S6", timestamp="2026-11-21T03:00:00+00:00", lot_id="L4"),
        ], "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        journeys = {journey["wafer_id"]: journey["steps"] for journey in result["transformations"][1]["journeys"]}
        self.assertEqual([step["lot_id_at_event"] for step in journeys["W1"]], ["L1", "L2", "L4"])
        self.assertEqual([step["lot_id_at_event"] for step in journeys["W2"]], ["L1", "L3", "L4"])

    def test_target_wafer_cohort_emits_a_chronology_claim_for_each_selected_wafer(self):
        data = investigation([
            event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00", chamber="C2"),
            event("W2", "S2", timestamp="2026-11-21T01:10:00+00:00", chamber="C1"),
            event("W3", "S3", timestamp="2026-11-21T01:20:00+00:00", chamber="C1"),
        ], ["W1", "W2", "W3"])
        data["target_wafer_ids"] = ["W2", "W3"]
        data["wafer_id"] = "W2"
        result = analyze(data)
        chronology = [item["statement"] for item in result["claims"] if item["method"] == "typed_step_instance_chronology"]
        self.assertEqual(len(chronology), 2)
        self.assertTrue(any(statement.startswith("Wafer W2 ") for statement in chronology))
        self.assertTrue(any(statement.startswith("Wafer W3 ") for statement in chronology))
        self.assertEqual(exposure(result)["population"], ["W1", "W2", "W3"])

    def test_p2_10_and_11_normal_exposure_and_abnormal_nonexposure_are_counterevidence(self):
        data = investigation([
            event("W1", "S1", chamber="C1"),
            event("W2", "S2", chamber="C2", tool_id="T2"),
            event("W3", "S3", chamber="C1"),
        ], ["W1", "W2", "W3", "W4"], outcomes=[
            {"wafer_id": "W1", "label": "NORMAL", "timestamp": "2026-11-21T02:00:00+00:00",
             "source_id": OUTCOME_SOURCE["id"], "relationship_id": OUTCOME_RELATIONSHIP["id"], "approved_relationship": True},
            {"wafer_id": "W2", "label": "ABNORMAL", "timestamp": "2026-11-21T02:00:00+00:00",
             "source_id": OUTCOME_SOURCE["id"], "relationship_id": OUTCOME_RELATIONSHIP["id"], "approved_relationship": True},
            {"wafer_id": "W3", "label": "ABNORMAL", "timestamp": "2026-11-21T02:00:00+00:00",
             "source_id": OUTCOME_SOURCE["id"], "relationship_id": OUTCOME_RELATIONSHIP["id"], "approved_relationship": True},
        ])
        data["wafer_id"] = "W1"
        data["sources"].append(OUTCOME_SOURCE)
        data["relationships"].append(OUTCOME_RELATIONSHIP)
        result = analyze(data)
        counter = result["counterevidence"][0]
        self.assertEqual(counter["abnormal_wafers_with_exact_exposure"], ["W3"])
        self.assertEqual(counter["normal_wafers_with_exact_exposure"], ["W1"])
        self.assertEqual(counter["abnormal_wafers_verified_unexposed"], [])
        self.assertEqual(counter["abnormal_wafers_not_observed_under_unverified_coverage"], ["W2"])
        self.assertEqual(counter["population_wafers_missing_outcome"], ["W4"])
        w2_outcome_evidence = next(item for item in counter["outcome_evidence"] if item["wafer_id"] == "W2")
        self.assertEqual(w2_outcome_evidence["source_id"], OUTCOME_SOURCE["id"])
        self.assertEqual(w2_outcome_evidence["relationship_id"], OUTCOME_RELATIONSHIP["id"])
        self.assertEqual(w2_outcome_evidence["exposure_classification"], "UNKNOWN")
        self.assertEqual(counter["statistical_association"]["status"], "NOT_COMPUTED")
        self.assertEqual(counter["causal_conclusion"]["status"], "NOT_ESTABLISHED")
        self.assertIn("W1", counter["contradicting_observations"]["normal_wafers_sharing_exact_exposure"][0]["wafer_id"])
        self.assertEqual(counter["missing_or_ambiguous_evidence"]["outcomes_missing"], ["W4"])
        w1_exposure_evidence = next(item for item in exposure(result)["evidence"] if item["wafer_id"] == "W1")
        self.assertEqual(w1_exposure_evidence["source_id"], SOURCE["id"])
        self.assertEqual(w1_exposure_evidence["relationship_id"], RELATIONSHIP["id"])
        self.assertEqual(exposure(result)["coverage_evidence"]["source_ids"], [COVERAGE_SOURCE["id"]])
        self.assertEqual(exposure(result)["coverage_evidence"]["relationship_id"], COVERAGE_RELATIONSHIP["id"])
        claim_by_method = {claim["method"]: claim for claim in result["claims"]}
        self.assertEqual(claim_by_method["typed_step_instance_chronology"]["source_ids"], [SOURCE["id"]])
        self.assertEqual(claim_by_method["exact_wafer_event_sequence_grouping"]["source_ids"], [SOURCE["id"]])
        self.assertEqual(claim_by_method["exact_chamber_and_timezone_aware_window_with_coverage_gate"]["source_ids"],
                         sorted([SOURCE["id"], COVERAGE_SOURCE["id"]]))
        self.assertEqual(claim_by_method["descriptive_outcome_exposure_cross_tabulation"]["source_ids"],
                         sorted([SOURCE["id"], COVERAGE_SOURCE["id"], OUTCOME_SOURCE["id"]]))
        relationships = result["artifacts"][0]["source_relationships"]
        self.assertEqual({item["id"] for item in relationships},
                         {RELATIONSHIP["id"], OUTCOME_RELATIONSHIP["id"], COVERAGE_RELATIONSHIP["id"]})
        self.assertIn("establish a causal conclusion", counter["interpretation"])
        self.assertFalse(any(c["category"] in ("CAUSAL_ESTIMATE", "INTERVENTION_VALIDATED") for c in result["claims"]))

    def test_chamber_scope_does_not_transfer_between_overlapping_chambers(self):
        rows = [
            event("W1", "C1_STEP", chamber="C1", tool_id="T1"),
            event("W2", "C2_STEP", chamber="C2", tool_id="T1"),
        ]
        data = investigation(rows, ["W1", "W2"])
        data["suspected_exposure"] = {"chamber_id": "C1", "tool_id": "T1", "start": "2026-11-21T00:00:00+00:00", "end": "2026-11-21T03:00:00+00:00"}
        result = analyze(data)
        self.assertEqual(exposure(result)["definitely_exposed"], ["W1"])
        self.assertEqual(exposure(result)["not_observed_exposed"], [])
        self.assertEqual(exposure(result)["not_observed_exposed_under_unverified_coverage"], ["W2"])
        self.assertEqual(exposure(result)["condition_context"]["evidence_status"], "NOT_SUPPLIED")

    def test_repeated_processing_retains_each_exact_exposure_instance(self):
        data = investigation([
            event("W1", "ETCH-1", chamber="C1", tool_id="T1", timestamp="2026-11-21T01:00:00+00:00"),
            event("W1", "ETCH-2", chamber="C1", tool_id="T1", timestamp="2026-11-21T02:00:00+00:00"),
        ], ["W1"])
        observed = exposure(analyze(data))
        self.assertEqual(observed["definitely_exposed"], ["W1"])
        self.assertEqual([item["step_instance_id"] for item in observed["evidence"]], ["ETCH-1", "ETCH-2"])

    def test_missing_population_moves_remain_unknown_even_with_other_observations(self):
        data = investigation([event("W1", "S1", chamber="C2", tool_id="T1")], ["W1", "W2"])
        data["coverage"]["complete"] = False
        observed = exposure(analyze(data))
        self.assertEqual(observed["unknown"], ["W1", "W2"])
        self.assertEqual(observed["not_observed_exposed"], [])

    def test_equipment_and_time_fields_must_be_approved_by_event_relationship(self):
        row = event("W1", "S1", chamber="C1", tool_id="T1")
        data = investigation([row], ["W1"])
        data["relationships"][0]["keys"] = ["wafer_id", "step_instance_id", "timestamp"]
        observed = exposure(analyze(data))
        self.assertEqual(observed["definitely_exposed"], [])
        self.assertEqual(observed["unknown"], ["W1"])
        self.assertEqual(observed["evidence"][0]["classification"], "SCOPE_OR_TIME_FIELD_NOT_APPROVED_BY_RELATIONSHIP")

    def test_source_linked_condition_events_report_time_context_without_causal_claim(self):
        data = investigation([event("W1", "S1", chamber="C1", tool_id="T1")], ["W1"])
        data["suspected_exposure"]["condition_type"] = "MAINTENANCE"
        data["sources"].append(CONDITION_SOURCE)
        data["relationships"].append(CONDITION_RELATIONSHIP)
        data["condition_events"] = [{
            "condition_event_id": "M1", "condition_type": "MAINTENANCE", "equipment_type": "CHAMBER",
            "equipment_id": "C1", "event_start": "2026-11-21T00:00:30+00:00", "event_end": "2026-11-21T00:00:45+00:00",
            "time_uncertainty_seconds": 60, "source_id": CONDITION_SOURCE["id"],
            "relationship_id": CONDITION_RELATIONSHIP["id"], "approved_relationship": True,
        }]
        result = analyze(data)
        observed = exposure(result)
        self.assertEqual(observed["condition_event_status"], "SOURCE_LINKED_EXACT_SCOPE_EVENTS_PRESENT")
        self.assertEqual(observed["condition_event_evidence"][0]["temporal_context"], "BOUNDARY_TIMING_UNCERTAIN")
        self.assertTrue(observed["condition_event_evidence"][0]["matches_caller_condition_label"])
        self.assertTrue(any("does not establish exposure effect" in item["meaning"] for item in observed["condition_event_evidence"]))
        self.assertEqual(result["counterevidence"][0]["population_wafers_missing_outcome"], ["W1"])
        self.assertFalse(any(claim["category"] in ("CAUSAL_ESTIMATE", "INTERVENTION_VALIDATED") for claim in result["claims"]))

    def test_false_condition_relationship_refuses_condition_context(self):
        data = investigation([event("W1", "S1", chamber="C1", tool_id="T1")], ["W1"])
        data["sources"].append(CONDITION_SOURCE)
        relation = copy.deepcopy(CONDITION_RELATIONSHIP)
        relation["approved"] = False
        data["relationships"].append(relation)
        data["condition_events"] = [{
            "condition_event_id": "M1", "condition_type": "MAINTENANCE", "equipment_type": "CHAMBER",
            "equipment_id": "C1", "event_start": "2026-11-21T01:00:00+00:00", "event_end": "2026-11-21T01:30:00+00:00",
            "source_id": CONDITION_SOURCE["id"], "relationship_id": CONDITION_RELATIONSHIP["id"], "approved_relationship": True,
        }]
        self.assertEqual(analyze(data)["status"], "REFUSED")

    def test_outcome_provenance_requires_effective_relationship_and_all_keys(self):
        outcome = {
            "wafer_id": "W1", "label": "ABNORMAL", "timestamp": "2026-11-21T02:00:00+00:00",
            "source_id": OUTCOME_SOURCE["id"], "relationship_id": OUTCOME_RELATIONSHIP["id"],
            "approved_relationship": True,
        }
        data = investigation([event("W1", "S1")], ["W1"], outcomes=[outcome])
        data["sources"].append(OUTCOME_SOURCE)
        data["relationships"].append(OUTCOME_RELATIONSHIP)
        self.assertEqual(analyze(data)["status"], "PARTIAL")

        expired = copy.deepcopy(data)
        expired["outcomes"][0]["timestamp"] = "2026-11-23T00:00:00+00:00"
        self.assertEqual(analyze(expired)["status"], "REFUSED")

        malformed = copy.deepcopy(data)
        malformed["relationships"][-1]["keys"] = ["wafer_id", "measurement_id"]
        self.assertEqual(analyze(malformed)["status"], "REFUSED")

    def test_p2_12_13k_catalog_rejects_unapproved_join(self):
        from fabintel.catalog import approved_join, synthetic_catalog
        catalog = synthetic_catalog(13000)
        self.assertFalse(approved_join(catalog[0]["id"], catalog[1]["id"], "wafer_id", catalog))
        self.assertFalse(approved_join(catalog[0]["id"], catalog[31]["id"], "step_instance_id", catalog,
                                       time_window=("2026-11-21T00:00:00+00:00", "2026-11-21T01:00:00+00:00")))

    def test_catalog_join_requires_exact_approved_effective_relationship(self):
        from fabintel.catalog import approved_join, synthetic_catalog
        catalog = synthetic_catalog(3)
        first, second = catalog[1], catalog[2]
        first["relationships"] = [{
            "target_id": second["id"], "approved": True, "keys": ["step_instance_id"],
            "cardinality": "many_to_one", "effective_start": "2026-11-20T00:00:00+00:00",
            "effective_end": "2026-11-22T00:00:00+00:00",
        }]
        self.assertFalse(approved_join(first["id"], second["id"], "step_instance_id", catalog))
        self.assertTrue(approved_join(first["id"], second["id"], "step_instance_id", catalog,
                                      time_window=("2026-11-21T00:00:00+00:00", "2026-11-21T01:00:00+00:00")))
        self.assertFalse(approved_join(first["id"], second["id"], "wafer_id", catalog,
                                       time_window=("2026-11-21T00:00:00+00:00", "2026-11-21T01:00:00+00:00")))
        self.assertFalse(approved_join(first["id"], second["id"], "step_instance_id", catalog,
                                       time_window=("2026-11-19T00:00:00+00:00", "2026-11-21T01:00:00+00:00")))

    def test_incomplete_coverage_never_labels_nonmatch_unexposed(self):
        data = investigation([event("W1", "S1", chamber="C2")], ["W1"])
        data["coverage"]["complete"] = False
        result = analyze(data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(exposure(result)["verified_unexposed"], [])
        self.assertEqual(exposure(result)["possibly_exposed"], ["W1"])

    def test_interval_overlap_and_half_open_window_boundaries(self):
        interval_relation = {**RELATIONSHIP, "id": "SYN_REL_PROCESSING_INTERVAL",
                             "keys": [*RELATIONSHIP["keys"], "processing_start", "processing_end"]}
        first = event("W1", "OVERLAP", timestamp="2026-11-20T23:00:00+00:00", chamber="C1",
                      processing_start="2026-11-20T23:00:00+00:00", processing_end="2026-11-21T00:30:00+00:00",
                      relationship_id=interval_relation["id"])
        data = investigation([first, event("W2", "AT_END", timestamp="2026-11-21T03:00:00+00:00", chamber="C1")], ["W1", "W2"])
        data["relationships"].append(interval_relation)
        result = analyze(data)
        self.assertEqual(exposure(result)["definitely_exposed"], ["W1"])
        self.assertEqual(exposure(result)["verified_unexposed"], [])
        self.assertEqual(exposure(result)["not_observed_exposed_under_unverified_coverage"], ["W2"])

    def test_equal_time_order_is_partial_not_tie_broken_as_fact(self):
        result = analyze({"wafer_id": "W1", "events": [
            event("W1", "S1", timestamp="2026-11-21T01:00:00+00:00"),
            event("W1", "S2", timestamp="2026-11-21T01:00:00+00:00"),
        ], "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["uncertainty"]["equal_timestamp_ties"], [["S1", "S2"]])

    def test_record_time_is_preserved_separately_from_event_time(self):
        result = analyze({"wafer_id": "W1", "events": [event(
            "W1", "S1", timestamp="2026-11-21T01:00:00-06:00", recorded_at="2026-11-21T08:00:00+00:00",
        )], "sources": [SOURCE], "relationships": [RELATIONSHIP]})
        step = result["transformations"][1]["journeys"][0]["steps"][0]
        self.assertEqual(step["timestamp"], "2026-11-21T01:00:00-06:00")
        self.assertEqual(step["timestamp_utc"], "2026-11-21T07:00:00+00:00")
        self.assertEqual(step["recorded_at"], "2026-11-21T08:00:00+00:00")

    def test_overlapping_clock_ranges_refuse_route_order_and_exact_exposure(self):
        rows = [
            event("W1", "S1", timestamp="2026-11-21T00:00:05+00:00", time_uncertainty_seconds=10),
            event("W1", "S2", timestamp="2026-11-21T00:00:12+00:00", chamber="C2", time_uncertainty_seconds=10),
        ]
        result = analyze(investigation(rows, ["W1"]))
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(exposure(result)["definitely_exposed"], [])
        self.assertEqual(exposure(result)["possibly_exposed"], ["W1"])
        self.assertEqual(result["transformations"][1]["journeys"][0]["route_conformance"], "ORDER_UNCERTAIN")
        self.assertTrue(any(variant["order_status"] == "ORDER_UNCERTAIN" for variant in result["transformations"][1]["route_variants"]))

    def test_event_source_without_metadata_is_refused(self):
        row = event("W1", "S1", source_id="NO_METADATA")
        result = analyze({"events": [row]})
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("without approved semantic metadata", result["limitations"][0])

    def test_approved_flag_without_source_relationship_is_refused(self):
        row = event("W1", "S1")
        row.pop("source_id")
        row.pop("relationship_id")
        result = analyze({"events": [row]})
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["claims"], [])
        self.assertIn("approved_relationship flags alone are not evidence", result["limitations"][0])

    def test_100_seeded_cohorts_match_independent_exact_chamber_oracle(self):
        rng = random.Random(20261122)
        start = "2026-11-21T00:00:00+00:00"
        end = "2026-11-21T03:00:00+00:00"
        for case_no in range(100):
            count = rng.randint(2, 10)
            wafers = [f"W{case_no}-{i}" for i in range(count)]
            chamber_choices = ["C1", "C2", None]
            rows = [event(
                wafer, f"S{case_no}-{index}",
                timestamp=f"2026-11-21T{rng.randint(0, 2):02d}:{rng.randint(0,59):02d}:00+00:00",
                chamber=rng.choice(chamber_choices), tool_id="T1",
            ) for index, wafer in enumerate(wafers)]
            # Independent oracle: exact chamber and in-window event timestamp only.
            expected = sorted({row["wafer_id"] for row in rows if row["chamber_id"] == "C1" and start <= row["timestamp"] < end})
            data = investigation(rows, wafers)
            data["suspected_exposure"]["tool_id"] = "OTHER_TOOL"
            data["coverage"] = coverage(wafers)
            result = analyze(data)
            self.assertEqual(exposure(result)["definitely_exposed"], expected, f"seeded case {case_no}")
            self.assertEqual(result, analyze(copy.deepcopy(data)))

    def test_100_seeded_exposure_windows_match_interval_oracle_across_timezones(self):
        rng = random.Random(20261123)
        utc = timezone.utc
        origin = datetime(2026, 11, 21, tzinfo=utc)
        window_start = origin + timedelta(minutes=30)
        window_end = origin + timedelta(minutes=150)
        offsets = [-480, 0, 330, 840]

        def local_iso(instant, offset_minutes):
            return instant.astimezone(timezone(timedelta(minutes=offset_minutes))).isoformat(timespec="seconds")

        def as_utc(value):
            return datetime.fromisoformat(value).astimezone(utc)

        for case_no in range(100):
            cohort = [f"TW{case_no}-{index}" for index in range(rng.randint(3, 8))]
            rows = []
            expected_exact = set()
            expected_possible = set()
            for index, wafer_id in enumerate(cohort):
                chamber = rng.choice(["C1", "C1", "C2", None])
                offset = rng.choice(offsets)
                if rng.choice([True, False]):
                    event_time = origin + timedelta(minutes=rng.randint(-60, 300), seconds=rng.randint(0, 59))
                    uncertainty = rng.choice([0, 10, 120, 600, 1800])
                    row = event(
                        wafer_id, f"TW{case_no}-S{index}", chamber=chamber,
                        timestamp=local_iso(event_time, offset),
                        time_uncertainty_seconds=uncertainty,
                    )
                    low = as_utc(row["timestamp"]) - timedelta(seconds=uncertainty)
                    high = as_utc(row["timestamp"]) + timedelta(seconds=uncertainty)
                    if low >= window_end or high < window_start:
                        temporal = "OUTSIDE"
                    elif low >= window_start and high < window_end:
                        temporal = "DEFINITE"
                    else:
                        temporal = "POSSIBLE"
                else:
                    processing_start = origin + timedelta(minutes=rng.randint(-60, 300))
                    processing_end = processing_start + timedelta(minutes=rng.randint(1, 45))
                    event_time = processing_start + (processing_end - processing_start) / 2
                    row = event(
                        wafer_id, f"TW{case_no}-S{index}", chamber=chamber,
                        timestamp=local_iso(event_time, offset),
                        processing_start=local_iso(processing_start, offset),
                        processing_end=local_iso(processing_end, offset),
                    )
                    temporal = "DEFINITE" if as_utc(row["processing_start"]) < window_end and as_utc(row["processing_end"]) > window_start else "OUTSIDE"
                rows.append(row)
                if chamber == "C1" and temporal == "DEFINITE":
                    expected_exact.add(wafer_id)
                elif chamber in ("C1", None) and temporal != "OUTSIDE":
                    expected_possible.add(wafer_id)

            expected_possible -= expected_exact
            data = investigation(rows, cohort)
            interval_rows = [row for row in rows if "processing_start" in row]
            if interval_rows:
                interval_relation = {**RELATIONSHIP, "id": "SYN_REL_PROCESSING_INTERVAL",
                                     "keys": [*RELATIONSHIP["keys"], "processing_start", "processing_end"]}
                for row in interval_rows:
                    row["relationship_id"] = interval_relation["id"]
                data["relationships"].append(interval_relation)
            data["suspected_exposure"]["start"] = window_start.isoformat()
            data["suspected_exposure"]["end"] = window_end.isoformat()
            data["coverage"]["window_start"] = window_start.isoformat()
            data["coverage"]["window_end"] = window_end.isoformat()
            data["coverage"]["valid_until"] = window_end.isoformat()
            result = analyze(data)
            observed = exposure(result)
            self.assertEqual(observed["definitely_exposed"], sorted(expected_exact), f"exact case {case_no}")
            self.assertEqual(observed["potentially_exposed"], sorted(expected_possible), f"possible case {case_no}")
            self.assertEqual(observed["verified_unexposed"], [], f"unverified coverage cannot establish nonexposure case {case_no}")
            self.assertEqual(observed["not_observed_exposed_under_unverified_coverage"], sorted(set(cohort) - expected_exact - expected_possible), f"asserted nonmatch case {case_no}")

    def test_event_input_permutations_preserve_chronological_investigation(self):
        rng = random.Random(20261124)
        for case_no in range(25):
            cohort = [f"PW{case_no}-{index}" for index in range(6)]
            rows = []
            for wafer_index, wafer_id in enumerate(cohort):
                for step_index in range(3):
                    minute = rng.randrange(0, 180)
                    rows.append(event(
                        wafer_id, f"PW{case_no}-{wafer_index}-{step_index}",
                        timestamp=f"2026-11-21T{minute // 60:02d}:{minute % 60:02d}:00+00:00",
                        chamber=rng.choice(["C1", "C2", None]),
                        lot_id=f"LOT-{wafer_index // 2}",
                    ))
            data = investigation(rows, cohort)
            baseline = analyze(data)
            stable_fields = ("status", "claims", "transformations", "populations", "counterevidence", "uncertainty", "limitations")
            expected = {field: baseline[field] for field in stable_fields}
            for permutation in range(4):
                shuffled = copy.deepcopy(data)
                rng.shuffle(shuffled["events"])
                result = analyze(shuffled)
                self.assertEqual({field: result[field] for field in stable_fields}, expected,
                                 f"case {case_no}, permutation {permutation}")

    def test_40_seeded_counterevidence_cohorts_match_independent_cross_tab_oracle(self):
        rng = random.Random(20261125)
        for case_no in range(40):
            cohort = [f"CW{case_no}-{index}" for index in range(30)]
            chamber_by_wafer = {wafer_id: rng.choice(["C1", "C2", None]) for wafer_id in cohort}
            label_by_wafer = {wafer_id: rng.choice(["NORMAL", "ABNORMAL", None]) for wafer_id in cohort}
            label_by_wafer[cohort[0]] = "NORMAL"
            label_by_wafer[cohort[1]] = "ABNORMAL"
            rows = [event(wafer_id, f"CW{case_no}-S{index}", chamber=chamber_by_wafer[wafer_id])
                    for index, wafer_id in enumerate(cohort)]
            outcomes = [{
                "wafer_id": wafer_id, "label": label, "timestamp": "2026-11-21T02:00:00+00:00",
                "source_id": OUTCOME_SOURCE["id"], "relationship_id": OUTCOME_RELATIONSHIP["id"],
                "approved_relationship": True,
            } for wafer_id, label in label_by_wafer.items() if label is not None]
            data = investigation(rows, cohort, outcomes=outcomes)
            data["sources"].append(OUTCOME_SOURCE)
            data["relationships"].append(OUTCOME_RELATIONSHIP)
            result = analyze(data)
            observed = result["counterevidence"][0]
            exposed = {wafer_id for wafer_id, chamber in chamber_by_wafer.items() if chamber == "C1"}
            unexposed = {wafer_id for wafer_id, chamber in chamber_by_wafer.items() if chamber == "C2"}
            unknown = set(chamber_by_wafer) - exposed
            expected = {
                "abnormal_wafers_with_exact_exposure": sorted(w for w, label in label_by_wafer.items() if label == "ABNORMAL" and w in exposed),
                "normal_wafers_with_exact_exposure": sorted(w for w, label in label_by_wafer.items() if label == "NORMAL" and w in exposed),
                "abnormal_wafers_verified_unexposed": [],
                "normal_wafers_verified_unexposed": [],
                "abnormal_wafers_not_observed_under_unverified_coverage": sorted(w for w, label in label_by_wafer.items() if label == "ABNORMAL" and w in unexposed),
                "normal_wafers_not_observed_under_unverified_coverage": sorted(w for w, label in label_by_wafer.items() if label == "NORMAL" and w in unexposed),
                "outcomes_with_unknown_exposure": sorted(w for w, label in label_by_wafer.items() if label is not None and w in unknown),
                "population_wafers_missing_outcome": sorted(w for w, label in label_by_wafer.items() if label is None),
            }
            self.assertEqual({key: observed[key] for key in expected}, expected, f"cross-tab case {case_no}")
            self.assertFalse(any(claim["category"] in ("CAUSAL_ESTIMATE", "INTERVENTION_VALIDATED") for claim in result["claims"]))


if __name__ == "__main__":
    unittest.main()
