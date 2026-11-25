"""Regenerate source-integrity hashes; generated self-referential artifacts are excluded."""
import hashlib
from pathlib import Path

if __package__:
    from .build_bundle import files_to_package
else:
    from build_bundle import files_to_package

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "release" / "BOOTSTRAP_MANIFEST.sha256"
EXCLUDED_PACKAGE_PATHS = {
    "release/BOOTSTRAP_MANIFEST.sha256",
    "release/SBOM.spdx.json",
    "qualification/evidence/bundle-verification.log",
    "qualification/no_external_network.sb",
}


def source_manifest_entries():
    entries = []
    for relative, content in files_to_package():
        if relative in EXCLUDED_PACKAGE_PATHS:
            continue
        entries.append((hashlib.sha256(content).hexdigest(), relative))
    return entries


def main():
    rows = [f"{digest}  {relative}" for digest, relative in source_manifest_entries()]
    MANIFEST.write_text("\n".join(rows) + "\n", encoding="utf8")
    digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    print(f"Updated {MANIFEST.relative_to(ROOT)}: {len(rows)} files; manifest sha256 {digest}.")


if __name__ == "__main__":
    main()
