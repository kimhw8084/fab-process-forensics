import unittest

from release.verify_bundle import _require_sdk_suite_success


class SDKReleaseGateTests(unittest.TestCase):
    def test_accepts_completed_sdk_suite_with_zero_skips(self):
        output = "Ran 199 tests in 45.568s\n\nOK\n"
        self.assertEqual(_require_sdk_suite_success(0, output), 199)

    def test_rejects_sdk_suite_that_skips_cases(self):
        output = "Ran 199 tests in 5.642s\n\nOK (skipped=36)\n"
        with self.assertRaises(SystemExit):
            _require_sdk_suite_success(0, output)

    def test_rejects_missing_or_failed_summary(self):
        with self.assertRaises(SystemExit):
            _require_sdk_suite_success(0, "tests exited without a unittest summary")
        with self.assertRaises(SystemExit):
            _require_sdk_suite_success(1, "Ran 199 tests in 45s\n\nOK\n")


if __name__ == "__main__":
    unittest.main()
