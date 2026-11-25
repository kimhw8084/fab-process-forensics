import unittest

from fabintel.cli import _preflight_report


def complete_capture():
    operations = {name: f"fab-{name}" for name in (
        "discover", "semantics", "relationships", "read_bounded", "cancel", "audit"
    )}
    return {
        "contract_version": "1.0.0",
        "semantic_version": "site-captured-v1",
        "permission_scope": {"read_only": True, "source_scopes": ["approved source set"]},
        "operations": operations,
        "tool_versions": {tool_name: "1.2.3" for tool_name in operations.values()},
        "limits": {"max_rows": 100, "max_bytes": 1000000, "timeout_seconds": 30},
        "auth_scope": "read-only", "audit_supported": True, "cancel_supported": True,
    }


class PreflightTests(unittest.TestCase):
    def test_no_live_adapter_is_always_pending_internal(self):
        report = _preflight_report()
        self.assertEqual(report["status"], "PENDING_INTERNAL_QUALIFICATION")
        self.assertEqual(report["network_requests"], 0)

    def test_complete_capture_is_structural_only_not_company_qualification(self):
        report = _preflight_report(complete_capture())
        self.assertEqual(report["capture_structure"], "PASS")
        self.assertEqual(report["status"], "PENDING_INTERNAL_QUALIFICATION")
        self.assertEqual(report["network_requests"], 0)
        self.assertEqual(report["operation_mappings_checked"], 6)
        self.assertEqual(report["tool_versions_checked"], 6)

    def test_capture_requires_matching_contract_exact_tool_versions_and_source_scopes(self):
        payload = complete_capture()
        payload["contract_version"] = "0.0.0"
        payload["tool_versions"].pop("fab-read_bounded")
        payload["permission_scope"]["source_scopes"] = []
        report = _preflight_report(payload)
        self.assertEqual(report["capture_structure"], "INCOMPLETE")
        self.assertTrue(any("contract version" in item for item in report["missing"]))
        self.assertTrue(any("exact tool version" in item for item in report["missing"]))
        self.assertTrue(any("source scope" in item for item in report["missing"]))

    def test_capture_rejects_credential_fields_without_echoing_values(self):
        payload = complete_capture()
        payload["credentials"] = {"api_key": "local-secret-value"}
        report = _preflight_report(payload)
        self.assertEqual(report["capture_structure"], "INCOMPLETE")
        self.assertTrue(any("credential material" in item for item in report["missing"]))
        self.assertNotIn("local-secret-value", str(report))

    def test_bad_limits_and_write_scope_are_reported(self):
        payload = {
            "semantic_version": "v1", "permission_scope": {"read_only": False},
            "operations": {}, "limits": {"max_rows": True, "max_bytes": 0, "timeout_seconds": 1},
            "auth_scope": "", "audit_supported": False, "cancel_supported": False,
        }
        report = _preflight_report(payload)
        self.assertEqual(report["capture_structure"], "INCOMPLETE")
        self.assertTrue(any("read-only" in item for item in report["missing"]))
        self.assertTrue(any("max_rows" in item for item in report["missing"]))


if __name__ == "__main__":
    unittest.main()
