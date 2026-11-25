"""Fixed-answer checks for untrusted, offline P2 descriptor mapping proposals."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fabintel.catalog import synthetic_catalog
from fabintel.cli import main as cli_main
from fabintel.onboarding import propose_mappings


def _column(kind, *, entity=None, meaning=None, timezone=False, values=None):
    result = {"type": kind}
    if entity:
        result["entity"] = entity
    if meaning:
        result["meaning"] = meaning
    if kind == "timestamp":
        result["timezone_required"] = timezone
    if values:
        result["values"] = values
    return result


def _tool(name, description, required, types):
    return {
        "name": name, "description": description,
        "inputSchema": {
            "type": "object", "required": required,
            "properties": {key: {"type": value} for key, value in types.items()},
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    }


def _capture():
    params = {
        "discover": ([], {}),
        "semantics": (["source_ids"], {"source_ids": "array"}),
        "relationships": (["entity_refs", "time_window"], {"entity_refs": "array", "time_window": "object"}),
        "read_bounded": (["approved_plan", "permission_context", "limits", "operation_id"], {
            "approved_plan": "object", "permission_context": "string", "limits": "object", "operation_id": "string",
        }),
        "cancel": (["operation_id"], {"operation_id": "string"}),
        "audit": (["operation_id"], {"operation_id": "string"}),
    }
    cues = {
        "discover": "Inspect read-only capabilities",
        "semantics": "Read source semantics and definitions",
        "relationships": "Inspect approved relationships and join keys",
        "read_bounded": "Read bounded source rows",
        "cancel": "Cancel a running request",
        "audit": "Read audit trace for a request",
    }
    tools = [_tool(f"site_{name}_v4", cues[name], *params[name]) for name in params]
    versions = {item["name"]: "4.2.1" for item in tools}
    sources, relationships = [], []

    def add_source(role, record_kind, columns, relationship_type=None, relationship_keys=None):
        source_id = f"SITE_{role.upper()}_ALIAS"
        version = "site-sem-2026.11"
        digest = hashlib.sha256(source_id.encode()).hexdigest()
        source = {
            "source_id": source_id, "record_kind": record_kind, "approved": True,
            "semantic_version": version, "source_hash": digest,
            "grain": f"one {record_kind.lower()} record",
            "effectivity": {"start": "2026-01-01T00:00:00Z", "end": "2027-01-01T00:00:00Z"},
            "column_definitions": columns,
        }
        relation = {
            "id": f"SITE_REL_{role.upper()}_ALIAS", "approved": True,
            "source_ids": [source_id], "keys": relationship_keys or list(columns),
            "cardinality": "one declared row to one source record",
            "grain": source["grain"],
            "effective_start": "2026-01-01T00:00:00Z", "effective_end": "2027-01-01T00:00:00Z",
            "relationship_type": relationship_type,
            "source_reference": {"source_ids": [source_id], "source_hash": digest, "semantic_version": version},
        }
        sources.append(source)
        relationships.append(relation)

    add_source("events", "PROCESS_STEP_INSTANCE", {
        "wafer_ref": _column("identifier", entity="wafer"),
        "operation_instance": _column("identifier", entity="process_step_instance"),
        "processed_at": _column("timestamp", meaning="event time", timezone=True),
        "performed_op": _column("string", entity="operation", meaning="actual performed operation"),
        "tool_asset": _column("identifier", entity="tool"),
        "chamber_asset": _column("identifier", entity="chamber"),
        "lot_ref": _column("identifier", entity="lot"),
    })
    add_source("outcomes", "WAFER_OUTCOME", {
        "wafer_ref": _column("identifier", entity="wafer"),
        "result_state": _column("enum", values=["ABNORMAL", "NORMAL"]),
        "result_time": _column("timestamp", meaning="outcome time", timezone=True),
    })
    add_source("material", "MATERIAL_RELATIONSHIP", {
        "edge_id": _column("identifier", entity="relationship_record"),
        "parent_lot": _column("identifier", entity="lot"),
        "parent_kind": _column("string", meaning="from entity type"),
        "member_wafer": _column("identifier", entity="wafer"),
        "member_kind": _column("string", meaning="to entity type"),
        "valid_from": _column("timestamp", meaning="effective start", timezone=True),
        "valid_to": _column("timestamp", meaning="effective end", timezone=True),
        "source_seen_at": _column("timestamp", meaning="source observation time", timezone=True),
    }, relationship_type="LOT_MEMBERSHIP", relationship_keys=[
        "edge_id", "parent_lot", "parent_kind", "member_wafer", "member_kind", "source_seen_at",
    ])
    coverage_columns = {
        "coverage_ref": _column("identifier", entity="coverage_record"),
        "is_complete": _column("boolean"),
        "wafers_in_scope": _column("identifier_list", entity="wafer"),
        "lots_in_scope": _column("identifier_list", entity="lot"),
        "operations_in_scope": _column("identifier_list", entity="operation"),
        "sources_in_scope": _column("identifier_list", entity="source", meaning="sources covered by scope"),
        "source_refs": _column("identifier_list", entity="source", meaning="coverage record source identifiers"),
        "population_grain": _column("string", meaning="population identity grain"),
        "authority_label": _column("string", meaning="authority label claim"),
        "scope_start": _column("timestamp", meaning="window start", timezone=True),
        "scope_end": _column("timestamp", meaning="window end", timezone=True),
        "expires_at": _column("timestamp", meaning="valid until", timezone=True),
        "missing_refs": _column("identifier_list", entity="record"),
        "captured_at": _column("timestamp", meaning="source observation time", timezone=True),
    }
    add_source("coverage", "EXPOSURE_COVERAGE", copy.deepcopy(coverage_columns))
    add_source("history", "PROCESS_HISTORY_COVERAGE", copy.deepcopy(coverage_columns))
    add_source("route_coverage", "ROUTE_COVERAGE", copy.deepcopy(coverage_columns))
    add_source("route_definition", "ROUTE_DEFINITION", {
        "route_ref": _column("identifier", entity="route"),
        "version_ref": _column("identifier", entity="route_version"),
        "definition_approved": _column("boolean"),
        "ordered_ops": _column("ordered_string_list"),
        "valid_sequences": _column("list_of_ordered_string_lists"),
        "defined_at": _column("timestamp", meaning="route definition record time", timezone=True),
    })
    return {
        "capture_mode": "SYNTHETIC_TEST_ONLY", "tools": tools, "tool_versions": versions,
        "sources": sources, "relationships": relationships,
        "limits": {"max_rows": 100, "max_bytes": 32768, "max_seconds": 5},
    }


def _renamed_environment_capture():
    capture = _capture()
    field_names = {
        "wafer_ref": "wafer_identifier", "operation_instance": "step_occurrence_id",
        "processed_at": "processed_timestamp", "performed_op": "operation_performed",
        "tool_asset": "tool_identifier", "chamber_asset": "chamber_identifier",
        "lot_ref": "lot_identifier", "result_state": "outcome_label",
        "result_time": "outcome_timestamp", "edge_id": "membership_record_id",
        "parent_lot": "lot_parent_identifier", "parent_kind": "parent_entity_type",
        "member_wafer": "wafer_child_identifier", "member_kind": "child_entity_type",
        "valid_from": "membership_start", "valid_to": "membership_end",
        "source_seen_at": "descriptor_observed_at", "coverage_ref": "coverage_identifier",
        "is_complete": "complete_scope", "wafers_in_scope": "wafer_scope_ids",
        "lots_in_scope": "lot_scope_ids", "operations_in_scope": "operation_scope_ids",
        "sources_in_scope": "covered_source_ids", "source_refs": "scope_source_ids",
        "population_grain": "population_level", "authority_label": "authority_assertion",
        "scope_start": "validity_start", "scope_end": "validity_end",
        "expires_at": "scope_expiry", "missing_refs": "missing_record_refs",
        "captured_at": "descriptor_timestamp", "route_ref": "route_identifier",
        "version_ref": "route_version_identifier", "definition_approved": "route_is_approved",
        "ordered_ops": "ordered_operation_codes", "valid_sequences": "alternative_operation_orders",
        "defined_at": "route_document_time",
    }
    source_ids = {}
    source_hashes = {}
    for source in capture["sources"]:
        old_id = source["source_id"]
        source["source_id"] = old_id.replace("SITE_", "FABX_")
        source_ids[old_id] = source["source_id"]
        source["source_hash"] = hashlib.sha256(source["source_id"].encode()).hexdigest()
        source_hashes[source["source_id"]] = source["source_hash"]
        source["column_definitions"] = {
            field_names.get(name, name): value
            for name, value in source["column_definitions"].items()
        }
    for relation in capture["relationships"]:
        relation["id"] = relation["id"].replace("SITE_REL_", "FABX_REL_")
        relation["source_ids"] = [source_ids[item] for item in relation["source_ids"]]
        relation["keys"] = [field_names.get(name, name) for name in relation["keys"]]
        relation["source_reference"] = {
            "source_ids": list(relation["source_ids"]),
            "source_hash": source_hashes[relation["source_ids"][0]],
            "semantic_version": relation["source_reference"]["semantic_version"],
        }
    names = {}
    for tool in capture["tools"]:
        old_name = tool["name"]
        tool["name"] = old_name.replace("site_", "fabsvc__")
        names[old_name] = tool["name"]
        tool["inputSchema"]["additionalProperties"] = False
    capture["tool_versions"] = {names[name]: version for name, version in capture["tool_versions"].items()}
    return capture


class OnboardingProposalTests(unittest.TestCase):
    def test_renamed_tools_and_semantic_field_aliases_map_as_review_only_candidates(self):
        capture = _capture()
        report = propose_mappings(capture)
        self.assertEqual(report["state"], "REVIEW_REQUIRED")
        self.assertEqual(report["catalog_descriptors_examined"], 7)
        self.assertEqual({name: value["candidate_tool_names"][0]
                          for name, value in report["operation_proposals"].items()},
                         {name: f"site_{name}_v4" for name in
                          ("discover", "semantics", "relationships", "read_bounded", "cancel", "audit")})
        self.assertEqual({name for name, value in report["source_role_proposals"].items()
                          if value["candidate_state"] == "UNIQUE_REVIEW_REQUIRED"},
                         {"events", "outcomes", "coverage", "history_coverage", "route_definitions",
                          "route_coverage", "material_relationships"})
        process = report["source_role_proposals"]["events"]["candidates"][0]
        self.assertEqual(process["field_mapping"]["wafer_id"], "wafer_ref")
        self.assertEqual(process["field_mapping"]["event_time"], "processed_at")
        self.assertEqual(process["field_mapping"]["chamber_id"], "chamber_asset")
        membership = report["source_role_proposals"]["material_relationships"]["candidates"][0]
        self.assertEqual(membership["field_mapping"]["from_entity_id"], "parent_lot")
        self.assertEqual(membership["field_mapping"]["to_entity_id"], "member_wafer")
        self.assertEqual(membership["relationship_id"], "SITE_REL_MATERIAL_ALIAS")
        self.assertEqual(report["bounded_query_plan_proposals"][0]["authorization_state"], "REVIEW_REQUIRED_NOT_EXECUTED")
        self.assertEqual(len(report["bounded_query_plan_proposals"]), 7)
        self.assertFalse(report["company_qualified"])
        self.assertFalse(report["server_authorization_established"])
        self.assertFalse(report["reads_executed"])
        self.assertFalse(report["relationships_joined"])
        self.assertEqual(report["capture_origin_verification"], "NOT_ESTABLISHED")

    def test_second_synthetic_environment_maps_different_source_and_field_conventions(self):
        capture = _renamed_environment_capture()
        report = propose_mappings(capture)
        self.assertEqual(report["state"], "REVIEW_REQUIRED")
        self.assertEqual(report["operation_proposals"]["read_bounded"]["candidate_tool_names"],
                         ["fabsvc__read_bounded_v4"])
        process = report["source_role_proposals"]["events"]["candidates"][0]
        self.assertEqual(process["source_id"], "FABX_EVENTS_ALIAS")
        self.assertEqual(process["field_mapping"]["wafer_id"], "wafer_identifier")
        self.assertEqual(process["field_mapping"]["event_time"], "processed_timestamp")
        self.assertEqual(process["relationship_id"], "FABX_REL_EVENTS_ALIAS")
        self.assertFalse(report["company_qualified"])

    def test_two_process_event_timestamps_abstain_with_a_specific_review_question(self):
        capture = _capture()
        events = capture["sources"][0]
        events["column_definitions"]["execution_time"] = copy.deepcopy(
            events["column_definitions"]["processed_at"]
        )
        report = propose_mappings(capture)
        proposal = report["source_role_proposals"]["events"]
        self.assertEqual(proposal["candidate_state"], "NO_STRUCTURALLY_COMPATIBLE_SOURCE")
        self.assertIsNone(proposal["preferred_candidate_source_id"])
        candidate = proposal["candidates"][0]
        diagnostic = next(item for item in candidate["diagnostics"]
                          if item["code"] == "AMBIGUOUS_PROCESS_EVENT_TIME")
        self.assertEqual(set(diagnostic["fields"]), {"processed_at", "execution_time"})
        self.assertIn("Which source field", diagnostic["question"])

    def test_split_merge_descriptors_are_reported_without_being_mapped_as_membership(self):
        capture = _capture()
        membership = next(item for item in capture["relationships"]
                          if item["relationship_type"] == "LOT_MEMBERSHIP")
        for kind in ("LOT_SPLIT", "LOT_MERGE"):
            capture["relationships"].append({
                **copy.deepcopy(membership), "id": f"SITE_REL_{kind}",
                "relationship_type": kind,
            })
        proposal = propose_mappings(capture)["source_role_proposals"]["material_relationships"]
        self.assertEqual(proposal["candidate_state"], "UNIQUE_REVIEW_REQUIRED")
        candidate = proposal["candidates"][0]
        self.assertEqual(candidate["relationship_id"], membership["id"])
        diagnostic = next(item for item in candidate["diagnostics"]
                          if item["code"] == "MATERIAL_LINEAGE_RELATIONSHIP_UNMAPPED")
        self.assertEqual(diagnostic["relationship_types"], ["LOT_MERGE", "LOT_SPLIT"])
        self.assertTrue(candidate["requires_authorized_review"])

    def test_ambiguous_or_unannotated_tools_and_bad_semantic_sources_are_not_promoted(self):
        capture = _capture()
        ambiguous = copy.deepcopy(capture["tools"][0])
        ambiguous["name"] = "second_capability_probe"
        capture["tools"].append(ambiguous)
        unannotated = copy.deepcopy(capture["tools"][3])
        unannotated["name"] = "unsafe_read"
        unannotated["annotations"]["destructiveHint"] = True
        capture["tools"].append(unannotated)
        capture["tool_versions"].update({"second_capability_probe": "1.0", "unsafe_read": "1.0"})

        bad = copy.deepcopy(capture["sources"][0])
        bad["source_id"] = "BAD_EVENT_CLOCK"
        bad["source_hash"] = hashlib.sha256(b"BAD_EVENT_CLOCK").hexdigest()
        bad["column_definitions"]["processed_at"]["timezone_required"] = False
        capture["sources"].append(bad)
        capture["relationships"].append({
            **copy.deepcopy(capture["relationships"][0]),
            "id": "BAD_CLOCK_REL", "source_ids": ["BAD_EVENT_CLOCK"],
            "source_reference": {"source_ids": ["BAD_EVENT_CLOCK"], "source_hash": bad["source_hash"],
                                 "semantic_version": bad["semantic_version"]},
        })
        report = propose_mappings(capture)
        self.assertEqual(report["operation_proposals"]["discover"]["candidate_state"], "AMBIGUOUS")
        self.assertNotIn("unsafe_read", report["operation_proposals"]["read_bounded"]["candidate_tool_names"])
        self.assertEqual(report["source_role_proposals"]["events"]["candidate_state"], "UNIQUE_REVIEW_REQUIRED")
        self.assertEqual(report["source_role_proposals"]["events"]["candidates"][1]["candidate_state"],
                         "MISSING_REQUIRED_SEMANTICS_OR_RELATIONSHIP")
        self.assertEqual(report["state"], "DIAGNOSTIC_DECISIONS_REQUIRED")

    def test_duplicate_descriptor_identity_invalidates_mapping_and_nested_rows_are_refused(self):
        capture = _capture()
        capture["relationships"].append(copy.deepcopy(capture["relationships"][0]))
        report = propose_mappings(capture)
        self.assertIn("SITE_REL_EVENTS_ALIAS", report["descriptor_diagnostics"]["duplicate_relationship_ids_rejected"])
        self.assertEqual(report["source_role_proposals"]["events"]["candidate_state"],
                         "NO_STRUCTURALLY_COMPATIBLE_SOURCE")
        self.assertEqual(report["state"], "DIAGNOSTIC_DECISIONS_REQUIRED")

        capture = _capture()
        capture["sources"][0]["snapshot"] = {"typed_rows": [{"wafer_ref": "SYN-NOT-ALLOWED"}]}
        with self.assertRaisesRegex(ValueError, "descriptors only"):
            propose_mappings(capture)

        malformed = _capture()
        malformed["limits"] = None
        malformed["tool_versions"] = "not-a-version-map"
        report = propose_mappings(malformed)
        self.assertEqual(report["state"], "DIAGNOSTIC_DECISIONS_REQUIRED")
        self.assertEqual(report["descriptor_diagnostics"]["invalid_capture_sections"], ["tool_versions", "limits"])

    def test_13000_name_only_catalog_descriptors_do_not_create_source_mappings(self):
        capture = _capture()
        distractors = synthetic_catalog(13000)
        capture["sources"].extend({
            "source_id": item["id"], "record_kind": None, "approved": item["approved"],
            "grain": "unknown", "column_definitions": {},
        } for item in distractors)
        report = propose_mappings(capture)
        self.assertEqual(report["catalog_descriptors_examined"], 13007)
        self.assertEqual(report["source_role_proposals"]["events"]["candidate_state"], "UNIQUE_REVIEW_REQUIRED")
        self.assertEqual(len(report["source_role_proposals"]["events"]["candidates"]), 1)
        self.assertNotIn("approved_join", str(report))

    def test_cli_writes_only_a_review_proposal_and_rejects_embedded_source_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture_path = Path(temporary) / "capture.json"
            report_path = Path(temporary) / "proposal.json"
            capture_path.write_text(json.dumps(_capture()), encoding="utf8")
            with patch("sys.argv", ["fabintel", "onboard", "--descriptors", str(capture_path),
                                     "--output", str(report_path)]):
                self.assertEqual(cli_main(), 0)
            report = json.loads(report_path.read_text(encoding="utf8"))
            self.assertFalse(report["reads_executed"])
            self.assertEqual(report["state"], "REVIEW_REQUIRED")

            unsafe = _capture()
            unsafe["events"] = [{"wafer_ref": "SYN-ONLY"}]
            with self.assertRaisesRegex(ValueError, "descriptors only"):
                propose_mappings(unsafe)


if __name__ == "__main__":
    unittest.main()
