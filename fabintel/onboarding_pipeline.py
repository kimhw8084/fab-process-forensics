"""Review-gated onboarding from official MCP descriptors to a P2 read plan.

Discovery is metadata-only. A review record is a configuration decision, not an
authentication credential; server-side permission checks remain authoritative.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any

from fabintel.mcp_adapter import ConfiguredMCPAdapter, MCPContractError, MCPUnsupported
from fabintel.onboarding import propose_mappings


_ROLES = (
    "events", "outcomes", "coverage", "history_coverage", "route_definitions",
    "route_coverage", "material_relationships",
)
_OPERATIONS = ("discover", "semantics", "relationships", "read_bounded", "cancel", "audit")
_SEMANTICS_BATCH_SIZE = 64
_RELATIONSHIP_RELEVANT_RECORD_KINDS = {
    "PROCESS_STEP_INSTANCE", "WAFER_OUTCOME", "EXPOSURE_COVERAGE",
    "PROCESS_HISTORY_COVERAGE", "ROUTE_DEFINITION", "ROUTE_COVERAGE",
    "MATERIAL_RELATIONSHIP",
}


def _chunks(values: list[Any], size: int):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def _digest(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timezone-aware ISO timestamps are required.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone-aware ISO timestamps are required.")
    return parsed.astimezone(timezone.utc)


async def discover_descriptor_capture(
    adapter: ConfiguredMCPAdapter, tool_descriptors: list[dict[str, Any]],
    time_window: dict[str, str], performance: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Collect source definitions and relationships via the frozen read-only ops."""
    started = time.perf_counter()
    discovered = await adapter.discover()
    if performance is not None:
        performance["mcp_discover_ms"] = (time.perf_counter() - started) * 1000
    catalog = discovered.get("source_catalog")
    if not isinstance(catalog, list) or not catalog:
        raise MCPContractError("MCP discovery did not expose a source ID catalog; P2 will not guess source IDs.")
    source_ids = [item.get("source_id") for item in catalog if isinstance(item, dict)]
    if (len(source_ids) != len(catalog) or any(not isinstance(item, str) or not item for item in source_ids)
            or len(source_ids) != len(set(source_ids))):
        raise MCPContractError("MCP source catalog contains invalid or duplicate IDs.")
    semantic_sources = []
    semantics_batches = 0
    started = time.perf_counter()
    for source_batch in _chunks(source_ids, _SEMANTICS_BATCH_SIZE):
        response = await adapter.semantics(source_batch)
        semantic_sources.extend(response["sources"])
        semantics_batches += 1
    if performance is not None:
        performance["source_semantics_ms"] = (time.perf_counter() - started) * 1000
    # Relationship metadata is needed only for descriptors that can match a
    # frozen P2 source role. This is a request-volume optimization, not a trust
    # decision: all source semantics are retained and every resulting mapping
    # still requires explicit review plus server-side authorization.
    relationship_source_ids = [item["source_id"] for item in semantic_sources
                               if item.get("record_kind") in _RELATIONSHIP_RELEVANT_RECORD_KINDS]
    refs = [{"source_id": source_id, "entity_type": "source", "entity_id": source_id}
            for source_id in relationship_source_ids]
    started = time.perf_counter()
    relations = await adapter.relationships(refs, time_window)
    if performance is not None:
        performance["source_relationships_ms"] = (time.perf_counter() - started) * 1000
    return {
        "capture_mode": "LIVE_MCP_METADATA_ONLY_UNVERIFIED_ORIGIN",
        "protocol_version": adapter.protocol_version,
        "tools": tool_descriptors,
        "tool_versions": discovered["tool_versions"],
        "sources": semantic_sources,
        "relationships": relations["relationships"],
        "metadata_source_count": len(source_ids),
        "metadata_semantics_batch_count": semantics_batches,
        "metadata_semantics_batch_size": _SEMANTICS_BATCH_SIZE,
        "metadata_relationship_source_count": len(relationship_source_ids),
        "limits": discovered["limits"],
        "auth_scopes": discovered["auth_scopes"],
    }


async def propose_from_live_mcp_metadata(
    transport: dict[str, Any], *, time_window: dict[str, str],
    request_timeout_seconds: float = 10, max_response_bytes: int = 1048576,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Discover tools then inspect only declared semantics/relationships.

    No `read_bounded` call is made. The returned source proposals are still
    review-required and do not establish origin, permission, or approval.
    """
    performance: dict[str, float] = {}
    started = time.perf_counter()
    descriptor_result = await ConfiguredMCPAdapter.inspect_tool_descriptors(
        transport, request_timeout_seconds=request_timeout_seconds,
        max_response_bytes=max_response_bytes, environment=environment,
    )
    performance["tool_descriptor_inspection_ms"] = (time.perf_counter() - started) * 1000
    tools = descriptor_result["tools"]
    started = time.perf_counter()
    bootstrap = propose_mappings({
        "capture_mode": "UNVERIFIED_MCP_TOOL_METADATA", "tools": tools,
        "sources": [], "relationships": [],
        "limits": {"max_rows": 1, "max_bytes": 1024, "max_seconds": 1},
    })
    tool_map = {}
    for operation in _OPERATIONS:
        candidate = bootstrap["operation_proposals"][operation]
        if candidate["candidate_state"] != "UNIQUE_REVIEW_REQUIRED":
            raise MCPUnsupported(
                f"MCP onboarding requires a unique reviewed-compatible tool for {operation}; "
                "no source metadata or records were requested."
            )
        tool_map[operation] = candidate["candidate_tool_names"][0]
    if len(set(tool_map.values())) != len(_OPERATIONS):
        raise MCPUnsupported("One discovered tool ambiguously matches multiple logical operations.")
    config = {
        "schema_version": "p2-mcp-client-config/v1", "transport": transport,
        "tools": tool_map, "request_timeout_seconds": request_timeout_seconds,
        "max_response_bytes": max_response_bytes,
    }
    performance["tool_mapping_ms"] = (time.perf_counter() - started) * 1000
    async with ConfiguredMCPAdapter(config, environment=environment) as adapter:
        capture = await discover_descriptor_capture(adapter, tools, time_window, performance)
    performance["metadata_capture_total_ms"] = sum(
        performance[key] for key in ("mcp_discover_ms", "source_semantics_ms", "source_relationships_ms")
    )
    started = time.perf_counter()
    proposal = propose_mappings(capture)
    performance["source_mapping_ms"] = (time.perf_counter() - started) * 1000
    return {
        "schema_version": "p2-live-onboarding-proposal/v1",
        "mcp_protocol_version": descriptor_result["protocol_version"],
        "metadata_only": True, "bounded_row_reads_executed": False,
        "capture": capture, "descriptor_capture_sha256": _digest(capture),
        "proposal": proposal, "proposal_sha256": _digest(proposal),
        "configured_tool_map_is_review_required": True,
        "server_authorization_established": False, "company_qualified": False,
        "performance_metrics": {
            **performance,
            "measurement_scope": "SDK tool discovery, MCP source discovery, bounded semantics batches, relationships, and deterministic mapping; excludes review, record reads, analysis, and browser rendering.",
        },
    }


def validate_review_and_materialize(
    proposal: dict[str, Any], *, decision: str, reviewer_id: str,
    selected_tools: dict[str, str],
    selected_sources: dict[str, dict[str, Any]],
    time_window: dict[str, str], limits: dict[str, Any],
    permission_scope: str, capture_limits: dict[str, Any],
    descriptor_capture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an explicit human review record and materialize bounded config.

    `selected_tools` and `selected_sources` must be populated by a reviewer. No
    selection is inferred here. The resulting record is not company approval.
    """
    if not isinstance(proposal, dict) or proposal.get("schema_version") != "p2-onboarding-proposal/v1":
        raise ValueError("A versioned onboarding proposal is required.")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("reviewer_id is required for the explicit review record.")
    if decision != "APPROVE":
        raise ValueError("The reviewer must explicitly set decision=APPROVE to materialize a read plan.")
    if proposal.get("reads_executed") is not False:
        raise ValueError("Descriptor proposals must not contain executed reads.")
    if not isinstance(time_window, dict) or set(time_window) != {"start", "end"}:
        raise ValueError("A bounded start and end time are required.")
    window_start, window_end = _instant(time_window.get("start")), _instant(time_window.get("end"))
    if window_end <= window_start:
        raise ValueError("The reviewed time window must have positive duration.")
    tool_proposals = proposal.get("operation_proposals", {})
    if not isinstance(selected_tools, dict) or set(selected_tools) != set(tool_proposals):
        raise ValueError("Every logical operation requires one explicit tool selection.")
    for logical, name in selected_tools.items():
        candidates = tool_proposals[logical].get("candidate_tool_names", [])
        if name not in candidates:
            raise ValueError(f"Selected tool for {logical} is not a discovered read-only candidate.")

    role_proposals = proposal.get("source_role_proposals", {})
    if not isinstance(selected_sources, dict) or set(selected_sources) != set(_ROLES):
        raise ValueError("Every P2 source role requires an explicit source and relationship decision.")
    read_plans = []
    source_ids, relationship_ids = [], []
    for role in _ROLES:
        choice = selected_sources[role]
        if not isinstance(choice, dict):
            raise ValueError(f"Source selection for {role} must be an object.")
        source_id, relationship_id = choice.get("source_id"), choice.get("relationship_id")
        candidates = role_proposals.get(role, {}).get("candidates", [])
        candidate = next((item for item in candidates
                          if item.get("source_id") == source_id
                          and item.get("relationship_id") == relationship_id
                          and item.get("candidate_state") in {
                              "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED",
                              "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED",
                          }), None)
        if candidate is None:
            raise ValueError(f"Selected source/relationship pair for {role} is not a structural candidate.")
        missing = candidate.get("missing_optional_fields", [])
        if sorted(choice.get("acknowledge_missing_optional", [])) != sorted(missing):
            raise ValueError(f"The reviewer must explicitly acknowledge the optional unknowns for {role}: {missing}.")
        effectivity = candidate.get("descriptor_effectivity_intersection", {})
        if not (isinstance(effectivity.get("start"), str) and isinstance(effectivity.get("end"), str)
                and _instant(effectivity["start"]) <= window_start
                and _instant(effectivity["end"]) >= window_end):
            raise ValueError(f"Selected {role} source/relationship does not cover the reviewed time window.")
        if source_id in source_ids or relationship_id in relationship_ids:
            raise ValueError("Each physical source and relationship must have one role in this plan.")
        source_ids.append(source_id)
        relationship_ids.append(relationship_id)
        read_plans.append({
            "dataset_role": role, "source_ids": [source_id],
            "relationship_ids": [relationship_id], "time_field": candidate["time_field"],
            "time_window": time_window, "filters": {},
            "field_mapping": candidate["field_mapping"],
            "nullable_fields": candidate.get("nullable_fields", []),
            "relationship_type": candidate.get("relationship_type"),
            "missing_optional_fields": missing,
            "authorization_state": "REVIEWED_BUT_SERVER_AUTHORIZATION_REQUIRED",
        })

    for key in ("max_rows", "max_bytes", "max_seconds"):
        value, upper = limits.get(key), capture_limits.get(key)
        if (not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0
                or not isinstance(upper, (int, float)) or value > upper
                or (key != "max_seconds" and not float(value).is_integer())):
            raise ValueError(f"Reviewed {key} must be positive and no greater than the discovered server bound.")
    if not isinstance(permission_scope, str) or not permission_scope:
        raise ValueError("An explicit permission scope must be selected for the read plan.")
    source_descriptors = {
        item.get("source_id"): item for item in (descriptor_capture or {}).get("sources", [])
        if isinstance(item, dict)
    }
    relation_descriptors = {
        item.get("id"): item for item in (descriptor_capture or {}).get("relationships", [])
        if isinstance(item, dict)
    }
    for plan in read_plans:
        source_id = plan["source_ids"][0]
        relation_id = plan["relationship_ids"][0]
        source = source_descriptors.get(source_id)
        relation = relation_descriptors.get(relation_id)
        if not isinstance(source, dict) or not isinstance(relation, dict):
            raise ValueError("The selected source and relationship must be present in the reviewed descriptor capture.")
        plan["expected_source_hash"] = source.get("source_hash")
        plan["expected_semantic_version"] = source.get("semantic_version")
        plan["expected_relationship_sha256"] = _digest(relation)
    review_record = {
        "schema_version": "p2-onboarding-review/v1",
        "decision": "APPROVE",
        "reviewer_id": reviewer_id,
        "proposal_sha256": _digest(proposal),
        "selections_sha256": _digest({"decision": decision, "reviewer_id": reviewer_id,
                                       "selected_tools": selected_tools, "selected_sources": selected_sources,
                                       "time_window": time_window, "limits": limits,
                                       "permission_scope": permission_scope,
                                       "descriptor_capture_sha256": _digest(descriptor_capture or {})}),
        "authority": "NOT_AUTHENTICATED_BY_P2; SERVER PERMISSIONS REMAIN AUTHORITATIVE",
    }
    return {
        "schema_version": "p2-approved-investigation-config/v1",
        "review": review_record,
        "descriptor_capture_sha256": _digest(descriptor_capture or {}),
        "mcp_tools": dict(selected_tools),
        "reviewed_decisions": {"decision": decision, "reviewer_id": reviewer_id,
                               "selected_tools": dict(selected_tools), "selected_sources": selected_sources,
                               "time_window": dict(time_window), "limits": dict(limits),
                               "permission_scope": permission_scope,
                               "descriptor_capture_sha256": _digest(descriptor_capture or {})},
        "approved_plan": {
            "source_ids": source_ids, "relationship_ids": relationship_ids,
            "time_window": dict(time_window), "read_plans": read_plans,
        },
        "permission_scope": permission_scope,
        "limits": dict(limits),
        "server_authorization_established": False,
        "company_qualified": False,
    }


def verify_materialized_config(config: dict[str, Any], proposal: dict[str, Any]) -> None:
    """Fail closed if review content was changed after materialization."""
    review = config.get("review") if isinstance(config, dict) else None
    if (not isinstance(review, dict) or review.get("schema_version") != "p2-onboarding-review/v1"
            or review.get("proposal_sha256") != _digest(proposal)
            or review.get("authority") != "NOT_AUTHENTICATED_BY_P2; SERVER PERMISSIONS REMAIN AUTHORITATIVE"):
        raise ValueError("Review record is missing, stale, or unrelated to the current proposal.")
    decisions = config.get("reviewed_decisions")
    if not isinstance(decisions, dict) or review.get("selections_sha256") != _digest(decisions):
        raise ValueError("Reviewed selections changed after the decision was recorded.")
    if (decisions.get("decision") not in {"APPROVE", "APPROVE_EXACT_PROPOSAL"}
            or decisions.get("descriptor_capture_sha256") != config.get("descriptor_capture_sha256")
            or review.get("descriptor_capture_sha256") != config.get("descriptor_capture_sha256")):
        raise ValueError("Review approval or descriptor version binding changed.")
    bound_payload = {
        "approved_plan": config.get("approved_plan"), "mcp_tools": config.get("mcp_tools"),
        "permission_scope": config.get("permission_scope"), "limits": config.get("limits"),
        "descriptor_capture_sha256": config.get("descriptor_capture_sha256"),
        "reviewed_decisions": decisions,
    }
    if review.get("materialized_sha256") != _digest(bound_payload):
        raise ValueError("Materialized source selections or bounded plan changed after review.")
    approved = config.get("approved_plan")
    if not isinstance(approved, dict) or not isinstance(approved.get("read_plans"), list):
        raise ValueError("Materialized plan is malformed.")
    for plan in approved["read_plans"]:
        if plan.get("authorization_state") != "REVIEWED_BUT_SERVER_AUTHORIZATION_REQUIRED":
            raise ValueError("Only reviewed, bounded plans can be presented for execution.")
        if (not isinstance(plan.get("expected_source_hash"), str)
                or not isinstance(plan.get("expected_semantic_version"), str)
                or not isinstance(plan.get("expected_relationship_sha256"), str)):
            raise ValueError("The reviewed plan must pin its source and relationship descriptor versions.")


def materialize_live_review(report: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    """Validate explicit review choices against a live metadata-only proposal."""
    if (not isinstance(report, dict) or report.get("schema_version") != "p2-live-onboarding-proposal/v1"
            or report.get("metadata_only") is not True or report.get("bounded_row_reads_executed") is not False):
        raise ValueError("A metadata-only live onboarding proposal is required.")
    if not isinstance(decisions, dict):
        raise ValueError("Reviewer decisions must be an object.")
    capture = report.get("capture")
    proposal = report.get("proposal")
    if not isinstance(capture, dict) or not isinstance(proposal, dict):
        raise ValueError("Live proposal is missing its descriptor capture or proposal.")
    decision = decisions.get("decision")

    def verify_review_snapshot():
        capture_digest = _digest(capture)
        if report.get("descriptor_capture_sha256") != capture_digest:
            raise ValueError("Descriptor capture changed after the mapping proposal was created.")
        if decisions.get("descriptor_capture_sha256") != capture_digest:
            raise ValueError("Reviewer decision must cite the exact descriptor_capture_sha256.")
        if report.get("proposal_sha256") != _digest(proposal):
            raise ValueError("Mapping proposal changed after its proposal_sha256 was created.")
        if propose_mappings(capture) != proposal:
            raise ValueError("Mapping proposal no longer matches its descriptor capture.")

    if decision == "APPROVE_EXACT_PROPOSAL":
        verify_review_snapshot()
        expected = report.get("proposal_sha256") or _digest(proposal)
        if decisions.get("proposal_sha256") != expected or expected != _digest(proposal):
            raise ValueError("Exact-proposal approval must cite the current proposal SHA-256.")
        selected_tools = {}
        for operation in _OPERATIONS:
            item = proposal.get("operation_proposals", {}).get(operation, {})
            candidates = item.get("candidate_tool_names", [])
            if item.get("candidate_state") != "UNIQUE_REVIEW_REQUIRED" or len(candidates) != 1:
                raise ValueError(f"Exact-proposal approval requires one compatible tool for {operation}.")
            selected_tools[operation] = candidates[0]
        selected_sources = {}
        for role in _ROLES:
            item = proposal.get("source_role_proposals", {}).get(role, {})
            compatible = [candidate for candidate in item.get("candidates", [])
                          if candidate.get("candidate_state") in {
                              "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED",
                              "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED",
                          }]
            if item.get("candidate_state") != "UNIQUE_REVIEW_REQUIRED" or len(compatible) != 1:
                raise ValueError(f"Exact-proposal approval requires one reviewed-compatible source for {role}.")
            candidate = compatible[0]
            if candidate.get("candidate_state") != "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED":
                raise ValueError(
                    f"Exact-proposal approval cannot acknowledge partial source role {role}; "
                    "select it explicitly and acknowledge each missing optional field."
                )
            selected_sources[role] = {
                "source_id": candidate["source_id"],
                "relationship_id": candidate["relationship_id"],
                "acknowledge_missing_optional": candidate.get("missing_optional_fields", []),
            }
        validation_decision = "APPROVE"
    elif decision == "APPROVE":
        verify_review_snapshot()
        selected_tools = decisions.get("selected_tools")
        selected_sources = decisions.get("selected_sources")
        validation_decision = "APPROVE"
    else:
        raise ValueError("Reviewer must explicitly set decision=APPROVE or digest-bound APPROVE_EXACT_PROPOSAL.")
    result = validate_review_and_materialize(
        proposal, decision=validation_decision, reviewer_id=decisions.get("reviewer_id"),
        selected_tools=selected_tools,
        selected_sources=selected_sources,
        time_window=decisions.get("time_window"), limits=decisions.get("limits"),
        permission_scope=decisions.get("permission_scope"),
        capture_limits=capture.get("limits", {}), descriptor_capture=capture,
    )
    result["proposal_sha256"] = _digest(proposal)
    result["review"]["descriptor_capture_sha256"] = _digest(capture)
    result["reviewed_decisions"] = {
        "decision": decision,
        "reviewer_id": decisions.get("reviewer_id"),
        "selected_tools": selected_tools,
        "selected_sources": selected_sources,
        **({"proposal_sha256": decisions.get("proposal_sha256")}
           if decision == "APPROVE_EXACT_PROPOSAL" else {}),
        "time_window": decisions.get("time_window"), "limits": decisions.get("limits"),
        "permission_scope": decisions.get("permission_scope"),
        "descriptor_capture_sha256": _digest(capture),
    }
    result["review"]["decision"] = decision
    result["review"]["selections_sha256"] = _digest(result["reviewed_decisions"])
    result["mcp_transport"] = "SUPPLY_SEPARATELY_FROM_AUTHORIZED_LOCAL_CONFIGURATION"
    result["review"]["materialized_sha256"] = _digest({
        "approved_plan": result["approved_plan"], "mcp_tools": result["mcp_tools"],
        "permission_scope": result["permission_scope"], "limits": result["limits"],
        "descriptor_capture_sha256": result["descriptor_capture_sha256"],
        "reviewed_decisions": result["reviewed_decisions"],
    })
    return result
