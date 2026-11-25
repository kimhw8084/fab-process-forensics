"""Build a stable source ZIP and SHA-256 sidecar using local files only."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
BUNDLE = RELEASE / "FAB_PROCESS_FORENSICS_P2_CANDIDATE.zip"
CHECKSUMS = RELEASE / "BUNDLE_SHA256SUMS.txt"
PREFIX = "FAB_PROCESS_FORENSICS_P2/"
EXCLUDED_NAMES = {
    BUNDLE.name, CHECKSUMS.name, "RELEASE_RECEIPT.json", "__pycache__", ".venv",
    "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    ".coverage", "coverage.xml",
}


def files_to_package():
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative.parts[:2] == ("release", "archive"):
            continue
        if any(part in EXCLUDED_NAMES or part.endswith(".pyc") for part in relative.parts):
            continue
        if relative.as_posix() == "qualification/evidence/bundle-verification.log":
            continue
        if relative.as_posix() == "qualification/no_external_network.sb":
            continue
        if ".DS_Store" in relative.parts:
            continue
        result.append((relative.as_posix(), path.read_bytes()))
    return sorted(result)


def main():
    files = files_to_package()
    with zipfile.ZipFile(BUNDLE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, content in files:
            info = zipfile.ZipInfo(PREFIX + relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
    CHECKSUMS.write_text(f"{digest}  {BUNDLE.name}\n", encoding="utf8")
    print(json.dumps({"bundle": BUNDLE.name, "sha256": digest, "files": len(files), "bytes": BUNDLE.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
