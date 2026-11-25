"""Capture a full offline synthetic MCP read-to-evidence workflow."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "qualification" / "evidence" / "mcp-end-to-end-workflow.json"
sys.path.insert(0, str(ROOT))

from fabintel.mcp_adapter import ConfiguredMCPAdapter
from fabintel.mcp_workflow import investigate_with_mcp


async def main():
    config = {
        "schema_version": "p2-mcp-client-config/v1",
        "transport": {
            "kind": "stdio",
            "command": sys.executable,
            "args": ["-m", "fabintel.synthetic_mcp_server", "--scenario", "engineer-complete"],
            "cwd": str(ROOT),
        },
        "tools": {name: name for name in (
            "discover", "semantics", "relationships", "read_bounded", "cancel", "audit",
        )},
        "request_timeout_seconds": 8,
        "max_response_bytes": 32768,
    }
    plan = {
        "source_ids": ["SYN_PROCESS", "SYN_OUTCOMES", "SYN_EXPOSURE_COVERAGE", "SYN_HISTORY_COVERAGE", "SYN_ROUTE_DEFINITIONS", "SYN_ROUTE_COVERAGE"],
        "relationship_ids": ["SYN_REL_WAFER_STEP", "SYN_REL_WAFER_OUTCOME", "SYN_REL_EXPOSURE_COVERAGE", "SYN_REL_HISTORY_COVERAGE", "SYN_REL_ROUTE_DEFINITION", "SYN_REL_ROUTE_COVERAGE"],
        "time_window": {"start": "2026-11-21T00:00:00+00:00", "end": "2026-11-22T00:00:00+00:00"},
        "read_plans": [
            {"source_ids": ["SYN_PROCESS"], "relationship_ids": ["SYN_REL_WAFER_STEP"], "time_field": "timestamp", "dataset_role": "events"},
            {"source_ids": ["SYN_OUTCOMES"], "relationship_ids": ["SYN_REL_WAFER_OUTCOME"], "time_field": "timestamp", "dataset_role": "outcomes"},
            {"source_ids": ["SYN_EXPOSURE_COVERAGE"], "relationship_ids": ["SYN_REL_EXPOSURE_COVERAGE"], "time_field": "timestamp", "dataset_role": "coverage"},
            {"source_ids": ["SYN_HISTORY_COVERAGE"], "relationship_ids": ["SYN_REL_HISTORY_COVERAGE"], "time_field": "timestamp", "dataset_role": "history_coverage"},
            {"source_ids": ["SYN_ROUTE_DEFINITIONS"], "relationship_ids": ["SYN_REL_ROUTE_DEFINITION"], "time_field": "timestamp", "dataset_role": "route_definitions"},
            {"source_ids": ["SYN_ROUTE_COVERAGE"], "relationship_ids": ["SYN_REL_ROUTE_COVERAGE"], "time_field": "timestamp", "dataset_role": "route_coverage"},
        ],
    }
    async with ConfiguredMCPAdapter(config) as adapter:
        evidence = await investigate_with_mcp(
            adapter,
            plan,
            "SYNTHETIC_READ",
            {"max_rows": 30, "max_bytes": 30000, "max_seconds": 5},
            [
                {"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": "SYN-W1"},
                {"source_id": "SYN_OUTCOMES", "entity_type": "wafer", "entity_id": "SYN-W1"},
                {"source_id": "SYN_EXPOSURE_COVERAGE", "entity_type": "exposure_coverage", "entity_id": "SYN-COV-1"},
                {"source_id": "SYN_HISTORY_COVERAGE", "entity_type": "history_coverage", "entity_id": "SYN-HISTORY-COV-1"},
                {"source_id": "SYN_ROUTE_DEFINITIONS", "entity_type": "route_definition", "entity_id": "SYN-BASE-v1"},
                {"source_id": "SYN_ROUTE_COVERAGE", "entity_type": "route_coverage", "entity_id": "SYN-ROUTE-COV-1"},
            ],
            suspected_exposure={
                "chamber_id": "SYN-C1",
                "start": "2026-11-21T03:00:00+00:00",
                "end": "2026-11-21T06:00:00+00:00",
            },
    )
    OUTPUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with status {evidence['status']} in {evidence['mode']} mode.")


if __name__ == "__main__":
    asyncio.run(main())
