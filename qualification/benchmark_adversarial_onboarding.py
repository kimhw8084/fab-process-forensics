"""Independently specified structural source-mapping challenge suite."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fabintel.catalog import synthetic_catalog
from fabintel.onboarding import propose_mappings


CAPTURE = ROOT / "qualification/fixtures/onboarding_descriptor_capture_synthetic_v1.json"
OUTPUT = ROOT / "qualification/evidence/onboarding-adversarial-environments.json"
ROLE_EXPECTATIONS = {
    "events": "SITE_EVENTS_ALIAS", "outcomes": "SITE_OUTCOMES_ALIAS",
    "coverage": "SITE_COVERAGE_ALIAS", "history_coverage": "SITE_HISTORY_ALIAS",
    "route_definitions": "SITE_ROUTE_DEFINITION_ALIAS", "route_coverage": "SITE_ROUTE_COVERAGE_ALIAS",
    "material_relationships": "SITE_MATERIAL_ALIAS",
}


def _source(data, role):
    kind = {
        "events": "PROCESS_STEP_INSTANCE", "outcomes": "WAFER_OUTCOME",
        "coverage": "EXPOSURE_COVERAGE", "history_coverage": "PROCESS_HISTORY_COVERAGE",
        "route_definitions": "ROUTE_DEFINITION", "route_coverage": "ROUTE_COVERAGE",
        "material_relationships": "MATERIAL_RELATIONSHIP",
    }[role]
    return next(item for item in data["sources"] if item.get("record_kind") == kind)


def _relation(data, source_id):
    return next(item for item in data["relationships"] if item.get("source_ids") == [source_id])


def _renamed_semantic_environment(base):
    capture = copy.deepcopy(base)
    field_aliases = {
        "wafer_ref": "wafer_identifier", "operation_instance": "step_occurrence_id",
        "processed_at": "processed_timestamp", "performed_op": "operation_performed",
        "tool_asset": "tool_identifier", "chamber_asset": "chamber_identifier",
        "lot_ref": "lot_identifier", "result_state": "outcome_label",
        "result_time": "outcome_timestamp", "edge_id": "membership_record_id",
        "parent_lot": "lot_parent_identifier", "parent_kind": "parent_entity_type",
        "member_wafer": "wafer_child_identifier", "member_kind": "child_entity_type",
        "valid_from": "membership_start", "valid_to": "membership_end",
        "source_seen_at": "descriptor_observed_at", "coverage_ref": "coverage_identifier",
        "is_complete": "complete_scope", "wafers_in_scope": "wafer_scope_ids",
        "lots_in_scope": "lot_scope_ids", "operations_in_scope": "operation_scope_ids",
        "sources_in_scope": "covered_source_ids", "source_refs": "scope_source_ids",
        "population_grain": "population_level", "authority_label": "authority_assertion",
        "scope_start": "validity_start", "scope_end": "validity_end",
        "expires_at": "scope_expiry", "missing_refs": "missing_record_refs",
        "captured_at": "descriptor_timestamp", "route_ref": "route_identifier",
        "version_ref": "route_version_identifier", "definition_approved": "route_is_approved",
        "ordered_ops": "ordered_operation_codes", "valid_sequences": "alternative_operation_orders",
        "defined_at": "route_document_time",
    }
    source_ids, source_hashes = {}, {}
    for source in capture["sources"]:
        old = source["source_id"]
        source["source_id"] = old.replace("SITE_", "ENV2_")
        source_ids[old] = source["source_id"]
        source["source_hash"] = hashlib.sha256(source["source_id"].encode()).hexdigest()
        source_hashes[source["source_id"]] = source["source_hash"]
        source["column_definitions"] = {
            field_aliases.get(name, name): definition
            for name, definition in source["column_definitions"].items()
        }
    for relation in capture["relationships"]:
        relation["id"] = relation["id"].replace("SITE_REL_", "ENV2_REL_")
        relation["source_ids"] = [source_ids[item] for item in relation["source_ids"]]
        relation["keys"] = [field_aliases.get(name, name) for name in relation["keys"]]
        relation["source_reference"] = {
            "source_ids": list(relation["source_ids"]),
            "source_hash": source_hashes[relation["source_ids"][0]],
            "semantic_version": relation["source_reference"]["semantic_version"],
        }
    tool_names = {}
    for tool in capture["tools"]:
        old = tool["name"]
        tool["name"] = old.replace("site_", "fabsvc__")
        tool_names[old] = tool["name"]
    capture["tool_versions"] = {tool_names[name]: version
                                 for name, version in capture["tool_versions"].items()}
    return capture


def _fixed_cases(base):
    # Expected answer is declared here before calling propose_mappings.
    cases = []

    canonical = copy.deepcopy(base)
    cases.append(("separate_explicit_semantics", canonical, {
        "states": {role: "UNIQUE_REVIEW_REQUIRED" for role in ROLE_EXPECTATIONS},
        "top_ids": dict(ROLE_EXPECTATIONS), "expected_abstention": False,
    }))

    renamed = _renamed_semantic_environment(base)
    renamed_role_ids = {role: source_id.replace("SITE_", "ENV2_")
                        for role, source_id in ROLE_EXPECTATIONS.items()}
    cases.append(("renamed_fields_and_source_conventions", renamed, {
        "states": {role: "UNIQUE_REVIEW_REQUIRED" for role in ROLE_EXPECTATIONS},
        "top_ids": renamed_role_ids, "expected_abstention": False,
    }))

    event_clock_ambiguous = copy.deepcopy(base)
    events = _source(event_clock_ambiguous, "events")
    events["column_definitions"]["step_completed_at"] = copy.deepcopy(
        events["column_definitions"]["processed_at"]
    )
    cases.append(("two_process_event_time_fields", event_clock_ambiguous, {
        "states": {"events": "NO_STRUCTURALLY_COMPATIBLE_SOURCE"},
        "top_ids": {"events": None}, "expected_abstention": True,
        "diagnostics": {"events": "AMBIGUOUS_PROCESS_EVENT_TIME"},
    }))

    split_merge = copy.deepcopy(base)
    membership = _source(split_merge, "material_relationships")
    membership_relation = _relation(split_merge, membership["source_id"])
    for kind in ("LOT_SPLIT", "LOT_MERGE"):
        split_merge["relationships"].append({
            **copy.deepcopy(membership_relation), "id": f"SITE_REL_{kind}",
            "relationship_type": kind,
        })
    cases.append(("membership_with_split_merge_edges", split_merge, {
        "states": {"material_relationships": "UNIQUE_REVIEW_REQUIRED"},
        "top_ids": {"material_relationships": ROLE_EXPECTATIONS["material_relationships"]},
        "expected_abstention": False,
        "diagnostics": {"material_relationships": "MATERIAL_LINEAGE_RELATIONSHIP_UNMAPPED"},
    }))

    ingested_only = copy.deepcopy(base)
    events = _source(ingested_only, "events")
    events["column_definitions"]["processed_at"]["meaning"] = "record ingestion time"
    cases.append(("process_record_time_decoy", ingested_only, {
        "states": {"events": "NO_STRUCTURALLY_COMPATIBLE_SOURCE"},
        "top_ids": {"events": None}, "expected_abstention": True,
    }))

    group_only = copy.deepcopy(base)
    events = _source(group_only, "events")
    events["column_definitions"].pop("chamber_asset")
    events["column_definitions"].pop("tool_asset")
    events["column_definitions"]["tool_group_ref"] = {"type": "identifier", "entity": "tool_group"}
    rel = _relation(group_only, events["source_id"])
    rel["keys"] = [key for key in rel["keys"] if key not in {"tool_asset", "chamber_asset"}]
    cases.append(("equipment_group_without_chamber", group_only, {
        "states": {"events": "UNIQUE_REVIEW_REQUIRED"},
        "top_ids": {"events": ROLE_EXPECTATIONS["events"]}, "expected_abstention": False,
        "must_report_unknown": "chamber_id",
    }))

    static_membership = copy.deepcopy(base)
    membership = _source(static_membership, "material_relationships")
    for key in ("valid_from", "valid_to"):
        membership["column_definitions"].pop(key)
    rel = _relation(static_membership, membership["source_id"])
    rel["keys"] = [key for key in rel["keys"] if key not in {"valid_from", "valid_to"}]
    cases.append(("static_membership_no_history", static_membership, {
        "states": {"material_relationships": "NO_STRUCTURALLY_COMPATIBLE_SOURCE"},
        "top_ids": {"material_relationships": None}, "expected_abstention": True,
    }))

    version_conflict = copy.deepcopy(base)
    current = _source(version_conflict, "events")
    current_rel = _relation(version_conflict, current["source_id"])
    previous = copy.deepcopy(current)
    previous["source_id"] = "HISTORY_EVENT_V3"
    previous["semantic_version"] = "synthetic-previous-v3"
    previous["source_hash"] = "c" * 64
    version_conflict["sources"].append(previous)
    previous_rel = copy.deepcopy(current_rel)
    previous_rel["id"] = "HISTORY_EVENT_V3_REL"
    previous_rel["source_ids"] = [previous["source_id"]]
    previous_rel["source_reference"] = {
        "source_ids": [previous["source_id"]], "source_hash": previous["source_hash"],
        "semantic_version": previous["semantic_version"],
    }
    version_conflict["relationships"].append(previous_rel)
    cases.append(("two_active_versioned_event_sources", version_conflict, {
        "states": {"events": "AMBIGUOUS"}, "top_ids": {"events": None},
        "expected_abstention": True,
    }))

    authority_conflict = copy.deepcopy(base)
    first = _source(authority_conflict, "events")
    first["authority_ref"] = "SYNTHETIC_AUTHORITY_A"
    second = copy.deepcopy(first)
    second["source_id"] = "OTHER_EVENT_AUTHORITY"
    second["source_hash"] = "f" * 64
    second["authority_ref"] = "SYNTHETIC_AUTHORITY_B"
    authority_conflict["sources"].append(second)
    first_relation = _relation(authority_conflict, first["source_id"])
    second_relation = copy.deepcopy(first_relation)
    second_relation["id"] = "OTHER_EVENT_AUTHORITY_REL"
    second_relation["source_ids"] = [second["source_id"]]
    second_relation["source_reference"] = {
        "source_ids": [second["source_id"]], "source_hash": second["source_hash"],
        "semantic_version": second["semantic_version"],
    }
    authority_conflict["relationships"].append(second_relation)
    cases.append(("conflicting_event_source_authorities", authority_conflict, {
        "states": {"events": "AMBIGUOUS"}, "top_ids": {"events": None},
        "expected_abstention": True,
    }))

    duplicate_tool = copy.deepcopy(base)
    duplicate = copy.deepcopy(duplicate_tool["tools"][3])
    duplicate["name"] = "alternate_bounded_read"
    duplicate_tool["tools"].append(duplicate)
    duplicate_tool["tool_versions"][duplicate["name"]] = "site-4.2.2"
    cases.append(("duplicate_read_tool_description", duplicate_tool, {
        "states": {}, "top_ids": {}, "expected_abstention": True,
        "operation_states": {"read_bounded": "AMBIGUOUS"},
    }))

    misleading_combined = copy.deepcopy(base)
    events = _source(misleading_combined, "events")
    events["source_id"] = "ALL_PROCESS_AND_OUTCOME_HISTORY"
    events["record_kind"] = "COMBINED_UNTYPED_HISTORY"
    rel = _relation(misleading_combined, "SITE_EVENTS_ALIAS")
    rel["source_ids"] = [events["source_id"]]
    rel["source_reference"]["source_ids"] = [events["source_id"]]
    cases.append(("misleading_combined_table_name", misleading_combined, {
        "states": {"events": "NO_STRUCTURALLY_COMPATIBLE_SOURCE"},
        "top_ids": {"events": None}, "expected_abstention": True,
    }))

    split_edge_only = copy.deepcopy(base)
    membership = _source(split_edge_only, "material_relationships")
    rel = _relation(split_edge_only, membership["source_id"])
    rel["relationship_type"] = "LOT_SPLIT"
    cases.append(("split_relationship_not_membership", split_edge_only, {
        "states": {"material_relationships": "NO_STRUCTURALLY_COMPATIBLE_SOURCE"},
        "top_ids": {"material_relationships": None}, "expected_abstention": True,
    }))

    no_outcomes = copy.deepcopy(base)
    no_outcomes["sources"] = [item for item in no_outcomes["sources"] if item.get("record_kind") != "WAFER_OUTCOME"]
    cases.append(("outcome_role_missing", no_outcomes, {
        "states": {"outcomes": "NO_STRUCTURALLY_COMPATIBLE_SOURCE"},
        "top_ids": {"outcomes": None}, "expected_abstention": True,
    }))

    denied = copy.deepcopy(base)
    source = _source(denied, "events")
    source["approved"] = False
    cases.append(("permission_restricted_descriptor", denied, {
        "states": {"events": "NO_STRUCTURALLY_COMPATIBLE_SOURCE"},
        "top_ids": {"events": None}, "expected_abstention": True,
    }))

    decoy_name = copy.deepcopy(base)
    decoy = copy.deepcopy(_source(decoy_name, "events"))
    decoy["source_id"] = "PROCESS_STEP_INSTANCE_CHAMBER_EVENTS"
    decoy["record_kind"] = "SCHEDULED_ROUTE_INTENT"
    decoy["source_hash"] = "d" * 64
    decoy_name["sources"].append(decoy)
    cases.append(("semantic_decoy_named_like_event_log", decoy_name, {
        "states": {"events": "UNIQUE_REVIEW_REQUIRED"},
        "top_ids": {"events": ROLE_EXPECTATIONS["events"]}, "expected_abstention": False,
    }))
    return cases


def main():
    base = json.loads(CAPTURE.read_text(encoding="utf-8"))
    cases = _fixed_cases(base)
    # Exercise the established large catalogue workload without allowing names
    # to influence semantic role mapping.
    large = copy.deepcopy(base)
    large["sources"].extend({
        "source_id": item["id"], "record_kind": None, "approved": item["approved"],
        "grain": "unknown", "column_definitions": {},
    } for item in synthetic_catalog(13000))
    clock_decoy = copy.deepcopy(_source(large, "events"))
    clock_decoy["source_id"] = "DECOY_INGESTION_TIME_EVENTS"
    clock_decoy["source_hash"] = "e" * 64
    clock_decoy["column_definitions"]["processed_at"]["meaning"] = "record ingestion time"
    large["sources"].append(clock_decoy)
    clock_relation = copy.deepcopy(_relation(large, ROLE_EXPECTATIONS["events"]))
    clock_relation["id"] = "DECOY_INGESTION_TIME_REL"
    clock_relation["source_ids"] = [clock_decoy["source_id"]]
    clock_relation["source_reference"] = {
        "source_ids": [clock_decoy["source_id"]], "source_hash": clock_decoy["source_hash"],
        "semantic_version": clock_decoy["semantic_version"],
    }
    large["relationships"].append(clock_relation)
    cases.append(("catalog_13008_descriptors", large, {
        "states": {role: "UNIQUE_REVIEW_REQUIRED" for role in ROLE_EXPECTATIONS},
        "top_ids": dict(ROLE_EXPECTATIONS), "expected_abstention": False,
    }))

    results = []
    state_correct = top_rank_correct = 0
    total_expected = 0
    wrong_candidates_autoaccepted = 0
    review_decisions = []
    for name, capture, expected in cases:
        started = time.perf_counter()
        report = propose_mappings(capture)
        elapsed_ms = (time.perf_counter() - started) * 1000
        states_ok, ranking_ok = True, True
        for role, expected_state in expected["states"].items():
            total_expected += 1
            actual = report["source_role_proposals"][role]
            states_ok &= actual["candidate_state"] == expected_state
            expected_top = expected["top_ids"][role]
            actual_top = actual["preferred_candidate_source_id"]
            ranking_ok &= actual_top == expected_top
        diagnostics_ok = True
        for role, code in expected.get("diagnostics", {}).items():
            proposal = report["source_role_proposals"][role]
            diagnostics = [item for candidate in proposal["candidates"]
                           for item in candidate.get("diagnostics", [])]
            diagnostics_ok &= any(item.get("code") == code for item in diagnostics)
        operation_states_ok = all(
            report["operation_proposals"][operation]["candidate_state"] == state
            for operation, state in expected.get("operation_states", {}).items()
        )
        candidates_needing_review = sum(
            item.get("candidate_state") in {"STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED", "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED"}
            for proposal in report["source_role_proposals"].values() for item in proposal["candidates"]
        )
        review_decisions.append(len(report["required_manual_decisions"]))
        # No source mapping is ever executable from this proposal path.
        wrong_candidates_autoaccepted += int(report["relationships_joined"] is not False or report["reads_executed"] is not False)
        result = {
            "environment": name, "descriptors_examined": report["catalog_descriptors_examined"],
            "expected_states": expected["states"],
            "actual_states": {role: report["source_role_proposals"][role]["candidate_state"] for role in expected["states"]},
            "expected_top_source_ids": expected["top_ids"],
            "actual_ranked_top_source_ids": {role: report["source_role_proposals"][role]["preferred_candidate_source_id"]
                                               for role in expected["states"]},
            "correct_abstention": all(
                (expected["top_ids"][role] is None)
                == (report["source_role_proposals"][role]["preferred_candidate_source_id"] is None)
                for role in expected["states"]
            ),
            "candidate_pairs_requiring_review": candidates_needing_review,
            "manual_decisions_required": len(report["required_manual_decisions"]),
            "automated_scan_ms": round(elapsed_ms, 3),
            "source_rows_read": False,
            "mapping_auto_approved": False,
        }
        result["fixed_answer_pass"] = bool(
            states_ok and ranking_ok and diagnostics_ok and operation_states_ok and result["correct_abstention"]
        )
        state_correct += int(states_ok)
        top_rank_correct += int(ranking_ok)
        results.append(result)

    payload = {
        "qualification": "ADVERSARIAL_SYNTHETIC_DESCRIPTOR_ONBOARDING",
        "python": platform.python_version(), "platform": platform.platform(),
        "environments": results,
        "summary": {
            "environments": len(results), "fixed_answer_passes": sum(item["fixed_answer_pass"] for item in results),
            "fixed_answer_failures": [item["environment"] for item in results if not item["fixed_answer_pass"]],
            "role_state_expectations_checked": total_expected,
            "correct_top_ranked_sources": top_rank_correct,
            "automatic_wrong_mapping_acceptances": wrong_candidates_autoaccepted,
            "source_mapping_authorized_automatically": False,
            "successful_investigations": "See official-SDK integration acceptance; not counted as human onboarding effort.",
            "human_review_time": "NOT_MEASURED",
            "manual_decisions_required_range": [min(review_decisions), max(review_decisions)],
            "mean_scan_ms": round(sum(item["automated_scan_ms"] for item in results) / len(results), 3),
            "scale_case_descriptors": results[-1]["descriptors_examined"],
        },
        "interpretation": "Cases are synthetic structural compatibility tests. Correct source meaning, authority, permissions, and company usefulness require authorized engineer review.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    if payload["summary"]["fixed_answer_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
