"""Verify the P1 React handoff ZIP and run its mounted panel tests after extraction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "integration" / "artifacts"
ARCHIVE = ARTIFACTS / "P2_REACT_HOST_HANDOFF.zip"
SIDECAR = ARTIFACTS / "P2_REACT_HOST_HANDOFF.sha256"
OUTPUT = ARTIFACTS / "P2_REACT_HOST_HANDOFF_VERIFICATION.json"


def main() -> int:
    expected, filename = SIDECAR.read_text(encoding="utf8").strip().split("  ", 1)
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if filename != ARCHIVE.name or expected != digest:
        raise SystemExit("P1 handoff checksum mismatch.")
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("Handoff verification requires the local npm executable.")
    with tempfile.TemporaryDirectory(prefix="p2-react-handoff-verify-") as temp_name:
        target = Path(temp_name)
        with zipfile.ZipFile(ARCHIVE) as archive:
            names = archive.namelist()
            if not names or any(name.startswith("/") or "\\" in name or ".." in PurePosixPath(name).parts for name in names):
                raise SystemExit("P1 handoff contains an unsafe archive path.")
            archive.extractall(target)
        package = target / "P2_REACT_HOST_HANDOFF" / "ui" / "p2-react"
        evidence = target / "P2_REACT_HOST_HANDOFF" / "qualification" / "evidence" / "mcp-end-to-end-workflow.json"
        envelope = json.loads(evidence.read_text(encoding="utf8"))
        roles = [row["dataset_role"] for row in envelope["provenance"]["mcp_integration"]["read_operations"]]
        exposure = envelope["artifacts"][0]["exposure_analysis"]
        route_summary = envelope["artifacts"][0]["journey"]["route_population_summary"]
        if (envelope.get("status") != "PARTIAL" or envelope.get("mode") != "SYNTHETIC_DEMO"
                or roles != ["events", "outcomes", "coverage", "history_coverage", "route_definitions", "route_coverage"]
                or exposure.get("coverage_evidence_level") != "ASSERTED_UNVERIFIED"
                or exposure.get("verified_unexposed") != []
                or route_summary.get("coverage_evidence_level") != "ASSERTED_UNVERIFIED"):
            raise SystemExit("P1 handoff mock evidence does not contain the qualified six-source workflow.")
        # Run from the package root: npm 11 resolves --prefix package names from
        # the invoking directory and can reject an otherwise synchronized lock.
        subprocess.run([npm, "ci", "--offline", "--ignore-scripts"], cwd=package, check=True)
        result = subprocess.run([npm, "test"], cwd=package, check=False, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit("Extracted React module tests failed:\n" + result.stdout + result.stderr)
    test_count = 0
    for line in result.stdout.splitlines():
        if line.startswith("ℹ tests "):
            test_count = int(line.rsplit(" ", 1)[1])
    if test_count != 7:
        raise SystemExit(f"Expected seven mounted React module tests from the handoff, observed {test_count}.")
    report = {
        "status": "PASS_FRESH_EXTRACTION_OFFLINE_REACT_HOST_TESTS",
        "archive": "integration/artifacts/P2_REACT_HOST_HANDOFF.zip",
        "archive_sha256": digest,
        "member_count": len(names),
        "offline_npm_install": "PASS_USING_HOST_LOCAL_NPM_CACHE",
        "mounted_panel_tests": {"total": test_count, "passed": test_count, "failed": 0, "skipped": 0},
        "mock_evidence": {"status": envelope["status"], "mode": envelope["mode"], "read_roles": roles,
                          "exposure_coverage": exposure["coverage_evidence_level"],
                          "verified_unexposed": exposure["verified_unexposed"],
                          "route_coverage": route_summary["coverage_evidence_level"]},
        "p1_host_integration": "NOT_RUN_P1_HOST_UNAVAILABLE",
        "source_transfer_status": "NOT_GRANTED_OR_INFERRED; local handoff only",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
