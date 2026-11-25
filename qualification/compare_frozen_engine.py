#!/usr/bin/env python3
"""Compare frozen and working P2 engines on one identical synthetic task."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FROZEN_ARCHIVE_SHA256 = "8cd4d26b58cec464e21bebc3a6c4704ea862ed496de5c729568f297970303f5d"
FROZEN_SOURCE_MANIFEST_SHA256 = "dbfe462fa80ae9117a8541d9b6c75b7747c42d4683aee538d925babe8ccfcf88"
DEFAULT_ARCHIVE = Path("/Users/haewonkim/home/work/product 2/FAB_INTELLIGENCE_P2_CODEX_LAUNCHKIT_2026-11-22/release/FAB_PROCESS_FORENSICS_P2_CANDIDATE.zip")
DEFAULT_FIXTURE = ROOT / "qualification/fixtures/complex_engineer_investigation_v1.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_frozen(archive: Path, destination: Path) -> Path:
    if sha256(archive.read_bytes()) != FROZEN_ARCHIVE_SHA256:
        raise SystemExit("Frozen candidate archive checksum does not match the pinned baseline.")
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode):
                raise SystemExit(f"Frozen archive contains an unsafe member path: {member.filename}")
        bundle.extractall(destination)
    package = destination / "FAB_PROCESS_FORENSICS_P2"
    manifest = package / "release/BOOTSTRAP_MANIFEST.sha256"
    if not package.is_dir() or sha256(manifest.read_bytes()) != FROZEN_SOURCE_MANIFEST_SHA256:
        raise SystemExit("Frozen extracted source manifest does not match the pinned snapshot.")
    return package


def run_analysis(product_root: Path, fixture: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "fabintel", "analyze", str(fixture)],
        cwd=product_root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ""},
    )
    return json.loads(completed.stdout)


def summary(envelope: dict) -> dict:
    journey = next(item for item in envelope["transformations"] if item.get("id") == "p2-journey-and-route-variants-v1")
    exposure = envelope["artifacts"][0]["exposure_analysis"]
    hypothesis = envelope["counterevidence"][0]
    verification = hypothesis.get("next_authorized_verification", {})
    candidates = verification.get("candidates", [])
    return {
        "status": envelope["status"],
        "journeys": len(journey["journeys"]),
        "retained_step_instances": sum(len(item["steps"]) for item in journey["journeys"]),
        "exposure": {
            "exact": len(exposure["definitely_exposed"]),
            "potential": len(exposure["potentially_exposed"]),
            "unknown": len(exposure["unknown"]),
            "verified_unexposed": len(exposure["verified_unexposed"]),
            "coverage_evidence_level": exposure["coverage_evidence_level"],
        },
        "causal_conclusion": hypothesis["causal_conclusion"]["status"],
        "generic_next_check_present": bool(verification.get("purpose")),
        "bounded_check_candidate_count": len(candidates),
        "bounded_check_categories": [item["category"] for item in candidates],
        "membership_conflict_target_and_records": [
            {
                "target_wafer_ids": item.get("target_wafer_ids", []),
                "step_instance_refs": item.get("step_instance_refs", []),
                "material_relationship_refs": item.get("material_relationship_refs", []),
                "relationship_scoped_keys": [
                    {
                        "source_id": ref.get("source_id"),
                        "relationship_id": ref.get("relationship_id"),
                        "keys": ref.get("requested_declared_keys", []),
                    }
                    for ref in item.get("source_relationships", [])
                ],
                "proposed_not_executed": item.get("proposed_not_executed"),
                "authorization_status": item.get("authorization_status"),
            }
            for item in candidates if item.get("category") == "LOT_MEMBERSHIP_CONFLICT"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=ROOT / "qualification/evidence/frozen-baseline-matched-investigation.json")
    args = parser.parse_args()
    fixture = args.fixture.resolve()
    fixture_hash = sha256(fixture.read_bytes())

    with tempfile.TemporaryDirectory(prefix="p2-frozen-baseline-") as temporary:
        frozen_root = extract_frozen(args.archive.resolve(), Path(temporary))
        frozen = run_analysis(frozen_root, fixture)
    current = run_analysis(ROOT, fixture)
    frozen_summary = summary(frozen)
    current_summary = summary(current)

    invariant_keys = ("status", "journeys", "retained_step_instances", "exposure", "causal_conclusion")
    safety_parity = all(frozen_summary[key] == current_summary[key] for key in invariant_keys)
    if not safety_parity:
        raise SystemExit("The matched baseline challenge found a change in the protected scientific result envelope.")
    membership = current_summary["membership_conflict_target_and_records"]
    if len(membership) != 1:
        raise SystemExit("The working revision must expose exactly one deduplicated membership-conflict check for this fixture.")
    proposal = membership[0]
    if proposal["target_wafer_ids"] != ["SYN-EW-010"]:
        raise SystemExit("The bounded membership check did not retain the fixed expected wafer.")
    if {ref["step_instance_id"] for ref in proposal["step_instance_refs"]} != {"SYN-EW-010-S02", "SYN-EW-010-S03"}:
        raise SystemExit("The bounded membership check did not retain the exact expected process steps.")
    if {ref["record_id"] for ref in proposal["material_relationship_refs"]} != {"SYN-MEM-010-B"}:
        raise SystemExit("The bounded membership check did not retain the exact expected material record.")
    relation_keys = {ref["relationship_id"]: set(ref["keys"]) for ref in proposal["relationship_scoped_keys"]}
    if "from_entity_id" in relation_keys["SYN_REL_EW_PROCESS"] or "step_instance_id" in relation_keys["SYN_REL_EW_LOT_MEMBERSHIP"]:
        raise SystemExit("Relationship-specific key scopes were combined in the membership check.")
    if proposal["proposed_not_executed"] is not True or proposal["authorization_status"] != "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER":
        raise SystemExit("The membership check is not safely gated by explicit server authorization.")

    report = {
        "status": "PASS_MATCHED_FROZEN_BASELINE_ENGINE_TASK",
        "fixture": fixture.relative_to(ROOT).as_posix() if fixture.is_relative_to(ROOT) else str(fixture),
        "fixture_sha256": fixture_hash,
        "frozen_candidate_sha256": FROZEN_ARCHIVE_SHA256,
        "frozen_source_snapshot_manifest_sha256": FROZEN_SOURCE_MANIFEST_SHA256,
        "execution": "The frozen candidate archive was safely extracted to a temporary directory; both engines analyzed the same snapshot using the same Python executable.",
        "protected_scientific_result_parity": safety_parity,
        "frozen_baseline": frozen_summary,
        "working_revision": current_summary,
        "measured_increment": {
            "new_bounded_check_candidates": current_summary["bounded_check_candidate_count"] - frozen_summary["bounded_check_candidate_count"],
            "specific_membership_conflict_check_added": bool(membership),
            "causal_or_exposure_result_changed": False,
        },
        "limitations": [
            "This is a matched synthetic engine-output task, not a blinded engineer study or company ROI estimate.",
            "The direct browser interaction replay is recorded separately; this comparison does not measure operator completion time.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
