import hashlib
import json
from pathlib import Path
import unittest
import zipfile

from release.build_bundle import files_to_package
from release.update_source_manifest import EXCLUDED_PACKAGE_PATHS, source_manifest_entries


class ReleasePackagingTests(unittest.TestCase):
    def test_source_archive_omits_generated_caches_and_local_environments(self):
        excluded = {
            "__pycache__", ".venv", "node_modules", ".pytest_cache",
            ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".coverage", "coverage.xml",
        }
        packaged = [path for path, _ in files_to_package()]
        self.assertTrue(packaged)
        self.assertFalse(
            [path for path in packaged if excluded.intersection(path.split("/"))],
        )
        expected_manifest_paths = [path for path in packaged if path not in EXCLUDED_PACKAGE_PATHS]
        self.assertEqual([path for _, path in source_manifest_entries()], expected_manifest_paths)
        sbom = json.loads((Path(__file__).resolve().parent.parent / "release" / "SBOM.spdx.json").read_text())
        expected_sbom_paths = {"./" + path for path in packaged if path != "release/SBOM.spdx.json"}
        self.assertEqual({item["fileName"] for item in sbom["files"]}, expected_sbom_paths)

    def test_bundled_python_dependency_licenses_are_hashed_and_declared_in_spdx(self):
        root = Path(__file__).resolve().parent.parent
        vendor = root / "vendor" / "mcp-sdk-2.3.0" / "macos-arm64-cp311"
        inventory = json.loads((vendor / "license-inventory.json").read_text())
        sbom = json.loads((root / "release" / "SBOM.spdx.json").read_text())
        packages = {item["name"]: item for item in sbom["packages"]}
        self.assertEqual(len(inventory["packages"]), 28)
        for item in inventory["packages"]:
            self.assertTrue(item["license_expression"], item["name"])
            wheel = vendor / "wheelhouse" / item["wheel"]
            self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), item["wheel_sha256"])
            with zipfile.ZipFile(wheel) as archive:
                self.assertTrue(item["bundled_license_files"], item["name"])
                for license_file in item["bundled_license_files"]:
                    contents = archive.read(license_file["path"])
                    self.assertEqual(hashlib.sha256(contents).hexdigest(), license_file["sha256"])
            self.assertEqual(packages[item["name"]]["licenseDeclared"], item["license_expression"])


if __name__ == "__main__":
    unittest.main()
