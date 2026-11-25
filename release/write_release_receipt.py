"""Record exact local qualification evidence and archive checksums."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
OUT = RELEASE / "RELEASE_RECEIPT.json"


def digest(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit(f"Required release evidence is missing: {relative}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    git_result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    commit = git_result.stdout.strip() if git_result.returncode == 0 else None
    receipt = {
        "receipt_version": "1.0.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_state": "CANDIDATE",
        "evaluated_commit": commit,
        "commit_note": None if commit else "No Git repository is present in the supplied launchkit folder.",
        "host": {
            "os": platform.system(), "release": platform.release(),
            "architecture": platform.machine(), "python": sys.version,
        },
        "artifacts": {
            "bundle": "release/FAB_PROCESS_FORENSICS_P2_CANDIDATE.zip",
            "bundle_sha256": digest("release/FAB_PROCESS_FORENSICS_P2_CANDIDATE.zip"),
            "bundle_checksum_sidecar_sha256": digest("release/BUNDLE_SHA256SUMS.txt"),
            "source_manifest": "release/BOOTSTRAP_MANIFEST.sha256",
            "source_manifest_sha256": digest("release/BOOTSTRAP_MANIFEST.sha256"),
            "sbom": "release/SBOM.spdx.json",
            "sbom_sha256": digest("release/SBOM.spdx.json"),
            "gate_report_sha256": digest("release/GATE_REPORT.json"),
            "test_log_sha256": digest("qualification/evidence/test-suite.log"),
            "science_oracle_summary_sha256": digest("qualification/evidence/science-oracle-summary.json"),
            "bundle_verification_log_sha256": digest("qualification/evidence/bundle-verification.log"),
            "browser_smoke_sha256": digest("qualification/evidence/browser-ui-smoke.json"),
            "browser_workflow_sha256": digest("qualification/evidence/browser-workflow-2026-11-22.json"),
            "browser_current_workflow_sha256": digest("qualification/evidence/browser-workflow-current.json"),
            "browser_process_forensics_sha256": digest("qualification/evidence/browser-process-forensics-current.json"),
            "browser_current_export_sha256": digest("qualification/evidence/browser-current-export.json"),
            "browser_accessibility_sha256": digest("qualification/evidence/browser-accessibility-current.json"),
            "browser_accessibility_export_sha256": digest("qualification/evidence/browser-accessibility-export.json"),
            "ui_accessibility_test_source_sha256": digest("tests/test_schema_and_ui.py"),
            "browser_export_sha256": digest("qualification/evidence/browser-keyboard-export.json"),
            "ui_state_smoke_sha256": digest("qualification/evidence/ui-state-smoke.json"),
            "mcp_end_to_end_workflow_sha256": digest("qualification/evidence/mcp-end-to-end-workflow.json"),
            "current_host_qualification_sha256": digest("release/CURRENT_HOST_QUALIFICATION.md"),
            "internal_preflight_template_check_sha256": digest("qualification/evidence/internal-preflight-template-check.json"),
            "server_stop_smoke_sha256": digest("qualification/evidence/server-stop-smoke.json"),
            "graph_benchmark_sha256": digest("qualification/evidence/graph-library-benchmark.json"),
            "mcp_vulnerability_scan_sha256": digest("qualification/evidence/mcp-dependency-vulnerability-scan.json"),
            "external_gap_ledger_sha256": digest("requirements/EXTERNAL_GAP_LEDGER.md"),
            "heldout_test_module_sha256": digest("tests/test_heldout_adversarial.py"),
            "product_manifest_sha256": digest("product.json"),
        },
        "engineering_reference": {
            "name": "Golden Agentic Engineering",
            "repository": "https://github.com/kimhw8084/golden-agentic-engineering",
            "commit": "dc2ece864b2d744e47dfe8c7d9ad78aadbed369e",
            "status": "STAGED_EXTERNAL_REFERENCE_NOT_COMPANY_QUALIFICATION",
        },
        "commands": [
            "rtk proxy /tmp/p2-offline-mcp-qualified/bin/python -m unittest discover -s tests -v",
            "rtk proxy /tmp/p2-offline-mcp-qualified/bin/python release/verify_bundle.py",
            "rtk python -m fabintel serve --port 8767 (then Ctrl-C; see server-stop-smoke.json)",
            "rtk python -m fabintel demo",
            "rtk sandbox-exec -f qualification/no_external_network.sb node qualification/ui_state_smoke.js",
            "rtk sandbox-exec -f qualification/no_external_network.sb python -m fabintel preflight --capabilities requirements/mcp-discovery.template.json",
        ],
        "qualification": {
            "state": "PARTIAL_CANDIDATE",
            "target_os_qualified": False,
            "company_data_or_mcp_qualified": False,
            "external_transfer_ready": False,
            "internal_qualification": "PENDING_INTERNAL",
            "science_holdout": "INDEPENDENT_FIXED_CASES_NOT_BLINDED",
            "unverified_gates": ["E01", "E02", "E05", "E07", "E08", "E09", "E11", "E12"],
        },
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(f"Wrote {OUT.relative_to(ROOT)}; candidate evidence and checksums recorded.")


if __name__ == "__main__":
    main()
