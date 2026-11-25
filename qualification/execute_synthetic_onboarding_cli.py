"""Exercise the documented onboarding CLI against an authorized mock MCP peer."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "qualification/evidence/onboarding-cli-100-alias-e2e-2026-11-24.json"
EVIDENCE_GZIP = ROOT / "qualification/evidence/onboarding-cli-100-alias-evidence.json.gz"
WINDOW = {"start": "2026-11-20T00:00:00Z", "end": "2026-11-30T00:00:00Z"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_cli(env: dict[str, str], *args: str) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-m", "fabintel", *args], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=90,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if completed.returncode:
        raise RuntimeError(
            f"CLI step failed ({args[0]}): exit={completed.returncode}\n"
            f"stdout={completed.stdout[-2000:]}\nstderr={completed.stderr[-3000:]}"
        )
    return elapsed_ms


def main() -> int:
    sdk_path = os.environ.get("P2_TEST_SDK_PATH")
    if not sdk_path or not Path(sdk_path).is_dir():
        raise SystemExit("Set P2_TEST_SDK_PATH to the pinned offline MCP SDK environment.")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), sdk_path, env.get("PYTHONPATH", ""))))

    with tempfile.TemporaryDirectory(prefix="p2-onboarding-cli-") as tmp:
        workspace = Path(tmp)
        transport = {
            "transport": {
                "kind": "stdio", "command": sys.executable,
                "args": ["-m", "fabintel.synthetic_mcp_server", "--tool-prefix", "site__",
                         "--scenario", "engineer-100-alt-alias"],
                "cwd": str(ROOT), "environment": {"PYTHONPATH": "P2_TEST_SDK_PATH"},
            },
            "request_timeout_seconds": 20,
            "max_response_bytes": 8 * 1024 * 1024,
        }
        transport_path = workspace / "synthetic-transport.json"
        proposal_path, decisions_path = workspace / "proposal.json", workspace / "review.json"
        config_path, scope_path = workspace / "approved-config.json", workspace / "scope.json"
        evidence_path = workspace / "evidence.json"
        transport_path.write_text(json.dumps(transport, indent=2) + "\n", encoding="utf-8")

        stage_times = {}
        stage_times["descriptor_discovery_and_mapping_ms"] = _run_cli(
            env, "onboard-live", "--transport", str(transport_path),
            "--start", WINDOW["start"], "--end", WINDOW["end"],
            "--output", str(proposal_path),
        )
        proposal_report = json.loads(proposal_path.read_text(encoding="utf-8"))
        if not proposal_report["metadata_only"] or proposal_report["bounded_row_reads_executed"]:
            raise AssertionError("onboard-live must inspect descriptors without reading source rows")
        if proposal_report["capture"]["metadata_source_count"] != 7:
            raise AssertionError("The fixed synthetic environment should expose seven source roles")
        expected_aliases = {
            "events": "PLANT7_ACTUAL_RUNS", "outcomes": "QDATA_WAFER_RESULTS",
            "coverage": "TRACE_EXPOSURE_COVERAGE", "history_coverage": "TRACE_HISTORY_COVERAGE",
            "route_definitions": "ROUTE_BOOK_V6", "route_coverage": "TRACE_ROUTE_COVERAGE",
            "material_relationships": "LOT_WAFER_LINEAGE",
        }
        for role, source_id in expected_aliases.items():
            mapping = proposal_report["proposal"]["source_role_proposals"][role]
            if mapping["candidate_state"] != "UNIQUE_REVIEW_REQUIRED" or mapping["preferred_candidate_source_id"] != source_id:
                raise AssertionError(f"Unexpected mapping for {role}: {mapping}")

        decisions = {
            "decision": "APPROVE_EXACT_PROPOSAL", "reviewer_id": "synthetic-cli-reviewer",
            "proposal_sha256": proposal_report["proposal_sha256"],
            "descriptor_capture_sha256": proposal_report["descriptor_capture_sha256"],
            "time_window": WINDOW,
            "limits": proposal_report["capture"]["limits"], "permission_scope": "SYNTHETIC_READ",
        }
        decisions_path.write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
        stage_times["explicit_synthetic_review_validation_ms"] = _run_cli(
            env, "onboard-review", "--proposal", str(proposal_path),
            "--decisions", str(decisions_path), "--output", str(config_path),
        )
        approved_config = json.loads(config_path.read_text(encoding="utf-8"))
        if approved_config["server_authorization_established"] is not False:
            raise AssertionError("Local synthetic review cannot establish server or company authority")

        scope = {
            "cohort_wafer_ids": [f"SYN-EW-{index:03d}" for index in range(1, 11)],
            "suspected_exposure": {
                "chamber_id": "SYN-C1", "start": "2026-11-21T01:25:00Z",
                "end": "2026-11-21T01:35:00Z", "condition_type": "MAINTENANCE",
            },
        }
        scope_path.write_text(json.dumps(scope, indent=2) + "\n", encoding="utf-8")
        stage_times["bounded_investigation_ms"] = _run_cli(
            env, "investigate-mcp", "--proposal", str(proposal_path),
            "--approved-config", str(config_path), "--transport", str(transport_path),
            "--scope", str(scope_path), "--output", str(evidence_path),
        )

        evidence_bytes = evidence_path.read_bytes()
        evidence = json.loads(evidence_bytes)
        if evidence.get("status") == "REFUSED":
            raise AssertionError(f"Synthetic authorized workflow refused: {evidence.get('limitations')}")
        mcp_reads = evidence["provenance"]["mcp_integration"]["read_operations"]
        if len(mcp_reads) != 7 or any(read["query_hash"] != read["audit_query_hash"] for read in mcp_reads):
            raise AssertionError("Expected seven bounded reads with correlated audit hashes")
        if evidence["provenance"]["mcp_integration"]["permission_scope_authenticated_for_company_use"]:
            raise AssertionError("Synthetic permission was incorrectly represented as company-authenticated")
        journey = evidence["transformations"][1]
        if len(journey.get("journeys", [])) != 98 or not journey.get("route_variants"):
            raise AssertionError("B01/B03 output did not preserve fixed 100-wafer journey and route results")
        exposure = evidence["transformations"][2].get("exposure")
        if not exposure or exposure.get("condition_context", {}).get("evidence_status") != "CALLER_SUPPLIED_UNVERIFIED":
            raise AssertionError("B02 must retain the maintenance label as unverified context")
        if not evidence.get("counterevidence"):
            raise AssertionError("B05 competing evidence was not present in the end-to-end result")

        compressed = gzip.compress(evidence_bytes, compresslevel=9, mtime=0)
        if gzip.decompress(compressed) != evidence_bytes:
            raise AssertionError("Compressed evidence failed byte-for-byte round-trip verification")
        if gzip.compress(gzip.decompress(compressed), compresslevel=9, mtime=0) != compressed:
            raise AssertionError("gzip output is not deterministic for an identical captured envelope")
        EVIDENCE_GZIP.write_bytes(compressed)
        report = {
            "schema_version": "p2-synthetic-onboarding-cli-e2e/v1",
            "environment": "unseen alternate physical field and source aliases; seven separate roles; official MCP SDK stdio peer",
            "workflow_stages": ["onboard-live", "onboard-review", "investigate-mcp"],
            "stage_elapsed_ms": {key: round(value, 3) for key, value in stage_times.items()},
            "source_role_mappings_fixed_answer_pass": True,
            "mapping_decision": "one explicit digest-bound synthetic reviewer record; no automatic approval",
            "metadata_source_count": proposal_report["capture"]["metadata_source_count"],
            "bounded_read_count": len(mcp_reads),
            "mcp_audit_hashes_match": True,
            "journey_count": len(journey["journeys"]),
            "process_instance_count": sum(len(item.get("steps", [])) for item in journey["journeys"]),
            "route_variant_count": len(journey["route_variants"]),
            "exposure_classification_counts": {
                key: len(exposure.get(key, []))
                for key in ("definitely_exposed", "potentially_exposed", "unknown", "not_observed_exposed")
            },
            "condition_label_status": exposure["condition_context"]["evidence_status"],
            "hypothesis_entries": len(evidence["counterevidence"]),
            "causal_conclusion": evidence["uncertainty"]["causal_identifiability"],
            "evidence_json_sha256": _sha256(evidence_bytes),
            "evidence_json_gzip_path": str(EVIDENCE_GZIP.relative_to(ROOT)),
            "evidence_json_gzip_sha256": _sha256(compressed),
            "artifact_integrity": {
                "gzip_mtime_seconds": 0,
                "decompresses_to_captured_json_byte_for_byte": True,
                "recompression_of_identical_json_is_byte_identical": True,
                "cross_run_json_identity": "NOT_GUARANTEED: MCP operation/audit IDs are generated per run; each captured envelope is individually hash-pinned.",
            },
            "baseline_comparison": {
                "frozen_candidate_sha256": "8cd4d26b58cec464e21bebc3a6c4704ea862ed496de5c729568f297970303f5d",
                "frozen_baseline_live_onboarding_commands": 0,
                "current_commands_to_investigation": 3,
                "configuration_step_reduction_claim": "NOT_MEASURED: frozen baseline has no equivalent executable live onboarding workflow, so manual effort is not reconstructable.",
                "human_engineer_time": "NOT_MEASURED",
            },
            "qualification_boundary": "Synthetic descriptors, reviewer decision, permissions and wafer history only. No company authority, mappings, source completeness, manufacturing validation, transfer rights or ROI is established.",
        }
        OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
