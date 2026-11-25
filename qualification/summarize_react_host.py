"""Aggregate synthetic React host runtime and declaration compatibility runs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "qualification" / "evidence"
REACT19 = ROOT / "ui" / "p2-react"
REACT18 = Path("/tmp/p2-react18-host")


def version(package_root: Path, package: str) -> str:
    return json.loads((package_root / "node_modules" / package / "package.json").read_text(encoding="utf8"))["version"]


def test_result(log_path: Path) -> dict:
    log = log_path.read_text(encoding="utf8")
    values = {}
    for key in ("tests", "pass", "fail", "cancelled", "skipped"):
        found = re.search(rf"ℹ {key} (\d+)", log)
        if not found:
            raise ValueError(f"Missing Node test summary field {key!r} in {log_path}")
        values[key] = int(found.group(1))
    values["status"] = "PASS" if values["tests"] == values["pass"] and not any(
        values[field] for field in ("fail", "cancelled", "skipped")
    ) else "FAIL"
    values["log"] = log_path.relative_to(ROOT).as_posix() if log_path.is_relative_to(ROOT) else str(log_path)
    values["log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
    return values


def main() -> int:
    manifest = json.loads((REACT19 / "package.json").read_text(encoding="utf8"))
    peer = manifest["peerDependencies"]["react"]
    react19 = {
        "react": version(REACT19, "react"),
        "react_dom": version(REACT19, "react-dom"),
        "typescript": version(REACT19, "typescript"),
        "runtime_tests": test_result(EVIDENCE / "react-host-react19.log"),
    }
    react18 = {
        "react": version(REACT18, "react"),
        "react_dom": version(REACT18, "react-dom"),
        "typescript": version(REACT18, "typescript"),
        "react_types": version(REACT18, "@types/react"),
        "runtime_tests": test_result(EVIDENCE / "react-host-react18.log"),
        "declaration_typecheck": {
            "command": "rtk proxy /tmp/p2-react18-host/node_modules/.bin/tsc -p /tmp/p2-react18-host/tsconfig.json",
            "status": "PASS" if (EVIDENCE / "react-host-react18-typecheck.log").read_text(encoding="utf8").startswith("PASS") else "FAIL",
            "evidence": "qualification/evidence/react-host-react18-typecheck.log",
        },
    }
    passed = (
        peer == ">=18.2.0 <20"
        and react18["react"] == "18.3.1" and react18["react_dom"] == "18.3.1"
        and react19["react"] == "19.3.1" and react19["react_dom"] == "19.3.1"
        and react18["runtime_tests"]["status"] == react19["runtime_tests"]["status"] == "PASS"
        and react18["declaration_typecheck"]["status"] == "PASS"
    )
    report = {
        "status": "PASS_SYNTHETIC_REACT_HOST_COMPATIBILITY" if passed else "FAIL",
        "module": manifest["name"],
        "module_version": manifest["version"],
        "declared_react_peer_range": peer,
        "react_18_host": react18,
        "react_19_host": react19,
        "p1_host_integration": "NOT_RUN_P1_SOURCE_TREE_AND_COMPONENT_API_UNAVAILABLE",
        "interpretation": "Compatibility is demonstrated against the named synthetic React hosts and adapters. It does not establish compatibility with the unavailable P1 shell or its exact React/component versions.",
    }
    output = EVIDENCE / "react-host-compatibility.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({"status": report["status"], "react_18": react18["runtime_tests"],
                      "react_18_typecheck": react18["declaration_typecheck"]["status"],
                      "react_19": react19["runtime_tests"]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
