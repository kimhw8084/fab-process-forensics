"""Record the pinned P2 React test/tool dependency license and npm audit evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ui" / "p2-react"
OUTPUT = ROOT / "qualification" / "evidence" / "p2-react-dependency-audit.json"
NPM_AUDIT = ROOT / "qualification" / "evidence" / "p2-react-npm-audit.json"
BUNDLED_RUNTIME = {"react", "react-dom", "scheduler"}


def _license(value):
    if isinstance(value, dict):
        return value.get("type") or value.get("url")
    return value if isinstance(value, str) else None


def main() -> int:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf8"))
    lock_path = PACKAGE / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf8"))
    audit = json.loads(NPM_AUDIT.read_text(encoding="utf8"))
    packages = []
    missing = []
    for package_path, record in sorted(lock.get("packages", {}).items()):
        if not package_path.startswith("node_modules/"):
            continue
        installed_manifest = PACKAGE / package_path / "package.json"
        if not installed_manifest.is_file():
            if record.get("optional"):
                continue
            missing.append(package_path)
            continue
        installed = json.loads(installed_manifest.read_text(encoding="utf8"))
        license_id = _license(installed.get("license"))
        if not license_id:
            missing.append(package_path)
        packages.append({
            "name": installed.get("name"),
            "version": installed.get("version"),
            "license": license_id,
            "development_only": installed.get("name") not in BUNDLED_RUNTIME,
            "bundled_reference_host_runtime": installed.get("name") in BUNDLED_RUNTIME,
        })

    vulnerabilities = audit.get("metadata", {}).get("vulnerabilities", {})
    total_vulnerabilities = vulnerabilities.get("total")
    direct_licenses = {}
    for name, version in manifest.get("devDependencies", {}).items():
        installed_manifest = PACKAGE / "node_modules" / name / "package.json"
        if not installed_manifest.is_file():
            missing.append(f"direct:{name}")
            continue
        installed = json.loads(installed_manifest.read_text(encoding="utf8"))
        direct_licenses[name] = {
            "pinned_version": version,
            "installed_version": installed.get("version"),
            "license": _license(installed.get("license")),
        }

    report = {
        "status": "PASS_LOCAL_NPM_AND_LICENSE_AUDIT" if not missing and total_vulnerabilities == 0 else "FAIL",
        "module": manifest["name"],
        "module_version": manifest["version"],
        "module_source_license": manifest.get("license"),
        "source_redistribution_status": "NOT_GRANTED_OR_INFERRED_BY_THIS_AUDIT",
        "lockfile_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "runtime_dependencies": manifest.get("dependencies", {}),
        "runtime_peer_dependencies": manifest.get("peerDependencies", {}),
        "bundled_reference_host_runtime": [
            {key: item[key] for key in ("name", "version", "license")}
            for item in packages if item["bundled_reference_host_runtime"]
        ],
        "direct_development_dependencies": direct_licenses,
        "installed_locked_package_count": len(packages),
        "optional_locked_package_count": sum(bool(item.get("optional")) for item in lock.get("packages", {}).values()),
        "license_ids_observed": sorted({item["license"] for item in packages if item["license"]}),
        "packages": packages,
        "missing_license_or_install_records": sorted(set(missing)),
        "npm_audit": {
            "audit_report_version": audit.get("auditReportVersion"),
            "vulnerabilities": vulnerabilities,
            "dependency_counts": audit.get("metadata", {}).get("dependencies", {}),
        },
        "limitations": [
            "npm audit covers the locked npm test/tool dependency graph at capture time; it is not a full source-code security review.",
            "Test/build tools remain development-only; the React, React DOM, and Scheduler packages named in bundled_reference_host_runtime are embedded in the local reference-host assets.",
            "This report records upstream license identifiers and does not grant redistribution rights or company approval.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({key: report[key] for key in ("status", "installed_locked_package_count", "license_ids_observed", "missing_license_or_install_records", "npm_audit")}, indent=2))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
