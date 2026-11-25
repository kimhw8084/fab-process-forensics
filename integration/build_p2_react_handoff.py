"""Build a deterministic, review-only P1 handoff for the headless P2 React module."""
from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "integration" / "artifacts" / "P2_REACT_HOST_HANDOFF.zip"
SUM = ROOT / "integration" / "artifacts" / "P2_REACT_HOST_HANDOFF.sha256"
PREFIX = "P2_REACT_HOST_HANDOFF/"
FILES = (
    "integration/P2_REACT_HOST_HANDOFF.md",
    "ui/P1_HOST_INTEGRATION_PROPOSAL.md",
    "ui/contribution.manifest.json",
    "ui/p2-react/package.json",
    "ui/p2-react/package-lock.json",
    "ui/p2-react/tsconfig.json",
    "ui/p2-react/README.md",
    "ui/p2-react/src/types.ts",
    "ui/p2-react/src/model.ts",
    "ui/p2-react/src/index.tsx",
    "ui/p2-react/test/p2-host.integration.test.mjs",
    "ui/p2-react/dist/index.js",
    "ui/p2-react/dist/index.d.ts",
    "ui/p2-react/dist/model.js",
    "ui/p2-react/dist/model.d.ts",
    "ui/p2-react/dist/types.js",
    "ui/p2-react/dist/types.d.ts",
    "contracts/evidence.v1.schema.json",
    "contracts/product-manifest.v1.schema.json",
    "product.json",
    "qualification/evidence/mcp-end-to-end-workflow.json",
    "qualification/evidence/react-host-compatibility.json",
    "qualification/evidence/react-host-react18.log",
    "qualification/evidence/react-host-react19.log",
    "qualification/evidence/react-host-react18-typecheck.log",
)


def main() -> int:
    missing = [relative for relative in FILES if not (ROOT / relative).is_file()]
    if missing:
        raise SystemExit("Handoff input is missing: " + ", ".join(missing))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(FILES):
            path = ROOT / relative
            info = zipfile.ZipInfo(PREFIX + relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    SUM.write_text(f"{digest}  {OUT.name}\n", encoding="utf8")
    print(f"PASS: {OUT.relative_to(ROOT)} ({len(FILES)} files, sha256 {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
