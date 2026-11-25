"""Create a local stdlib-only virtual environment; performs no package download."""
import argparse
import os
import platform
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".venv"
MARKER_NAME = ".fabintel-p2-managed"


def mcp_wheelhouse():
    if sys.version_info[:2] != (3, 11) or platform.system() != "Darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
        raise SystemExit("The pinned optional MCP wheelhouse is currently qualified only for macOS arm64 CPython 3.11; core installation remains available on supported Python 3.10+ hosts.")
    return ROOT / "vendor" / "mcp-sdk-2.3.0" / "macos-arm64-cp311"


def main():
    parser = argparse.ArgumentParser(description="Create the P2 local offline environment.")
    parser.add_argument("--with-mcp", action="store_true", help="Install the pinned optional official MCP SDK from the bundled target-specific wheelhouse.")
    parser.add_argument("--target", type=Path, default=ENV, help="Environment directory (defaults to .venv in this bundle).")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required; no installer was run.")
    target = Path(os.path.abspath(args.target.expanduser()))
    if args.with_mcp:
        wheelhouse = mcp_wheelhouse()
        if not (wheelhouse / "requirements.lock").is_file() or not (wheelhouse / "wheelhouse").is_dir():
            raise SystemExit("Pinned MCP lock or wheelhouse is missing; no package download was attempted.")
    if target.is_symlink():
        raise SystemExit("Refusing to use a symlinked .venv path.")
    marker = target / MARKER_NAME
    if target.exists():
        if not marker.is_file():
            raise SystemExit("Refusing to replace an existing unmanaged .venv directory.")
    else:
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=(sys.platform != "win32")).create(target)
        marker.write_text("Managed by this FAB Process Forensics bundle.\n", encoding="utf8")
    python = target / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if args.with_mcp:
        subprocess.run([
            str(python), "-m", "pip", "install", "--no-index",
            "--find-links", str(wheelhouse / "wheelhouse"), "--require-hashes",
            "-r", str(wheelhouse / "requirements.lock"),
        ], cwd=ROOT, check=True)
        subprocess.run([str(python), "-m", "pip", "check"], cwd=ROOT, check=True)
    subprocess.run([str(python), "-m", "fabintel", "doctor"], cwd=ROOT, check=True)
    if args.with_mcp:
        print("Offline environment ready with the optional pinned MCP SDK and its hash-checked dependency closure.")
    else:
        print("Offline core environment ready. Runtime core dependencies: Python standard library only.")


if __name__ == "__main__":
    main()
