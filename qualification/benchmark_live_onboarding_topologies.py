"""Fixed-answer official-SDK benchmark for structurally different MCP metadata."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fabintel.onboarding_pipeline import (
    materialize_live_review, propose_from_live_mcp_metadata, verify_materialized_config,
)


ORACLE = ROOT / "qualification/fixtures/live_onboarding_topologies_expected_v1.json"
OUTPUT = ROOT / "qualification/evidence/onboarding-live-topologies-2026-11-24.json"
WINDOW = {"start": "2026-11-21T00:00:00Z", "end": "2026-11-22T00:00:00Z"}
ROLES = ("events", "outcomes", "coverage", "history_coverage", "route_definitions",
         "route_coverage", "material_relationships")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False).encode()).hexdigest()


def _diagnostic(candidate: dict, code: str) -> bool:
    return any(item.get("code") == code for item in candidate.get("diagnostics", []))


async def run() -> dict:
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    if oracle.get("expectations_authored_before_mapper_run") is not True:
        raise SystemExit("Fixed-answer oracle must precede mapper execution.")
    sdk_path = os.environ.get("P2_TEST_SDK_PATH")
    if not sdk_path:
        raise SystemExit("Set P2_TEST_SDK_PATH to the pinned offline MCP SDK environment.")

    results = []
    for environment in oracle["environments"]:
        topology = environment["topology"]
        transport = {
            "kind": "stdio", "command": sys.executable,
            "args": ["-m", "fabintel.synthetic_mcp_server", "--descriptor-topology", topology],
            "cwd": str(ROOT), "environment": {"PYTHONPATH": "P2_TEST_SDK_PATH"},
        }
        started = time.perf_counter()
        report = await propose_from_live_mcp_metadata(
            transport, time_window=WINDOW, environment={"P2_TEST_SDK_PATH": sdk_path},
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        capture, proposal = report["capture"], report["proposal"]
        if not report["metadata_only"] or report["bounded_row_reads_executed"]:
            raise AssertionError(f"{topology}: discovery read rows or was not metadata-only")
        if capture["metadata_source_count"] != len(capture["sources"]):
            raise AssertionError(f"{topology}: source discovery/semantics count mismatch")
        if capture["metadata_semantics_batch_count"] != 1:
            raise AssertionError(f"{topology}: unexpected semantics batching for small catalog")
        if environment.get("misleading_source_name"):
            named = [item for item in capture["sources"]
                     if item.get("source_name") == environment["misleading_source_name"]]
            if len(named) != 1:
                raise AssertionError(f"{topology}: misleading source name was not exposed by the peer")
            if any(candidate.get("source_id") == named[0]["source_id"]
                   for role in proposal["source_role_proposals"].values()
                   for candidate in role.get("candidates", [])):
                raise AssertionError(f"{topology}: source-name similarity overrode missing semantics")
        if topology == "duplicate-event-version":
            duplicate_versions = {item["source_id"]: item["semantic_version"]
                                  for item in capture["sources"]
                                  if item["source_id"] in {"SYN_PROCESS", "SYN_PROCESS_OLDER_SEMANTICS"}}
            if duplicate_versions != {"SYN_PROCESS": "SYN-SEM-1",
                                      "SYN_PROCESS_OLDER_SEMANTICS": "SYN-SEM-2025.1"}:
                raise AssertionError(f"{topology}: semantic versions were flattened: {duplicate_versions}")

        role_results, false_accepts, correct = {}, [], 0
        for role, expected in environment["expected_roles"].items():
            actual = proposal["source_role_proposals"][role]
            ranked = actual["ranked_candidate_source_ids"]
            actual_sources = sorted(ranked)
            expected_sources = sorted(expected["source_ids"])
            match = actual["candidate_state"] == expected["state"] and actual_sources == expected_sources
            candidate_by_source = {item.get("source_id"): item
                                   for item in actual.get("candidates", [])}
            if expected.get("candidate_state"):
                match = match and all(candidate_by_source[source]["candidate_state"] == expected["candidate_state"]
                                      for source in expected["source_ids"])
            if "preferred_source_id" in expected:
                match = match and actual["preferred_candidate_source_id"] == expected["preferred_source_id"]
            if expected.get("missing_field"):
                candidate = candidate_by_source[expected_sources[0]]
                match = match and candidate["field_mapping"].get(expected["missing_field"]) is None
            if expected.get("diagnostic"):
                diagnostic_candidates = ([candidate_by_source[source] for source in expected_sources]
                                          if expected_sources else actual.get("candidates", []))
                match = match and any(_diagnostic(candidate, expected["diagnostic"])
                                      for candidate in diagnostic_candidates)
            if not match:
                false_accepts.append({"role": role, "expected": expected,
                                      "actual_state": actual["candidate_state"],
                                      "actual_ranked_source_ids": ranked})
            else:
                correct += 1
            role_results[role] = {
                "expected": expected, "actual_state": actual["candidate_state"],
                "ranked_source_ids": ranked,
                "preferred_source_id": actual["preferred_candidate_source_id"],
                "fixed_answer_pass": match,
            }

        metrics = {
            "elapsed_mcp_discovery_and_mapping_ms": round(elapsed_ms, 3),
            "tool_discovery_ms": round(report["performance_metrics"]["tool_descriptor_inspection_ms"], 3),
            "source_discovery_ms": round(report["performance_metrics"]["mcp_discover_ms"], 3),
            "semantics_ms": round(report["performance_metrics"]["source_semantics_ms"], 3),
            "relationships_ms": round(report["performance_metrics"]["source_relationships_ms"], 3),
            "mapping_ms": round(report["performance_metrics"]["source_mapping_ms"], 3),
            "descriptors_examined": capture["metadata_source_count"],
        }
        if false_accepts:
            raise AssertionError(f"{topology}: false source mapping/abstention result: {false_accepts}")

        approval_result = "NOT_ATTEMPTED"
        review_mode = "NOT_APPROVED"
        selected_source_role_fields = None
        unresolved_role_questions = sum(
            value["expected"]["state"] != "UNIQUE_REVIEW_REQUIRED"
            for value in role_results.values()
        )
        if topology == "standard":
            approval = {
                "decision": "APPROVE_EXACT_PROPOSAL", "reviewer_id": f"synthetic-review-{topology}",
                "proposal_sha256": report["proposal_sha256"], "time_window": WINDOW,
                "descriptor_capture_sha256": report["descriptor_capture_sha256"],
                "limits": capture["limits"], "permission_scope": "SYNTHETIC_READ",
            }
            config = materialize_live_review(report, approval)
            verify_materialized_config(config, proposal)
            approval_result = "DIGEST_BOUND_SYNTHETIC_REVIEW_VALIDATED"
            review_mode = "ONE_EXACT_PROPOSAL_REVIEW_RECORD"
            selected_source_role_fields = 0
            if config["server_authorization_established"] is not False:
                raise AssertionError("Synthetic review was incorrectly treated as server authorization.")
        elif topology == "equipment-group-only":
            approval = {
                "decision": "APPROVE_EXACT_PROPOSAL", "reviewer_id": f"synthetic-review-{topology}",
                "proposal_sha256": report["proposal_sha256"], "time_window": WINDOW,
                "descriptor_capture_sha256": report["descriptor_capture_sha256"],
                "limits": capture["limits"], "permission_scope": "SYNTHETIC_READ",
            }
            try:
                materialize_live_review(report, approval)
            except ValueError as error:
                if "cannot acknowledge partial source role events" not in str(error):
                    raise
            else:
                raise AssertionError("Partial chamber semantics passed the exact approval shortcut")
            explicit_sources = {}
            for role in ROLES:
                candidate = next(item for item in proposal["source_role_proposals"][role]["candidates"]
                                 if item.get("candidate_state") in {
                                     "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED",
                                     "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED",
                                 })
                explicit_sources[role] = {
                    "source_id": candidate["source_id"],
                    "relationship_id": candidate["relationship_id"],
                    "acknowledge_missing_optional": candidate.get("missing_optional_fields", []),
                }
            explicit_tools = {
                operation: proposal["operation_proposals"][operation]["candidate_tool_names"][0]
                for operation in ("discover", "semantics", "relationships", "read_bounded", "cancel", "audit")
            }
            explicit_decision = {
                "decision": "APPROVE", "reviewer_id": f"synthetic-review-{topology}",
                "selected_tools": explicit_tools, "selected_sources": explicit_sources,
                "descriptor_capture_sha256": report["descriptor_capture_sha256"],
                "time_window": WINDOW, "limits": capture["limits"],
                "permission_scope": "SYNTHETIC_READ",
            }
            config = materialize_live_review(report, explicit_decision)
            verify_materialized_config(config, proposal)
            selected_event = config["reviewed_decisions"]["selected_sources"]["events"]
            if set(selected_event["acknowledge_missing_optional"]) != {"chamber_id", "tool_id"}:
                raise AssertionError("Explicit review did not acknowledge both missing event fields")
            approval_result = "EXPLICIT_PARTIAL_MAPPING_REVIEW_VALIDATED"
            review_mode = "ONE_DETAILED_SYNTHETIC_REVIEW_RECORD"
            selected_source_role_fields = len(explicit_sources)
            unresolved_role_questions = 1
            if config["server_authorization_established"] is not False:
                raise AssertionError("Synthetic review was incorrectly treated as server authorization.")
        else:
            approval = {
                "decision": "APPROVE_EXACT_PROPOSAL", "reviewer_id": f"synthetic-review-{topology}",
                "proposal_sha256": report["proposal_sha256"], "time_window": WINDOW,
                "descriptor_capture_sha256": report["descriptor_capture_sha256"],
                "limits": capture["limits"], "permission_scope": "SYNTHETIC_READ",
            }
            try:
                materialize_live_review(report, approval)
            except ValueError:
                approval_result = "CORRECTLY_REJECTED_UNRESOLVED_MAPPING"
            else:
                raise AssertionError(f"{topology}: unresolved mapping passed exact proposal review")

        results.append({
            "environment": topology, "fixed_answer_pass": True,
            "role_expectations_checked": len(environment["expected_roles"]),
            "correct_role_decisions": correct, "false_mapping_acceptances": len(false_accepts),
            "abstained_roles": sum(value["actual_state"] != "UNIQUE_REVIEW_REQUIRED"
                                    for value in role_results.values()),
            "synthetic_review_mode": review_mode,
            "selected_source_role_fields_in_successful_review": selected_source_role_fields,
            "unresolved_role_questions": unresolved_role_questions,
            "mapping_auto_approved": False,
            "source_rows_read_during_discovery": False,
            "approval_boundary": approval_result,
            "descriptor_capture_sha256": _digest(capture),
            "proposal_sha256": report["proposal_sha256"],
            "performance": metrics, "roles": role_results,
        })

    result = {
        "schema_version": "p2-live-onboarding-topology-benchmark/v1",
        "benchmark_date": datetime.now(timezone.utc).date().isoformat(),
        "fixed_answer_oracle": str(ORACLE.relative_to(ROOT)),
        "mcp_protocol": "official SDK synthetic stdio peer",
        "environments": results,
        "summary": {
            "environments_passed": sum(item["fixed_answer_pass"] for item in results),
            "environments_total": len(results),
            "role_expectations_checked": sum(item["role_expectations_checked"] for item in results),
            "false_mapping_acceptances": sum(item["false_mapping_acceptances"] for item in results),
            "mapping_auto_approvals": sum(item["mapping_auto_approved"] for item in results),
            "source_reads_during_discovery": sum(item["source_rows_read_during_discovery"] for item in results),
            "successful_synthetic_review_records": sum(item["approval_boundary"] in {
                "DIGEST_BOUND_SYNTHETIC_REVIEW_VALIDATED", "EXPLICIT_PARTIAL_MAPPING_REVIEW_VALIDATED"
            } for item in results),
            "individual_source_role_fields_selected_in_successful_reviews": sum(
                item["selected_source_role_fields_in_successful_review"] or 0 for item in results
            ),
            "environments_needing_additional_semantic_or_relationship_evidence": sum(
                item["approval_boundary"] == "CORRECTLY_REJECTED_UNRESOLVED_MAPPING" for item in results
            ),
        },
        "qualification_boundary": "Synthetic source descriptors and synthetic reviewer records only; no company authority, permission, source semantics, or manufacturing evidence is established.",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2, sort_keys=True))
