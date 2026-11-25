"""Product-neutral local runner for the synthetic P2 reference workflow."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import uuid
from typing import Any

from fabintel.mcp_adapter import ConfiguredMCPAdapter, MCPContractError
from fabintel.mcp_workflow import _normalize_mapped_row, investigate_with_mcp
from fabintel.onboarding_pipeline import (
    materialize_live_review, propose_from_live_mcp_metadata, verify_materialized_config,
)


ROOT = Path(__file__).resolve().parent.parent
TIME_WINDOW = {
    "start": "2026-11-21T00:00:00+00:00",
    "end": "2026-11-22T00:00:00+00:00",
}
LIMITS = {"max_rows": 30, "max_bytes": 30000, "max_seconds": 5}
SOURCE_IDS = [
    "SYN_PROCESS", "SYN_OUTCOMES", "SYN_EXPOSURE_COVERAGE",
    "SYN_HISTORY_COVERAGE", "SYN_ROUTE_DEFINITIONS", "SYN_ROUTE_COVERAGE",
    "SYN_MATERIAL",
]
RELATIONSHIP_IDS = [
    "SYN_REL_WAFER_STEP", "SYN_REL_WAFER_OUTCOME", "SYN_REL_EXPOSURE_COVERAGE",
    "SYN_REL_HISTORY_COVERAGE", "SYN_REL_ROUTE_DEFINITION", "SYN_REL_ROUTE_COVERAGE",
    "SYN_REL_WAFER_LOT_MEMBERSHIP",
]
_ALIAS_MCP_SCENARIOS = {
    "engineer-100-alias", "engineer-100-alt-alias", "engineer-100-alt-alias-13k",
}
READ_PLANS = [
    {"source_ids": ["SYN_PROCESS"], "relationship_ids": ["SYN_REL_WAFER_STEP"], "time_field": "timestamp", "dataset_role": "events"},
    {"source_ids": ["SYN_OUTCOMES"], "relationship_ids": ["SYN_REL_WAFER_OUTCOME"], "time_field": "timestamp", "dataset_role": "outcomes"},
    {"source_ids": ["SYN_EXPOSURE_COVERAGE"], "relationship_ids": ["SYN_REL_EXPOSURE_COVERAGE"], "time_field": "timestamp", "dataset_role": "coverage"},
    {"source_ids": ["SYN_HISTORY_COVERAGE"], "relationship_ids": ["SYN_REL_HISTORY_COVERAGE"], "time_field": "timestamp", "dataset_role": "history_coverage"},
    {"source_ids": ["SYN_ROUTE_DEFINITIONS"], "relationship_ids": ["SYN_REL_ROUTE_DEFINITION"], "time_field": "timestamp", "dataset_role": "route_definitions"},
    {"source_ids": ["SYN_ROUTE_COVERAGE"], "relationship_ids": ["SYN_REL_ROUTE_COVERAGE"], "time_field": "timestamp", "dataset_role": "route_coverage"},
    {"source_ids": ["SYN_MATERIAL"], "relationship_ids": ["SYN_REL_WAFER_LOT_MEMBERSHIP"], "time_field": "timestamp", "dataset_role": "material_relationships"},
]
ENGINEER_PLAN = {
    "source_ids": SOURCE_IDS,
    "relationship_ids": RELATIONSHIP_IDS,
    "time_window": TIME_WINDOW,
    "read_plans": READ_PLANS,
}


def synthetic_adapter_config(*, delay_ms: int = 0, scenario: str = "engineer-complete") -> dict[str, Any]:
    tool_prefix = "fabsvc__" if "alias" in scenario else ""
    args = ["-m", "fabintel.synthetic_mcp_server", "--scenario", scenario]
    if tool_prefix:
        args.extend(["--tool-prefix", tool_prefix])
    if delay_ms:
        args.extend(["--delay-ms", str(delay_ms)])
    transport = {"kind": "stdio", "command": sys.executable, "args": args, "cwd": str(ROOT)}
    if os.environ.get("P2_TEST_SDK_PATH"):
        transport["environment"] = {"PYTHONPATH": "P2_TEST_SDK_PATH"}
    return {
        "schema_version": "p2-mcp-client-config/v1",
        "transport": transport,
        "tools": {name: name for name in ("discover", "semantics", "relationships", "read_bounded", "cancel", "audit")},
        "request_timeout_seconds": 8,
        "max_response_bytes": 8388608 if scenario.startswith("engineer-100") else 32768,
    }


def configured_reference_scenario() -> str:
    scenario = os.environ.get("P2_REFERENCE_SYNTHETIC_SCENARIO", "engineer-complete")
    if scenario not in {"engineer-complete", "engineer-100", *_ALIAS_MCP_SCENARIOS}:
        raise ValueError("P2_REFERENCE_SYNTHETIC_SCENARIO must be engineer-complete, engineer-100, or a declared engineer-100 alias fixture.")
    return scenario


def scenario_limits(scenario: str) -> dict[str, int | float]:
    return {"max_rows": 1000, "max_bytes": 4194304, "max_seconds": 30} if scenario.startswith("engineer-100") else LIMITS


def scenario_window(scenario: str) -> dict[str, str]:
    return {"start": "2026-11-20T00:00:00+00:00", "end": "2026-11-30T00:00:00+00:00"} if scenario.startswith("engineer-100") else TIME_WINDOW


def _synthetic_alias_transport(scenario: str) -> dict[str, Any]:
    return synthetic_adapter_config(scenario=scenario)["transport"]


async def _synthetic_alias_review(scenario: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Discover, propose, and digest-bind the local synthetic alias mapping.

    This deterministic reviewer exists only for the offline acceptance fixture.
    Production/source onboarding continues to require an engineer-supplied review.
    """
    window = scenario_window(scenario)
    client = synthetic_adapter_config(scenario=scenario)
    report = await propose_from_live_mcp_metadata(
        client["transport"], time_window=window,
        request_timeout_seconds=client["request_timeout_seconds"],
        max_response_bytes=client["max_response_bytes"],
    )
    if report.get("bounded_row_reads_executed") is not False:
        raise MCPContractError("Synthetic onboarding discovery unexpectedly read source rows.")
    decisions = {
        "decision": "APPROVE_EXACT_PROPOSAL",
        "proposal_sha256": report["proposal_sha256"],
        "descriptor_capture_sha256": report["descriptor_capture_sha256"],
        "reviewer_id": "SYNTHETIC_ACCEPTANCE_REVIEWER_ONLY",
        "time_window": window,
        "limits": report["capture"]["limits"],
        "permission_scope": "SYNTHETIC_READ",
    }
    reviewed = materialize_live_review(report, decisions)
    verify_materialized_config(reviewed, report["proposal"])
    verify = {
        "mode": "SYNTHETIC_FIXTURE_ONLY",
        "mcp_protocol_version": report.get("mcp_protocol_version"),
        "proposal_sha256": report["proposal_sha256"],
        "decision": reviewed["review"]["decision"],
        "reviewer_id": reviewed["review"]["reviewer_id"],
        "server_authorization_established": reviewed["server_authorization_established"],
        "company_qualified": reviewed["company_qualified"],
        "source_role_mappings": [
            {
                "dataset_role": plan["dataset_role"],
                "source_id": plan["source_ids"][0],
                "relationship_id": plan["relationship_ids"][0],
                "time_field": plan["time_field"],
                "field_mapping": plan["field_mapping"],
                "relationship_type": plan.get("relationship_type"),
            }
            for plan in reviewed["approved_plan"]["read_plans"]
        ],
    }
    runtime = {
        "schema_version": "p2-mcp-client-config/v1",
        "transport": client["transport"],
        "tools": reviewed["mcp_tools"],
        "request_timeout_seconds": client["request_timeout_seconds"],
        "max_response_bytes": client["max_response_bytes"],
    }
    return reviewed, runtime, verify


async def _read_alias_reference_options() -> dict[str, Any]:
    scenario = configured_reference_scenario()
    reviewed, runtime, onboarding = await _synthetic_alias_review(scenario)
    window, limits = scenario_window(scenario), reviewed["limits"]
    approved_plan = reviewed["approved_plan"]
    plans_by_role = {plan["dataset_role"]: plan for plan in approved_plan["read_plans"]}
    async with ConfiguredMCPAdapter(runtime) as adapter:
        discovery = await adapter.discover()
        semantic_response = await adapter.semantics(approved_plan["source_ids"])
        relationships = await adapter.relationships([
            {"source_id": source_id, "entity_type": "source", "entity_id": source_id}
            for source_id in approved_plan["source_ids"]
        ], window)
        relation_ids = {item.get("id") for item in relationships.get("relationships", [])
                        if isinstance(item, dict) and item.get("approved") is True}
        if set(approved_plan["relationship_ids"]) - relation_ids:
            raise MCPContractError("Reviewed synthetic relationship descriptors changed before option reads.")
        rows_by_role: dict[str, list[dict[str, Any]]] = {}
        reads = []
        for role in ("outcomes", "events"):
            plan = plans_by_role[role]
            operation_id = str(uuid.uuid4())
            result = await adapter.read_bounded(
                plan, reviewed["permission_scope"], limits, operation_id=operation_id,
            )
            audit = await adapter.audit(operation_id)
            if audit.get("query_hash") != result.get("query_hash"):
                raise MCPContractError("Alias-schema option audit hash does not match its bounded read.")
            rows = result.get("typed_rows")
            if not isinstance(rows, list) or result.get("truncated") is True:
                raise MCPContractError("Alias-schema option read was malformed or truncated.")
            rows_by_role[role] = [_normalize_mapped_row(plan, row) for row in rows]
            reads.append({
                "dataset_role": role, "operation_id": operation_id, "audit_id": result["audit_id"],
                "query_hash": result["query_hash"], "row_count": len(rows),
                "source_ids": result["source_ids"], "relationship_ids": result["relationship_ids"],
                "source_versions": result["source_versions"],
            })
    outcomes = [row for row in rows_by_role["outcomes"] if row.get("label") in {"ABNORMAL", "NORMAL"}]
    events = rows_by_role["events"]
    cohort = sorted({row["wafer_id"] for row in outcomes if isinstance(row.get("wafer_id"), str)})
    abnormal = sorted({row["wafer_id"] for row in outcomes if row.get("label") == "ABNORMAL"})
    chambers = sorted({row["chamber_id"] for row in events if isinstance(row.get("chamber_id"), str)})
    tools = sorted({row["tool_id"] for row in events if isinstance(row.get("tool_id"), str)})
    return {
        "mode": "SYNTHETIC_PROTOCOL_COMPATIBILITY_ONLY",
        "protocol_version": onboarding["mcp_protocol_version"],
        "default_suspected_exposure": {
            "chamber_id": "SYN-C1", "start": "2026-11-21T01:25:00+00:00",
            "end": "2026-11-21T01:35:00+00:00",
        },
        "cohort_wafer_ids": cohort, "abnormal_wafer_ids": abnormal,
        "chamber_ids": chambers, "tool_ids": tools,
        "sources": [
            {"id": source["source_id"], "source_hash": source["source_hash"]}
            for source in semantic_response["sources"]
        ],
        "audited_reads": reads,
        "onboarding": onboarding,
        "company_source_authorized": False,
        "mock_peer_permission_enforced": True,
        "discovered_auth_scopes": discovery["auth_scopes"],
    }


def _entity_refs(target_wafer_ids: list[str]) -> list[dict[str, str]]:
    refs = [
        ref
        for target in target_wafer_ids
        for ref in (
            {"source_id": "SYN_PROCESS", "entity_type": "wafer", "entity_id": target},
            {"source_id": "SYN_OUTCOMES", "entity_type": "wafer", "entity_id": target},
        )
    ]
    refs.extend([
        {"source_id": "SYN_EXPOSURE_COVERAGE", "entity_type": "exposure_coverage", "entity_id": "SYN-COV-1"},
        {"source_id": "SYN_HISTORY_COVERAGE", "entity_type": "history_coverage", "entity_id": "SYN-HISTORY-COV-1"},
        {"source_id": "SYN_ROUTE_DEFINITIONS", "entity_type": "route_definition", "entity_id": "SYN-BASE-v1"},
        {"source_id": "SYN_ROUTE_COVERAGE", "entity_type": "route_coverage", "entity_id": "SYN-ROUTE-COV-1"},
        {"source_id": "SYN_MATERIAL", "entity_type": "material_catalog", "entity_id": "SYN-MATERIAL"},
    ])
    return refs


def _options_read_plan(source_id: str, relationship_id: str, time_window: dict[str, str]) -> dict[str, Any]:
    return {
        "source_ids": [source_id], "relationship_ids": [relationship_id],
        "time_window": time_window, "time_field": "timestamp",
    }


async def read_reference_options() -> dict[str, Any]:
    """Read selectable cohort and exact equipment options through the mock MCP peer."""
    scenario = configured_reference_scenario()
    if scenario in _ALIAS_MCP_SCENARIOS:
        return await _read_alias_reference_options()
    window, limits = scenario_window(scenario), scenario_limits(scenario)
    async with ConfiguredMCPAdapter(synthetic_adapter_config(scenario=scenario)) as adapter:
        discovery = await adapter.discover()
        semantic_response = await adapter.semantics(["SYN_OUTCOMES", "SYN_PROCESS"])
        relationships = await adapter.relationships([
            {"source_id": "SYN_OUTCOMES", "entity_type": "outcome_catalog", "entity_id": "SYN-OUTCOMES"},
            {"source_id": "SYN_PROCESS", "entity_type": "process_catalog", "entity_id": "SYN-PROCESS"},
        ], window)
        relation_by_id = {item["id"]: item for item in relationships["relationships"]}
        for relation_id, source_id in (("SYN_REL_WAFER_OUTCOME", "SYN_OUTCOMES"), ("SYN_REL_WAFER_STEP", "SYN_PROCESS")):
            relation = relation_by_id.get(relation_id)
            if not isinstance(relation, dict) or relation.get("approved") is not True or source_id not in relation.get("source_ids", []):
                raise MCPContractError(f"Synthetic selection relationship {relation_id} was not approved by the configured peer.")

        reads = []
        rows_by_role: dict[str, list[dict[str, Any]]] = {}
        for role, source_id, relationship_id in (
            ("outcomes", "SYN_OUTCOMES", "SYN_REL_WAFER_OUTCOME"),
            ("events", "SYN_PROCESS", "SYN_REL_WAFER_STEP"),
        ):
            operation_id = str(uuid.uuid4())
            result = await adapter.read_bounded(
                _options_read_plan(source_id, relationship_id, window), "SYNTHETIC_READ", limits,
                operation_id=operation_id,
            )
            audit = await adapter.audit(operation_id)
            if audit.get("query_hash") != result.get("query_hash"):
                raise MCPContractError("Selection option audit hash does not match its bounded read.")
            rows = result.get("typed_rows")
            if not isinstance(rows, list):
                raise MCPContractError("Selection options returned malformed typed rows.")
            rows_by_role[role] = rows
            reads.append({
                "dataset_role": role, "operation_id": operation_id, "audit_id": result["audit_id"],
                "query_hash": result["query_hash"], "row_count": len(rows),
                "source_ids": result["source_ids"], "relationship_ids": result["relationship_ids"],
                "source_versions": result["source_versions"],
            })
        outcomes = [row for row in rows_by_role["outcomes"] if row.get("label") in {"ABNORMAL", "NORMAL"}]
        event_rows = rows_by_role["events"]
        abnormal = sorted({row["wafer_id"] for row in outcomes if row.get("label") == "ABNORMAL"})
        cohort = sorted({row["wafer_id"] for row in outcomes})
        chambers = sorted({row["chamber_id"] for row in event_rows if isinstance(row.get("chamber_id"), str) and row["chamber_id"]})
        tools = sorted({row["tool_id"] for row in event_rows if isinstance(row.get("tool_id"), str) and row["tool_id"]})
        source_hashes = {
            item["source_id"]: item["source_hash"] for item in semantic_response["sources"]
        }
        return {
            "mode": "SYNTHETIC_PROTOCOL_COMPATIBILITY_ONLY",
            "protocol_version": adapter.protocol_version,
            "default_suspected_exposure": ({
                "chamber_id": "SYN-C1",
                "start": "2026-11-21T01:25:00+00:00",
                "end": "2026-11-21T01:35:00+00:00",
            } if scenario == "engineer-100" else {
                "chamber_id": chambers[0] if chambers else "",
                "start": "2026-11-21T03:00:00+00:00",
                "end": "2026-11-21T06:00:00+00:00",
            }),
            "cohort_wafer_ids": cohort,
            "abnormal_wafer_ids": abnormal,
            "chamber_ids": chambers,
            "tool_ids": tools,
            "sources": [{"id": key, "source_hash": value} for key, value in sorted(source_hashes.items())],
            "audited_reads": reads,
            "company_source_authorized": False,
            "mock_peer_permission_enforced": True,
            "discovered_auth_scopes": discovery["auth_scopes"],
        }


async def investigate_reference(
    payload: dict[str, Any], *, operation_id: str | None = None, delay_ms: int = 0,
    follow_up_proposal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    targets = payload["target_wafer_ids"]
    cohort = payload["cohort_wafer_ids"]
    suspected = payload["suspected_exposure"]
    configured = configured_reference_scenario()
    if configured in _ALIAS_MCP_SCENARIOS:
        scenario = f"{configured}-followup" if follow_up_proposal is not None else configured
        reviewed, runtime, onboarding = await _synthetic_alias_review(scenario)
        approved_plan = reviewed["approved_plan"]
        source_by_role = {
            plan["dataset_role"]: plan["source_ids"][0]
            for plan in approved_plan["read_plans"]
        }
        entity_refs = [
            {"source_id": source_by_role[role], "entity_type": "wafer", "entity_id": target}
            for target in targets for role in ("events", "outcomes")
        ]
        entity_refs.extend(
            {"source_id": source_id, "entity_type": "source", "entity_id": source_id}
            for source_id in approved_plan["source_ids"]
            if source_id not in {source_by_role["events"], source_by_role["outcomes"]}
        )
        async with ConfiguredMCPAdapter(runtime) as adapter:
            evidence = await investigate_with_mcp(
                adapter, approved_plan, reviewed["permission_scope"], reviewed["limits"],
                entity_refs, suspected_exposure=suspected, cohort=cohort,
                target_wafer_ids=targets, operation_id=operation_id,
                follow_up_proposal=follow_up_proposal,
            )
        evidence["provenance"]["mcp_integration"]["onboarding"] = onboarding
        evidence["provenance"]["mcp_integration"]["onboarding"]["source_role_mappings"] = [
            {**mapping, "field_mapping": dict(mapping["field_mapping"])}
            for mapping in onboarding["source_role_mappings"]
        ]
        return evidence
    scenario = (("engineer-100-followup" if configured == "engineer-100" else "engineer-followup")
                if follow_up_proposal is not None else configured)
    approved_plan = {**ENGINEER_PLAN, "time_window": scenario_window(configured)}
    async with ConfiguredMCPAdapter(synthetic_adapter_config(delay_ms=delay_ms, scenario=scenario)) as adapter:
        return await investigate_with_mcp(
            adapter,
            approved_plan,
            "SYNTHETIC_READ",
            scenario_limits(configured),
            _entity_refs(targets),
            suspected_exposure=suspected,
            cohort=cohort,
            target_wafer_ids=targets,
            operation_id=operation_id,
            follow_up_proposal=follow_up_proposal,
        )


def run_reference_options() -> dict[str, Any]:
    return asyncio.run(read_reference_options())


def run_reference_investigation(
    payload: dict[str, Any], cancellation, *, operation_id: str | None = None,
    delay_ms: int = 0, follow_up_proposal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drive an MCP coroutine from a request thread and turn local cancel into task cancel."""
    from fabintel.project import AnalysisCancelled

    async def run():
        task = asyncio.create_task(investigate_reference(
            payload, operation_id=operation_id, delay_ms=delay_ms,
            follow_up_proposal=follow_up_proposal,
        ))
        try:
            while True:
                if cancellation.is_set():
                    task.cancel()
                try:
                    return await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError as exc:
            raise AnalysisCancelled("MCP-backed investigation cancelled; no partial evidence was returned.") from exc

    try:
        return asyncio.run(run())
    except asyncio.CancelledError as exc:
        raise AnalysisCancelled("MCP-backed investigation cancelled; no partial evidence was returned.") from exc
