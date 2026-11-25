"""Reproducible descriptor-only scan benchmark; no MCP connection or source rows."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import platform
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fabintel.catalog import synthetic_catalog
from fabintel.onboarding import propose_mappings


CAPTURE = ROOT / "qualification/fixtures/onboarding_descriptor_capture_synthetic_v1.json"
OUTPUT = ROOT / "qualification/evidence/onboarding-13k-descriptor-benchmark.json"
EXPECTED_SOURCE_IDS = {
    "events": "SITE_EVENTS_ALIAS", "outcomes": "SITE_OUTCOMES_ALIAS",
    "coverage": "SITE_COVERAGE_ALIAS", "history_coverage": "SITE_HISTORY_ALIAS",
    "route_definitions": "SITE_ROUTE_DEFINITION_ALIAS",
    "route_coverage": "SITE_ROUTE_COVERAGE_ALIAS",
    "material_relationships": "SITE_MATERIAL_ALIAS",
}


def main() -> None:
    capture = json.loads(CAPTURE.read_text(encoding="utf8"))
    distractors = synthetic_catalog(13000)
    capture["sources"].extend({
        "source_id": item["id"], "record_kind": None, "approved": item["approved"],
        "grain": "unknown", "column_definitions": {},
    } for item in distractors)

    bad_clock = copy.deepcopy(capture["sources"][0])
    bad_clock["source_id"] = "SYN_BAD_EVENT_CLOCK"
    bad_clock["source_hash"] = "0" * 64
    bad_clock["column_definitions"]["processed_at"]["timezone_required"] = False
    capture["sources"].append(bad_clock)
    bad_relation = copy.deepcopy(capture["relationships"][0])
    bad_relation["id"] = "SYN_BAD_EVENT_CLOCK_REL"
    bad_relation["source_ids"] = [bad_clock["source_id"]]
    bad_relation["source_reference"] = {
        "source_ids": [bad_clock["source_id"]], "source_hash": bad_clock["source_hash"],
        "semantic_version": bad_clock["semantic_version"],
    }
    capture["relationships"].append(bad_relation)

    tracemalloc.start()
    started = time.perf_counter()
    report = propose_mappings(capture)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    actual_source_ids = {
        role: proposal["candidates"][0]["source_id"]
        for role, proposal in report["source_role_proposals"].items()
        if proposal["candidate_state"] == "UNIQUE_REVIEW_REQUIRED"
    }
    compatible_tool_mappings = sum(
        int(value["candidate_state"] == "UNIQUE_REVIEW_REQUIRED"
            and bool(value["tool_version_by_name"].get(value["candidate_tool_names"][0])))
        for value in report["operation_proposals"].values()
        if value["candidate_tool_names"]
    )
    bad_clock = next(item for item in report["source_role_proposals"]["events"]["candidates"]
                     if item.get("source_id") == "SYN_BAD_EVENT_CLOCK")
    result = {
        "qualification": "SYNTHETIC_DESCRIPTOR_SCAN_ONLY",
        "python_version": platform.python_version(), "platform": platform.platform(),
        "catalog_descriptors_examined": report["catalog_descriptors_examined"],
        "source_role_mapping_accuracy": {
            "correct_unique_candidates": sum(actual_source_ids.get(role) == source_id
                                              for role, source_id in EXPECTED_SOURCE_IDS.items()),
            "expected_roles": len(EXPECTED_SOURCE_IDS),
            "false_positive_candidates": sum(
                item.get("candidate_state") == "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED"
                and item.get("source_id") != EXPECTED_SOURCE_IDS.get(role)
                for role, proposal in report["source_role_proposals"].items()
                for item in proposal["candidates"]
            ),
        },
        "logical_tool_mapping_accuracy": {
            "unique_versioned_candidates": compatible_tool_mappings,
            "expected_operations": 6,
        },
        "incorrect_semantic_decoys_rejected": bad_clock["candidate_state"] != "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED",
        "review_decision_count": len(report["required_manual_decisions"]),
        "query_plan_proposals": len(report["bounded_query_plan_proposals"]),
        "automated_scan_elapsed_ms": round(elapsed_ms, 3),
        "peak_traced_memory_bytes": peak_bytes,
        "network_calls": 0, "reads_executed": False,
        "authorization_or_company_approval": "NOT_ESTABLISHED",
        "human_setup_time": "NOT_MEASURED",
        "meaning": "Scan time and mapping counts are synthetic harness measurements; they do not estimate company onboarding time or source correctness.",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
