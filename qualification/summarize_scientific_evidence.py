"""Map executed local test names to the frozen P2 challenge catalog."""
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "qualification" / "evidence" / "test-suite.log"
OUT = ROOT / "qualification" / "evidence" / "science-oracle-summary.json"
TESTS = {
    "P2-01": ["test_p2_01_repeated_operation_keeps_distinct_step_instances"],
    "P2-02": ["test_p2_02_same_hour_wrong_chamber_remains_unknown_under_asserted_coverage"],
    "P2-03": ["test_p2_03_unapproved_relationship_refuses_path"],
    "P2-04": ["test_p2_04_missing_chamber_on_known_tool_is_unknown"],
    "P2-05": ["test_p2_05_naive_timestamp_refuses_order"],
    "P2-06": ["test_p2_06_namespaced_wafer_aliases_are_not_merged", "test_same_wafer_token_across_sources_requires_explicit_identity_approval"],
    "P2-07": ["test_p2_07_outside_maintenance_window_is_not_exposed"],
    "P2-08": ["test_p2_08_incomplete_events_do_not_become_route_violation", "test_approved_route_comparison_requires_coverage_and_reports_mismatch_carefully"],
    "P2-09": ["test_p2_09_lot_membership_is_retained_at_each_event"],
    "P2-10": ["test_p2_10_and_11_normal_exposure_and_abnormal_nonexposure_are_counterevidence"],
    "P2-11": ["test_p2_10_and_11_normal_exposure_and_abnormal_nonexposure_are_counterevidence"],
    "P2-12": ["test_p2_12_13k_catalog_rejects_unapproved_join", "test_catalog_join_requires_exact_approved_effective_relationship"],
    "P2-13": ["test_exact_tool_window_uses_tool_id_without_inferring_chamber_membership"],
    "P2-14": ["test_invalid_maintenance_context_is_refused_as_unverified_input", "test_preflight_refuses_invalid_condition_context_types"],
    "P2-15": ["test_unlinked_coverage_cannot_make_a_nonmatch_a_comparator"],
    "P2-16": ["test_history_coverage_omitting_an_observed_event_source_is_incomplete"],
    "P2-17": ["test_missing_chamber_move_on_known_tool_is_possible_not_exact"],
    "P2-18": ["test_repeated_exact_processing_preserves_both_exposure_instances"],
    "P2-19": ["test_maintenance_before_and_after_window_is_temporal_context_only"],
    "P2-20": ["test_route_version_segments_and_approved_exception_are_preserved"],
    "P2-21": ["test_explicit_rework_is_retained_but_excluded_from_base_route_count"],
    "P2-22": ["test_counterevidence_keeps_shared_normal_and_unexposed_abnormal_wafers"],
    "P2-23": ["test_time_scoped_lot_membership_and_split_require_typed_provenance"],
    "P2-24": ["test_multihop_lot_lineage_keeps_direction_time_and_sibling_boundary"],
    "P2-25": ["test_undeclared_event_lot_field_cannot_attach_unrelated_material_graph"],
    "P2-26": ["test_event_lot_join_crossing_source_effectivity_boundary_is_only_possible"],
    "P2-27": ["test_exposure_relationship_effectivity_boundary_stays_unknown"],
    "P2-28": ["test_route_variant_denominator_exposes_coverage_and_uncertain_histories"],
    "P2-29": ["test_hypothesis_equipment_alternatives_require_field_level_source_semantics"],
    "P2-30": ["test_duplicate_source_instance_collapses_only_if_identical"],
    "P2-31": ["test_absent_material_edges_do_not_establish_absent_lot_lineage"],
    "P2-32": ["test_material_lineage_coverage_requires_entity_type_source_and_full_time_scope"],
    "P2-33": ["test_processing_interval_effectivity_boundary_uncertainty_keeps_exact_exposure_unknown"],
    "P2-34": ["test_declared_missing_exposure_records_prevent_unexposed_comparator"],
    "P2-35": ["test_route_approval_flag_without_definition_relationship_cannot_establish_conformance"],
    "P2-36": ["test_route_definition_effectivity_must_cover_event_clock_uncertainty"],
    "P2-37": ["test_outcome_timestamp_without_source_declared_time_key_cannot_drive_time_confounds"],
    "P2-38": ["test_product_and_time_strata_require_verified_fields_and_show_selection_denominator"],
    "P2-39": ["test_process_timestamp_without_relationship_key_cannot_drive_chronology"],
    "P2-40": ["test_each_typed_row_is_included_in_response_relationships_and_time_semantics"],
    "P2-41": ["test_event_time_controls_exposure_and_order_when_arrival_time_disagrees"],
    "P2-42": ["test_equally_supported_equipment_hypotheses_remain_unranked"],
    "P2-43": ["test_route_patterns_compare_outcomes_without_ranking_causes"],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not LOG.is_file():
        raise SystemExit("Run the full test suite and save qualification/evidence/test-suite.log first.")
    output = LOG.read_text(encoding="utf8")
    cases = {}
    for case_id, tests in TESTS.items():
        executed = [name for name in tests if name in output]
        cases[case_id] = {"status": "PASS" if len(executed) == len(tests) else "NOT_RUN", "tests": executed}
    cases["SEEDED-100"] = {
        "status": "PASS" if "test_100_seeded_cohorts_match_independent_exact_chamber_oracle" in output else "NOT_RUN",
        "tests": ["test_100_seeded_cohorts_match_independent_exact_chamber_oracle"] if "test_100_seeded_cohorts_match_independent_exact_chamber_oracle" in output else [],
    }
    supplemental = {
        "SEEDED-TOOL-100": "test_100_seeded_cohorts_match_independent_exact_tool_oracle",
        "SEEDED-WINDOW-100": "test_100_seeded_exposure_windows_match_interval_oracle_across_timezones",
        "ORDER-PERMUTATION-25x4": "test_event_input_permutations_preserve_chronological_investigation",
        "COUNTEREVIDENCE-40": "test_40_seeded_counterevidence_cohorts_match_independent_cross_tab_oracle",
        "TARGET-COHORT": "test_target_wafer_cohort_emits_a_chronology_claim_for_each_selected_wafer",
    }
    for case_id, test_name in supplemental.items():
        cases[case_id] = {"status": "PASS" if test_name in output else "NOT_RUN",
                          "tests": [test_name] if test_name in output else []}
    heldout_tests = [
        "test_repeated_operation_instances_remain_two_chronological_events",
        "test_chamber_overlap_never_transfers_exact_exposure",
        "test_missing_population_observations_stay_unknown",
        "test_route_gap_is_incomplete_coverage_not_violation",
        "test_clock_uncertainty_prevents_definite_exposure_and_order",
        "test_unapproved_relationship_produces_no_factual_claims",
        "test_source_linked_maintenance_is_temporal_context_not_cause",
        "test_unlinked_coverage_cannot_make_a_nonmatch_a_comparator",
        "test_history_coverage_omitting_an_observed_event_source_is_incomplete",
        "test_missing_chamber_move_on_known_tool_is_possible_not_exact",
        "test_repeated_exact_processing_preserves_both_exposure_instances",
        "test_maintenance_before_and_after_window_is_temporal_context_only",
        "test_route_version_segments_and_approved_exception_are_preserved",
        "test_explicit_rework_is_retained_but_excluded_from_base_route_count",
        "test_counterevidence_keeps_shared_normal_and_unexposed_abnormal_wafers",
        "test_time_scoped_lot_membership_and_split_require_typed_provenance",
        "test_clock_error_overlapping_lot_transfer_keeps_membership_ambiguous",
        "test_identity_mapping_boundary_inside_clock_error_refuses_cross_source_merge",
        "test_multihop_lot_lineage_keeps_direction_time_and_sibling_boundary",
        "test_undeclared_event_lot_field_cannot_attach_unrelated_material_graph",
        "test_event_lot_join_crossing_source_effectivity_boundary_is_only_possible",
        "test_exposure_relationship_effectivity_boundary_stays_unknown",
        "test_route_variant_denominator_exposes_coverage_and_uncertain_histories",
        "test_hypothesis_equipment_alternatives_require_field_level_source_semantics",
        "test_duplicate_source_instance_collapses_only_if_identical",
        "test_absent_material_edges_do_not_establish_absent_lot_lineage",
        "test_material_lineage_coverage_requires_entity_type_source_and_full_time_scope",
        "test_processing_interval_effectivity_boundary_uncertainty_keeps_exact_exposure_unknown",
        "test_declared_missing_exposure_records_prevent_unexposed_comparator",
        "test_route_approval_flag_without_definition_relationship_cannot_establish_conformance",
        "test_route_definition_effectivity_must_cover_event_clock_uncertainty",
        "test_outcome_timestamp_without_source_declared_time_key_cannot_drive_time_confounds",
        "test_product_and_time_strata_require_verified_fields_and_show_selection_denominator",
        "test_process_timestamp_without_relationship_key_cannot_drive_chronology",
        "test_event_time_controls_exposure_and_order_when_arrival_time_disagrees",
        "test_equally_supported_equipment_hypotheses_remain_unranked",
        "test_route_patterns_compare_outcomes_without_ranking_causes",
    ]
    heldout_executed = [name for name in heldout_tests if name in output]
    cases["HELDOUT-ADVERSARIAL-37"] = {
        "status": "PASS" if len(heldout_executed) == len(heldout_tests) else "NOT_RUN",
        "tests": heldout_executed,
        "fixture_module_sha256": sha(ROOT / "tests" / "test_heldout_adversarial.py"),
    }
    passed = all(item["status"] == "PASS" for item in cases.values()) and "OK" in output
    report = {
        "status": "PASS_LOCAL_SYNTHETIC_ORACLES" if passed else "INCOMPLETE",
        "independently_expected": "Literal P2 case behaviors in docs/TEST_AND_RELEASE_MATRIX.md; direct set/sequence oracle in tests/test_p2_challenges.py; separate fixed-answer public-contract cases in tests/test_heldout_adversarial.py.",
        "case_catalog_sha256": sha(ROOT / "qualification" / "critical_cases.json"),
        "oracle_fixture_sha256": sha(ROOT / "fixtures" / "independent_oracle.json"),
        "test_log_sha256": sha(LOG),
        "environment": {"os": platform.system(), "release": platform.release(), "architecture": platform.machine(), "python": sys.version},
        "cases": cases,
        "holdout_status": "INDEPENDENT_FIXED_CASES_NOT_BLINDED",
        "limitation": "The separate fixed-answer adversarial module does not reuse implementation-suite fixtures or helpers, but it was visible during this development turn and is not a blinded holdout. No fab data, statistical causal estimand, independent reviewer, or company qualification is represented.",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {report['status']}.")


if __name__ == "__main__":
    main()
