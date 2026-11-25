"""Inventory local scanners and Python runtime imports without network access."""
import ast
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "qualification" / "evidence" / "security-tool-availability.json"
SCANNERS = ("syft", "grype", "pip-audit", "osv-scanner")
MANIFEST_PATTERNS = (
    "requirements*.txt", "pyproject.toml", "poetry.lock", "Pipfile*",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
)


def runtime_imports():
    imported = set()
    roots = (ROOT / "fabintel", ROOT / "products")
    for source_root in roots:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    imported.add(node.module.split(".", 1)[0])
    local = {"fabintel", "products"}
    return sorted(name for name in imported if name not in sys.stdlib_module_names and name not in local)


def main():
    scanners = {name: shutil.which(name) for name in SCANNERS}
    manifests = sorted({str(path.relative_to(ROOT)) for pattern in MANIFEST_PATTERNS for path in ROOT.rglob(pattern)
                        if ".venv" not in path.parts and "__pycache__" not in path.parts})
    third_party = runtime_imports()
    report = {
        "status": "PARTIAL",
        "network_used": False,
        "scanner_binaries_in_path": scanners,
        "python_runtime_imports_outside_stdlib_and_local_packages": third_party,
        "dependency_manifests_in_launchkit": manifests,
        "vulnerability_database": "NOT_AVAILABLE_OR_NOT_VERIFIED_FROM_LAUNCHKIT",
        "license_ownership": "NOASSERTION",
        "interpretation": "No transitive dependency or license approval is inferred. A current authorized vulnerability database and owner/transfer decision are still required for E09 PASS.",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
