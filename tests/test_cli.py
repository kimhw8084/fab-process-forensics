import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CliTests(unittest.TestCase):
    def test_doctor_separates_engineering_gates_from_transfer_and_internal_approval(self):
        result = subprocess.run(
            [sys.executable, "-m", "fabintel", "doctor"],
            cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        report = json.loads(result.stdout)
        self.assertFalse(report["external_transfer_ready"])
        readiness = report["readiness"]
        self.assertEqual(readiness["external_engineering"]["status"], "PARTIAL")
        self.assertIn("E02", readiness["external_engineering"]["open_gate_ids"])
        self.assertIn("E09", readiness["external_engineering"]["open_gate_ids"])
        self.assertEqual(readiness["formal_transfer_and_target_security"]["status"], "NOT_QUALIFIED")
        self.assertEqual(readiness["internal_qualification"]["status"], "PENDING_INTERNAL")
        self.assertEqual(readiness["canonical_requirements"]["status"], "NOT_VERIFIED")

    def test_analyze_writes_reproducible_evidence_envelope(self):
        evidence_dir = ROOT / "qualification" / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="fabintel-cli-", dir=evidence_dir) as temp_name:
            output = Path(temp_name) / "result.json"
            subprocess.run([
                sys.executable, "-m", "fabintel", "analyze",
                str(ROOT / "fixtures" / "case_positive.json"), "--output", str(output),
            ], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = json.loads(output.read_text(encoding="utf8"))
            self.assertEqual(result["schema_version"], "1.0.0")
            self.assertEqual(result["product_id"], "p2")
            self.assertEqual(result["provenance"]["engine_version"], "0.3.0")
            self.assertEqual(result["provenance"]["input_sha256"], result["artifacts"][0]["content_sha256"])


if __name__ == "__main__":
    unittest.main()
