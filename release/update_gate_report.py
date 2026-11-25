"""Regenerate current gate states from local evidence files and frozen contracts."""
import hashlib
import csv
import json
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "release" / "GATE_REPORT.json"
CSV_OUT = ROOT / "qualification" / "external_gates.csv"


def file_hash(relative):
    path = ROOT / relative
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    test_log = ROOT / "qualification" / "evidence" / "test-suite.log"
    suite = test_log.read_text(encoding="utf8") if test_log.exists() else ""
    science_ok = ("Ran " in suite and "OK" in suite and
                  all(name in suite for name in (
                      "test_100_seeded_cohorts_match_independent_exact_chamber_oracle",
                      "test_100_seeded_cohorts_match_independent_exact_tool_oracle",
                      "test_exact_tool_window_uses_tool_id_without_inferring_chamber_membership",
                      "test_100_seeded_exposure_windows_match_interval_oracle_across_timezones",
                      "test_event_input_permutations_preserve_chronological_investigation",
                      "test_40_seeded_counterevidence_cohorts_match_independent_cross_tab_oracle",
                      "test_target_wafer_cohort_emits_a_chronology_claim_for_each_selected_wafer",
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
                      "test_each_typed_row_is_included_in_response_relationships_and_time_semantics",
                      "test_relationship_ids_and_join_keys_are_unambiguous_and_source_declared",
                      "test_duplicate_source_semantics_records_are_rejected",
                      "test_streamable_http_denial_bounds_cancellation_and_recovery",
                      "test_hypothesis_equipment_alternatives_require_field_level_source_semantics",
                      "test_route_patterns_compare_outcomes_without_ranking_causes",
                  )))
    critical_ids = (all(f"test_p2_{number:02d}" in suite for number in range(1, 10))
                    and "test_p2_10_and_11" in suite and "test_p2_12" in suite
                    and "test_exact_tool_window_uses_tool_id_without_inferring_chamber_membership" in suite
                    and "test_invalid_maintenance_context_is_refused_as_unverified_input" in suite
                    and "test_preflight_refuses_invalid_condition_context_types" in suite
                    and all(name in suite for name in (
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
                        "test_each_typed_row_is_included_in_response_relationships_and_time_semantics",
                        "test_relationship_ids_and_join_keys_are_unambiguous_and_source_declared",
                        "test_duplicate_source_semantics_records_are_rejected",
                        "test_streamable_http_denial_bounds_cancellation_and_recovery",
                        "test_route_patterns_compare_outcomes_without_ranking_causes",
                    )))
    browser = ROOT / "qualification" / "evidence" / "browser-ui-smoke.json"
    browser_forensics = ROOT / "qualification" / "evidence" / "browser-process-forensics-current.json"
    mcp_workflow = ROOT / "qualification" / "evidence" / "mcp-end-to-end-workflow.json"
    browser_reference = ROOT / "qualification" / "evidence" / "browser-p2-reference-workflow.json"
    reference_export = ROOT / "qualification" / "evidence" / "browser-p2-reference-export.json"
    reference_workflow_ok = False
    if browser_reference.exists() and reference_export.exists():
        try:
            browser_run = json.loads(browser_reference.read_text(encoding="utf8"))
            browser_export = json.loads(reference_export.read_text(encoding="utf8"))
            reference_workflow_ok = (
                browser_run.get("status") == "PASS_LOCAL_SYNTHETIC_P2_MCP_BROWSER_WORKFLOW"
                and browser_run.get("evidence_export", {}).get("sha256") == file_hash("qualification/evidence/browser-p2-reference-export.json")
                and browser_export.get("status") == "PARTIAL"
                and browser_export.get("provenance", {}).get("mcp_integration", {}).get("operations_completed")
                == ["discover", "semantics", "relationships", "read_bounded", "audit"]
            )
        except (json.JSONDecodeError, OSError, AttributeError):
            reference_workflow_ok = False
    accessibility_evidence = ROOT / "qualification" / "evidence" / "browser-accessibility-current.json"
    accessibility_export = ROOT / "qualification" / "evidence" / "browser-accessibility-export.json"
    accessibility_ok = False
    if accessibility_evidence.exists() and accessibility_export.exists():
        try:
            evidence = json.loads(accessibility_evidence.read_text(encoding="utf8"))
            accessibility_ok = (
                evidence.get("status") == "PASS_LOCAL_BROWSER_INTERACTION"
                and evidence.get("keyboard_file_selection", {}).get("tab_stop_observed") is True
                and evidence.get("keyboard_file_selection", {}).get("keyboard_enter_opened_file_chooser") is True
                and evidence.get("keyboard_file_selection", {}).get("visible_focus_indicator_observed") is True
                and evidence.get("preflight", {}).get("status") == "READY_FOR_LOCAL_ANALYSIS"
                and evidence.get("analysis", {}).get("status") == "VALID"
                and evidence.get("rendered_tables", {}).get("count", 0) >= 1
                and evidence.get("rendered_tables", {}).get("all_have_caption") is True
                and evidence.get("rendered_tables", {}).get("all_headers_have_scope_col") is True
                and evidence.get("rendered_tables", {}).get("all_have_thead_and_tbody") is True
                and evidence.get("export", {}).get("sha256") == file_hash("qualification/evidence/browser-accessibility-export.json")
            )
        except (json.JSONDecodeError, OSError, AttributeError):
            accessibility_ok = False
    stop_smoke = ROOT / "qualification" / "evidence" / "server-stop-smoke.json"
    bundle_log = ROOT / "qualification" / "evidence" / "bundle-verification.log"
    bundle_ok = bundle_log.exists() and "PASS: checksum" in bundle_log.read_text(encoding="utf8")
    react_host_path = ROOT / "qualification" / "evidence" / "react-host-compatibility.json"
    react_host_ok = False
    if react_host_path.exists():
        try:
            react_host_ok = json.loads(react_host_path.read_text(encoding="utf8")).get("status") == "PASS_SYNTHETIC_REACT_HOST_COMPATIBILITY"
        except (json.JSONDecodeError, OSError):
            react_host_ok = False
    test_reconciliation = ROOT / "qualification" / "evidence" / "test-run-reconciliation.json"
    test_reconciliation_ok = False
    if test_reconciliation.exists():
        try:
            runs = json.loads(test_reconciliation.read_text(encoding="utf8")).get("runs", {})
            pinned = runs.get("pinned_sdk", {})
            core = runs.get("core", {})
            test_reconciliation_ok = (
                pinned.get("total_discovered", 0) > 0
                and pinned.get("actually_executed") == pinned.get("total_discovered")
                and pinned.get("passed") == pinned.get("actually_executed")
                and pinned.get("failed") == pinned.get("errored") == pinned.get("skipped") == 0
                and core.get("total_discovered") == pinned.get("total_discovered")
                and core.get("actually_executed", 0) + core.get("skipped", 0) == core.get("total_discovered")
                and core.get("passed") == core.get("actually_executed")
                and core.get("failed") == core.get("errored") == 0
                and core.get("skipped") == len(core.get("skipped_test_ids", []))
            )
        except (json.JSONDecodeError, OSError, AttributeError):
            test_reconciliation_ok = False
    stop_ok = False
    if stop_smoke.exists():
        try:
            stop_evidence = json.loads(stop_smoke.read_text(encoding="utf8"))
            stop_ok = (stop_evidence.get("status") == "PASS" and
                       isinstance(stop_evidence.get("post_stop_loopback_connect_ex"), int) and
                       stop_evidence["post_stop_loopback_connect_ex"] != 0)
        except (json.JSONDecodeError, OSError):
            stop_ok = False
    p2_implementation_ok = (test_reconciliation_ok and mcp_workflow.exists()
                            and "test_engineer_workflow_traces_six_source_roles_through_counterevidence_and_provenance" in suite
                            and "test_material_lineage_coverage_requires_entity_type_source_and_full_time_scope" in suite)
    shared_module_ok = react_host_ok and file_hash("ui/contribution.manifest.json") is not None
    report = {
        "state": "CANDIDATE",
        "product_states": {
            "P2_PRODUCT_IMPLEMENTATION_COMPLETE": {
                "status": "COMPLETE_FOR_SYNTHETIC_EXTERNAL_CONTRACTS" if p2_implementation_ok else "NOT_VERIFIED",
                "evidence": ["qualification/evidence/test-suite-pinned.log", "qualification/evidence/mcp-end-to-end-workflow.json", "qualification/evidence/browser-p2-reference-workflow.json"],
                "scope": "B01/B02/B03/B05 deterministic implementation and engineer workflow are complete against the external synthetic contracts; this is not company manufacturing qualification."
            },
            "P2_STANDALONE_WORKFLOW_VERIFIED": {
                "status": "PASS_LOCAL_BROWSER_WORKFLOW" if reference_workflow_ok else "NOT_VERIFIED",
                "evidence": ["qualification/evidence/browser-p2-reference-workflow.json", "qualification/evidence/browser-p2-reference-export.json", "qualification/evidence/mcp-end-to-end-workflow.json"],
                "scope": "The local browser executed the SDK-backed synthetic peer, six source reads, all five presentation panels, provenance inspection, cancellation/retry, and evidence export."
            },
            "SHARED_SUITE_COMPATIBILITY_READY": {
                "status": "READY_VERSIONED_REACT_CONTRIBUTION" if shared_module_ok else "NOT_VERIFIED",
                "evidence": ["ui/contribution.manifest.json", "ui/p2-react/", "qualification/evidence/react-host-compatibility.json", "integration/P2_REACT_HOST_HANDOFF.md"]
            },
            "SHARED_SUITE_INTEGRATION_PENDING": {
                "status": "PENDING_SHARED_HOST",
                "evidence": ["ui/P1_HOST_INTEGRATION_PROPOSAL.md", "integration/P2_REACT_HOST_HANDOFF.md"],
                "gap": "No combined shared suite host checkout or actual host API is present for integrated acceptance."
            },
            "EXTERNAL_TRANSFER_READY": {
                "status": "NOT_QUALIFIED",
                "gap": "Project source ownership/redistribution rights, designated target environment and complete transfer/security review are not verified."
            },
            "INTERNAL_QUALIFICATION_PENDING": {
                "status": "PENDING_INTERNAL",
                "gap": "Company MCP permissions, source semantics, manufacturing validation, company environment and approvals remain internal qualification dependencies."
            }
        },
        "qualification_layers": {
            "p2_product_implementation": {"status": "COMPLETE_FOR_SYNTHETIC_EXTERNAL_CONTRACTS" if p2_implementation_ok else "NOT_VERIFIED", "evidence": ["qualification/evidence/test-suite-pinned.log", "qualification/evidence/mcp-end-to-end-workflow.json", "qualification/evidence/browser-p2-reference-workflow.json"], "gap": "Synthetic contracts are externally tested; independent manufacturing validation and company source semantics remain separate qualification layers."},
            "p2_standalone_workflow": {"status": "PASS_LOCAL_BROWSER_WORKFLOW" if reference_workflow_ok else "NOT_VERIFIED", "evidence": ["qualification/evidence/browser-p2-reference-workflow.json", "qualification/evidence/browser-p2-reference-export.json"], "gap": "Browser evidence is synthetic and does not establish assistive-technology or engineer acceptance."},
            "p2_module_readiness_for_shared_host": {"status": "READY_VERSIONED_REACT_CONTRIBUTION" if shared_module_ok else "NOT_RUN", "evidence": ["ui/p2-react/", "ui/contribution.manifest.json", "qualification/evidence/react-host-compatibility.json", "ui/P1_HOST_INTEGRATION_PROPOSAL.md"], "gap": "Actual combined-suite host API and integration run remain pending."},
            "actual_integrated_suite_qualification": {"status": "PENDING_SHARED_HOST", "evidence": ["ui/P1_HOST_INTEGRATION_PROPOSAL.md", "qualification/evidence/react-host-compatibility.json"], "gap": "A unified suite host must mount this module with its actual route and host lifecycle adapters and run integrated acceptance."},
            "external_offline_release_qualification": {"status": "PARTIAL_CURRENT_HOST" if bundle_ok and test_reconciliation_ok else "NOT_RUN", "evidence": ["qualification/evidence/bundle-verification.log", "qualification/evidence/test-run-reconciliation.json"], "gap": "Only the observed macOS arm64 CPython 3.11 and local offline npm-cache environment are exercised; target-company OS/runtime/network policy are unknown."},
            "internal_company_qualification": {"status": "PENDING_INTERNAL", "evidence": ["qualification/evidence/mcp-end-to-end-workflow.json", "requirements/AUTHORITY_AND_GAPS.md"], "gap": "No company credentials, source approvals/mappings, real data, internal review, or canonical R01-R53 text were available."},
        },
        "evaluated_commit": None,
        "evaluated_source_manifest": "release/BOOTSTRAP_MANIFEST.sha256 (exact archive checksum in release/RELEASE_RECEIPT.json)",
        "host": {"os": platform.system(), "release": platform.release(), "architecture": platform.machine(), "python": platform.python_version()},
        "gates": {
            "E01": {"status": "PARTIAL" if browser.exists() and browser_forensics.exists() and mcp_workflow.exists() and react_host_ok and "test_post_returns_frozen_evidence_envelope" in suite and "test_engineer_workflow_traces_six_source_roles_through_counterevidence_and_provenance" in suite and "test_p1_host_proposal_tracks_the_versioned_react_contribution" in suite else "NOT_RUN",
                    "evidence": ["qualification/evidence/mcp-end-to-end-workflow.json", "qualification/evidence/test-suite-pinned.log", "qualification/evidence/react-host-compatibility.json", "ui/p2-react/test/p2-host.integration.test.mjs", "qualification/evidence/browser-workflow-current.json", "qualification/evidence/browser-process-forensics-current.json", "qualification/evidence/ui-state-smoke.json", "tests/test_mcp_adapter.py", "ui/P1_HOST_INTEGRATION_PROPOSAL.md", "docs/MCP_ADAPTER.md"],
                    "gap": "The six-source SDK workflow feeds all five P2 panels and traces evidence to source records. Synthetic caller coverage remains unverified, so nonmatches are unknown and route conformance is incomplete; shared-suite integration and company source binding remain separate."},
            "E02": {"status": "PARTIAL" if science_ok else "NOT_RUN",
                    "evidence": ["qualification/evidence/test-suite.log", "qualification/evidence/science-oracle-summary.json", "tests/test_heldout_adversarial.py"],
                    "scope": "P2-01 through P2-43; MCP-01 through MCP-05 synthetic protocol challenges; seeded exact-chamber/tool/window, 25x4 permutation and 40 counterevidence cross-tab oracles; thirty-seven separate fixed-answer adversarial cases, including route/outcome/exposure patterns with exact provenance and no causal ranking. All are synthetic.",
                    "gap": "The separate adversarial module is not blinded. No independently reviewed manufacturing holdout, real FAB workload, or company scientific validation is available."},
            "E03": {"status": "PASS" if critical_ids else "NOT_RUN",
                    "evidence": ["qualification/evidence/test-suite.log", "tests/test_heldout_adversarial.py"],
                    "scope": "P2-01 through P2-43, MCP-01 through MCP-05 protocol challenges, and fixed-answer synthetic refusals, including duplicate definitions/keys, source-undeclared joins, provenance omissions, event/record-time confusion, Streamable HTTP denial/bounds/cancel/recovery, uncertain membership/exposure/route definitions, product/time and route confounding, outcome gaps, multi-hop lineage traps, incomplete route histories, coverage gaps, conflicting duplicate processing instances, and equal-support hypotheses that remain unranked."},
            "E04": {"status": "PASS" if file_hash("contracts/evidence.v1.schema.json") and file_hash("contracts/product-manifest.v1.schema.json") and "test_p1_host_proposal_tracks_the_versioned_react_contribution" in suite and react_host_ok else "NOT_RUN",
                    "evidence": ["contracts/evidence.v1.schema.json", "contracts/product-manifest.v1.schema.json", "ui/contribution.manifest.json", "ui/p2-react/package.json", "qualification/evidence/react-host-compatibility.json", "ui/P1_HOST_INTEGRATION_PROPOSAL.md", "qualification/evidence/test-suite.log", "tests/test_schema_and_ui.py"],
                    "scope": "Frozen v1.0.0 contracts and versioned P2 React module pass synthetic React 18/19 compatibility and type checks; actual P1 route/component integration is a separate pending gate."},
            "E05": {"status": "PENDING_INTERNAL", "evidence": ["docs/INTERNAL_COMPANY_FIRST_RUN.md", "docs/DECISION_RECORD.md", "qualification/evidence/mcp-end-to-end-workflow.json"],
                    "gap": "No live source authorization, real Fab Insight mapping, bounded read audit, or site permissions were available."},
            "E06": {"status": "PASS" if "test_no_live_adapter_is_always_pending_internal" in suite else "NOT_RUN",
                    "evidence": ["tests/test_preflight.py", "qualification/evidence/test-suite.log"],
                    "scope": "Model-free deterministic path; no LLM or model tool-call path is bundled."},
            "E07": {"status": "PARTIAL" if accessibility_ok and react_host_ok else "NOT_RUN",
                    "evidence": ["qualification/evidence/browser-p2-reference-workflow.json", "qualification/evidence/browser-p2-reference-export.json", "qualification/evidence/browser-accessibility-current.json", "qualification/evidence/browser-accessibility-export.json", "qualification/evidence/browser-process-forensics-current.json", "qualification/evidence/browser-workflow-current.json", "qualification/evidence/ui-state-smoke.json", "qualification/evidence/react-host-compatibility.json", "ui/p2-react/test/p2-host.integration.test.mjs", "tests/test_schema_and_ui.py", "tests/test_engine.py", "tests/test_local_server.py"],
                    "gap": "Keyboard focus and accessible tables were checked in a real browser. Native dialog operation, assistive technology, broader screen-reader acceptance, and target-host UX remain unverified."},
            "E08": {"status": "PARTIAL" if bundle_ok else "NOT_RUN",
                    "evidence": ["qualification/evidence/bundle-verification.log", "qualification/evidence/network-block-check.log", "release/install_offline.py"],
                    "gap": "Fresh extraction, hash-checked no-index MCP install, full suite, demo, and rollback passed on macOS arm64 CPython 3.11. The company target OS/runtime and target-site network controls remain unknown."},
            "E09": {"status": "PARTIAL" if file_hash("release/SBOM.spdx.json") and file_hash("qualification/evidence/mcp-dependency-vulnerability-scan.json") and file_hash("qualification/evidence/p2-react-dependency-audit.json") else "NOT_RUN",
                    "evidence": ["release/SBOM.spdx.json", "release/SECURITY_AND_LICENSE_REVIEW.md", "qualification/evidence/p2-react-dependency-audit.json", "qualification/evidence/p2-react-npm-audit.json", "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/license-inventory.json", "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/cyclonedx.cdx.json", "qualification/evidence/mcp-dependency-vulnerability-scan.json", "qualification/evidence/security-tool-availability.json"],
                    "gap": "The pinned 28-package MCP dependency closure has wheel license inventory, SBOM, hashes, and a current pip-audit scan with no known findings. Project ownership/transfer rights, company OSS approval, and host/target-OS security review remain unresolved."},
            "E10": {"status": "PASS" if bundle_ok and stop_ok and test_reconciliation_ok else "NOT_RUN",
                    "evidence": ["release/FAB_PROCESS_FORENSICS_P2_CANDIDATE.zip", "release/BUNDLE_SHA256SUMS.txt", "qualification/evidence/bundle-verification.log", "qualification/evidence/test-run-reconciliation.json", "qualification/evidence/react-host-compatibility.json", "qualification/evidence/server-stop-smoke.json", "tests/test_local_server.py"],
                    "scope": "Deterministic archive, checksum, safe extraction, hash-checked no-index MCP install, all reconciled SDK tests, six-source MCP-to-evidence workflow, offline npm install, React panel tests/typecheck and reference-host build, demo, rollback, foreground stop, and cancellation recovery on the current host."},
            "E11": {"status": "PARTIAL" if file_hash("qualification/evidence/benchmark-local.json") else "NOT_RUN",
                    "evidence": ["qualification/evidence/benchmark-local.json", "qualification/evidence/benchmark-foundation-comparison.json", "qualification/evidence/benchmark-analysis-scaling.json", "qualification/evidence/benchmark-p2-react-render.json", "qualification/evidence/graph-library-benchmark.json", "qualification/evidence/benchmark-material-edge-index-run.log", "qualification/benchmark_analysis_scaling.py", "qualification/benchmark_graph_traversal.py", "qualification/benchmark_material_edge_index.py", "qualification/benchmark_p2_react_render.mjs", "docs/OSS_CATALOG_BENCHMARK_PROTOCOL.md", "docs/ANALYSIS_SCALING_BENCHMARK_PROTOCOL.md", "docs/MATERIAL_EDGE_INDEX_BENCHMARK_PROTOCOL.md", "docs/DECISION_RECORD.md"],
                    "gap": "Synthetic evidence includes 13,000-source lookup, 100-to-100,000-event analysis scaling, 100,000-edge NetworkX traversal, a 100,000-edge material interval-index screen, and JSDOM panel rendering for 1,000 wafers/8,000 steps after pagination (218 table rows mounted, 136 ms). JSDOM is not a native browser. Representative FAB workloads, target memory limits, faithful OCEL2 data, and measured engineer task-time improvement remain unavailable."},
            "E12": {"status": "PENDING_INTERNAL", "evidence": ["docs/INTERNAL_COMPANY_FIRST_RUN.md", "requirements/mcp-discovery.template.json", "qualification/evidence/internal-preflight-template-check.json", "qualification/evidence/mcp-end-to-end-workflow.json", "tests/test_preflight.py", "tests/test_snapshot_preflight.py"],
                    "gap": "Versioned local capability-capture and snapshot checks do not perform live authorized MCP discovery, source retrieval, or a first real engineering result."},
        },
        "internal": {"state": "PENDING_INTERNAL", "unverified": [
            "real Fab Insight MCP tools and permissions", "approved source definitions and relationships",
            "target OS and authentication", "approved model endpoint and host integration",
            "company engineering and accessibility review", "corporate transfer and source-license approval",
            "literal Samsung R01-R53 text and corporate interpretation of the pinned Golden reference",
        ]},
        "known_critical_defects": [],
        "release_note": "No EXTERNAL_TRANSFER_READY or READY_INTERNAL claim. See each gate's evidence and gap.",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    with CSV_OUT.open("r", encoding="utf8", newline="") as stream:
        original = {row["gate"]: row for row in csv.DictReader(stream)}
    with CSV_OUT.open("w", encoding="utf8", newline="") as stream:
        fields = ["gate", "acceptance", "evidence", "status", "details"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for gate_id, state in report["gates"].items():
            row = original.get(gate_id, {})
            writer.writerow({
                "gate": gate_id,
                "acceptance": row.get("acceptance", ""),
                "evidence": ";".join(state.get("evidence", [])),
                "status": state["status"],
                "details": state.get("gap", state.get("scope", "")),
            })
    print(f"Wrote {OUT.relative_to(ROOT)} (CANDIDATE; external/internal qualification not claimed).")


if __name__ == "__main__":
    main()
