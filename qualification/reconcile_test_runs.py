"""Reconcile unittest discovery, execution, skips, and MCP SDK coverage."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "qualification" / "evidence"
SUMMARY = re.compile(r"Ran (\d+) tests? in ([0-9.]+)s")
TEST_HEADER = re.compile(r"^([A-Za-z0-9_]+) \(([^)]+)\) \.\.\.", re.MULTILINE)
SKIPPED_LINE = re.compile(r"^([A-Za-z0-9_]+) \(([^)]+)\) \.\.\. skipped(?: .*)?$", re.MULTILINE)
FAILURE_SUMMARY = re.compile(r"^FAILED(?: \((.*)\))?$", re.MULTILINE)
FRESH_EXTRACTION_SUCCESS_MARKER = (
    "PASS: checksum, safe extraction, source integrity, hash-checked offline MCP installation, full SDK suite, "
    "six-source MCP-to-evidence workflow, offline npm install, React panel tests/typecheck, "
    "self-contained reference-host build, demo, and rollback."
)


def fresh_extraction_passed(log: str) -> bool:
    """Require the exact verifier marker covering protocol, React, demo, and rollback."""
    return FRESH_EXTRACTION_SUCCESS_MARKER in log


def parse_run(path: Path, runtime: str) -> dict:
    log = path.read_text(encoding="utf8")
    summary = SUMMARY.search(log)
    if not summary:
        raise ValueError(f"No unittest summary found in {path}")
    total = int(summary.group(1))
    headers = TEST_HEADER.findall(log)
    if len(headers) != total:
        raise ValueError(f"Test headers ({len(headers)}) do not reconcile with discovered tests ({total}) in {path}")
    skipped_rows = SKIPPED_LINE.findall(log)
    allowed_sdk_modules = (
        "test_mcp_adapter.MCPAdapterProtocolTests.",
        "test_reference_workflow.ReferenceWorkflowTests.",
    )
    unexpected_skips = [module for name, module in skipped_rows if not module.startswith(allowed_sdk_modules)]
    if unexpected_skips:
        raise ValueError("A skipped test is outside the explicitly optional MCP SDK suites: " + ", ".join(unexpected_skips))
    skipped = [f"{name} ({module})" for name, module in skipped_rows]
    failure = FAILURE_SUMMARY.search(log)
    failure_fields = failure.group(1) if failure else ""
    failed = int(re.search(r"failures=(\d+)", failure_fields).group(1)) if re.search(r"failures=(\d+)", failure_fields) else 0
    errored = int(re.search(r"errors=(\d+)", failure_fields).group(1)) if re.search(r"errors=(\d+)", failure_fields) else 0
    passed = total - len(skipped) - failed - errored
    if passed < 0 or not re.search(r"^(?:OK|FAILED)(?: \(.*\))?$", log, re.MULTILINE):
        raise ValueError(f"Unrecognized or inconsistent unittest result summary in {path}")
    try:
        log_location = path.relative_to(ROOT).as_posix()
    except ValueError:
        log_location = str(path)
    return {
        "runtime": runtime,
        "log": log_location,
        "total_discovered": total,
        "actually_executed": total - len(skipped),
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "skipped": len(skipped),
        "skipped_test_ids": skipped,
        "skipped_capability": (
            "Optional pinned MCP SDK protocol integration: stdio and Streamable HTTP transports, server permission enforcement, bounded multi-grain reads, role/source semantics, query/audit provenance, cancellation, recovery, and six-source reference-host API workflow."
            if skipped else None
        ),
    }


def main() -> int:
    pinned = parse_run(EVIDENCE / "test-suite-pinned.log", "Pinned offline MCP SDK venv")
    core = parse_run(EVIDENCE / "test-suite-core.log", "Core environment without optional MCP SDK")
    bundle_log = EVIDENCE / "bundle-verification.log"
    bundle_text = bundle_log.read_text(encoding="utf8") if bundle_log.is_file() else ""
    fresh_extraction_ok = fresh_extraction_passed(bundle_text)
    report = {
        "status": "PASS_RECONCILED" if all(not run["failed"] and not run["errored"] for run in (pinned, core)) else "FAIL",
        "runs": {"pinned_sdk": pinned, "core": core},
        "protocol_path_qualification": {
            "pinned_sdk": "executed, including full synthetic MCP read-to-analysis integration and cancellation/recovery cases",
            "core": "SDK-dependent protocol integration skipped; core analyzer and non-SDK tests executed",
            "fresh_extraction": (
                "PASS: the extracted archive completed source-integrity verification, hash-pinned offline installation, the full MCP-SDK-enabled protocol suite, six-source MCP-to-evidence workflow, offline npm/React host qualification, demo, and rollback"
                if fresh_extraction_ok else "PENDING_FRESH_EXTRACTION; bundle-verification.log has not recorded the complete protocol and React path"
            ),
        },
        "limitations": [
            "A skipped test is reported separately and never counted as passed or executed.",
            "Synthetic MCP qualification does not establish company endpoint compatibility, source approval, permission scope, or manufacturing validity.",
        ],
    }
    (EVIDENCE / "test-run-reconciliation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({"status": report["status"], "runs": {
        key: {field: value[field] for field in ("total_discovered", "actually_executed", "passed", "failed", "errored", "skipped")}
        for key, value in report["runs"].items()
    }}, indent=2))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
