"""Safely unpack and exercise the local transfer candidate."""
import hashlib
import os
from pathlib import PurePosixPath
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "release" / "FAB_PROCESS_FORENSICS_P2_CANDIDATE.zip"
CHECKSUMS = ROOT / "release" / "BUNDLE_SHA256SUMS.txt"


def _require_sdk_suite_success(returncode: int, output: str) -> int:
    if returncode:
        raise SystemExit(returncode)
    summary = re.search(r"Ran\s+(\d+)\s+tests?\s+in\s+[^\r\n]+", output)
    summary_tail = output[summary.end():].strip().splitlines() if summary else []
    if not summary or not summary_tail or summary_tail[0].strip() != "OK":
        raise SystemExit("SDK-enabled fresh-extraction regression must report a parsed test total, zero skips, and an OK result.")
    return int(summary.group(1))


def main():
    expected, name = CHECKSUMS.read_text(encoding="utf8").strip().split("  ", 1)
    if name != BUNDLE.name or hashlib.sha256(BUNDLE.read_bytes()).hexdigest() != expected:
        raise SystemExit("Bundle sidecar checksum mismatch.")
    with tempfile.TemporaryDirectory(prefix="fabintel-verify-", dir=ROOT / "release") as temp_name:
        destination = Path(temp_name)
        with zipfile.ZipFile(BUNDLE) as archive:
            names = archive.namelist()
            if not names or any(name.startswith("/") or "\\" in name or ".." in PurePosixPath(name).parts for name in names):
                raise SystemExit("Unsafe or empty bundle path list.")
            archive.extractall(destination)
        package = destination / "FAB_PROCESS_FORENSICS_P2"
        subprocess.run([sys.executable, "bootstrap_check.py"], cwd=package, check=True)
        subprocess.run([sys.executable, "release/install_offline.py", "--with-mcp"], cwd=package, check=True)
        python = package / ".venv" / "bin" / "python"
        if sys.platform == "win32":
            python = package / ".venv" / "Scripts" / "python.exe"
        suite_env = os.environ.copy()
        suite_env["P2_TEST_SDK_PATH"] = subprocess.check_output(
            [str(python), "-c", "import site; print(site.getsitepackages()[0])"],
            cwd=package, text=True,
        ).strip()
        suite = subprocess.run(
            [str(python), "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=package, env=suite_env, text=True, capture_output=True,
        )
        sys.stdout.write(suite.stdout)
        sys.stderr.write(suite.stderr)
        suite_output = suite.stdout + "\n" + suite.stderr
        if suite.returncode:
            raise SystemExit(suite.returncode)
        test_count = _require_sdk_suite_success(suite.returncode, suite_output)
        print(f"SDK-enabled regression PASS: {test_count} tests, zero skipped.")
        subprocess.run([str(python), "qualification/run_mock_mcp_workflow.py"], cwd=package, check=True)
        npm = shutil.which("npm")
        if npm is None:
            raise SystemExit("Fresh-extraction React panel qualification requires the local npm executable.")
        react_package = package / "ui" / "p2-react"
        subprocess.run([npm, "ci", "--offline", "--ignore-scripts"], cwd=react_package, check=True)
        subprocess.run([npm, "test"], cwd=react_package, check=True)
        subprocess.run([npm, "run", "host:typecheck"], cwd=react_package, check=True)
        subprocess.run([npm, "run", "host:build"], cwd=react_package, check=True)
        reference_host = package / "ui" / "reference-host"
        page = (reference_host / "dist" / "index.html").read_text(encoding="utf8")
        if "/assets/" not in page or "/src/main.tsx" in page or not list((reference_host / "dist" / "assets").glob("*.js")):
            raise SystemExit("Fresh extraction did not produce a self-contained reference-host asset set.")
        subprocess.run([str(python), "-m", "fabintel", "demo"], cwd=package, check=True)
        subprocess.run([sys.executable, "release/uninstall_offline.py"], cwd=package, check=True)
        if (package / ".venv").exists():
            raise SystemExit("Rollback left a bundle-managed virtual environment behind.")
    print("PASS: checksum, safe extraction, source integrity, hash-checked offline MCP installation, full SDK suite, six-source MCP-to-evidence workflow, offline npm install, React panel tests/typecheck, self-contained reference-host build, demo, and rollback.")


if __name__ == "__main__":
    main()
