"""Regression tests for SDK-only test accounting in release evidence."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from qualification.reconcile_test_runs import FRESH_EXTRACTION_SUCCESS_MARKER, fresh_extraction_passed, parse_run


class ReconcileTestRunsTests(unittest.TestCase):
    def test_sdk_and_reference_host_skips_are_counted_by_full_test_id(self):
        log = """test_read (test_mcp_adapter.MCPAdapterProtocolTests.test_read) ... skipped 'SDK required'
test_workflow (test_reference_workflow.ReferenceWorkflowTests.test_workflow) ... skipped 'SDK required'

----------------------------------------------------------------------
Ran 2 tests in 0.001s

OK (skipped=2)
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "core.log"
            path.write_text(log, encoding="utf8")
            result = parse_run(path, "core")

        self.assertEqual(result["total_discovered"], 2)
        self.assertEqual(result["actually_executed"], 0)
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["skipped"], 2)
        self.assertEqual(result["skipped_test_ids"], [
            "test_read (test_mcp_adapter.MCPAdapterProtocolTests.test_read)",
            "test_workflow (test_reference_workflow.ReferenceWorkflowTests.test_workflow)",
        ])

    def test_non_sdk_skip_is_rejected_instead_of_hidden(self):
        log = """test_unexpected (test_engine.EngineCase.test_unexpected) ... skipped 'unexpected'

----------------------------------------------------------------------
Ran 1 test in 0.001s

OK (skipped=1)
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "core.log"
            path.write_text(log, encoding="utf8")
            with self.assertRaisesRegex(ValueError, "outside the explicitly optional MCP SDK suites"):
                parse_run(path, "core")

    def test_fresh_extraction_requires_the_complete_protocol_and_react_marker(self):
        self.assertTrue(fresh_extraction_passed(FRESH_EXTRACTION_SUCCESS_MARKER))
        self.assertFalse(fresh_extraction_passed(FRESH_EXTRACTION_SUCCESS_MARKER.replace(
            "React panel tests/typecheck, self-contained reference-host build", "React panel tests"
        )))
        self.assertFalse(fresh_extraction_passed("PASS: checksum, source integrity, and demo."))


if __name__ == "__main__":
    unittest.main()
