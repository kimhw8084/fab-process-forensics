"""Read-only MCP-to-evidence workflow using the frozen logical operations."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
import uuid

from fabintel.mcp_adapter import ConfiguredMCPAdapter, MCPContractError
from fabintel.project import analyze


_ROLE_RECORD_KIND = {
    "events": "PROCESS_STEP_INSTANCE",
    "outcomes": "WAFER_OUTCOME",
    "coverage": "EXPOSURE_COVERAGE",
    "history_coverage": "PROCESS_HISTORY_COVERAGE",
    "route_definitions": "ROUTE_DEFINITION",
    "route_coverage": "ROUTE_COVERAGE",
    "material_relationships": "MATERIAL_RELATIONSHIP",
}
_FIELD_TARGET_ALIASES = {
    "event_time": "timestamp", "outcome_time": "timestamp",
    "outcome_label": "label", "record_time": "timestamp",
}


def _build_read_plans(approved_plan: dict[str, Any]) -> list[dict[str, Any]]:
    sources = approved_plan.get("source_ids")
    relationships = approved_plan.get("relationship_ids")
    window = approved_plan.get("time_window")
    if (not isinstance(sources, list) or not sources
            or any(not isinstance(item, str) or not item for item in sources)
            or len(sources) != len(set(sources))
            or not isinstance(relationships, list) or not relationships
            or any(not isinstance(item, str) or not item for item in relationships)
            or len(relationships) != len(set(relationships))
            or not isinstance(window, dict)):
        raise MCPContractError("approved_plan must declare unique source IDs, relationship IDs, and a bounded time window.")
    raw_plans = approved_plan.get("read_plans")
    if raw_plans is None:
        raw_plans = [{
            "source_ids": sources,
            "relationship_ids": relationships,
            "time_window": window,
            "time_field": approved_plan.get("time_field"),
            "dataset_role": "events",
        }]
    if not isinstance(raw_plans, list) or not raw_plans:
        raise MCPContractError("approved_plan read_plans must be a non-empty list.")
    plans = []
    used_sources: set[str] = set()
    used_relationships: set[str] = set()
    for index, raw in enumerate(raw_plans):
        if not isinstance(raw, dict):
            raise MCPContractError(f"approved_plan read_plans[{index}] must be an object.")
        plan_sources = raw.get("source_ids")
        plan_relationships = raw.get("relationship_ids")
        role = raw.get("dataset_role")
        time_field = raw.get("time_field")
        if (not isinstance(plan_sources, list) or not plan_sources
                or any(not isinstance(item, str) or not item for item in plan_sources)
                or len(plan_sources) != len(set(plan_sources))
                or not isinstance(plan_relationships, list) or not plan_relationships
                or any(not isinstance(item, str) or not item for item in plan_relationships)
                or len(plan_relationships) != len(set(plan_relationships))
                or role not in _ROLE_RECORD_KIND or not isinstance(time_field, str) or not time_field
                or raw.get("time_window", window) != window):
            raise MCPContractError(f"approved_plan read_plans[{index}] must declare one role, source/relationship IDs, time field, and the investigation window.")
        if used_sources.intersection(plan_sources) or used_relationships.intersection(plan_relationships):
            raise MCPContractError("Each source and relationship must belong to exactly one bounded dataset read.")
        used_sources.update(plan_sources)
        used_relationships.update(plan_relationships)
        read_plan = {
            "source_ids": list(plan_sources),
            "relationship_ids": list(plan_relationships),
            "time_window": window,
            "time_field": time_field,
            "dataset_role": role,
        }
        if "filters" in raw:
            read_plan["filters"] = raw["filters"]
        for field in ("expected_source_hash", "expected_semantic_version", "expected_relationship_sha256",
                      "field_mapping", "missing_optional_fields", "authorization_state", "relationship_type"):
            if field in raw:
                read_plan[field] = raw[field]
        plans.append(read_plan)
    if used_sources != set(sources) or used_relationships != set(relationships):
        raise MCPContractError("read_plans must cover exactly the sources and relationships declared by approved_plan.")
    return plans


def _canonical_hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _normalize_mapped_row(plan: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    mapping = plan.get("field_mapping")
    if mapping is None:
        return row
    if not isinstance(mapping, dict):
        raise MCPContractError("Reviewed field mapping is malformed.")
    role = plan["dataset_role"]
    nullable_fields = set(plan.get("nullable_fields", []))
    canonical = dict(row)
    for logical, physical in mapping.items():
        if physical is None:
            continue
        if not isinstance(physical, str):
            raise MCPContractError(f"Reviewed {role} mapping contains an invalid source field for {logical}.")
        if physical not in row and logical in nullable_fields:
            continue
        if physical not in row:
            raise MCPContractError(f"Reviewed {role} mapping requires source field {physical}, which is absent.")
        target = _FIELD_TARGET_ALIASES.get(logical, logical)
        if target in canonical and canonical[target] != row[physical]:
            raise MCPContractError(f"Source value conflicts with reviewed canonical field {target}.")
        canonical[target] = row[physical]
    if role == "material_relationships":
        from_id, from_type = mapping.get("from_entity_id"), mapping.get("from_entity_type")
        to_id, to_type = mapping.get("to_entity_id"), mapping.get("to_entity_type")
        canonical["from_entity"] = {"type": row[from_type], "id": row[from_id]}
        canonical["to_entity"] = {"type": row[to_type], "id": row[to_id]}
        canonical["relationship_type"] = plan.get("relationship_type") or row.get("relationship_type")
        canonical["observed_at"] = row[mapping["observed_at"]]
        raw_values = row.get(mapping.get("key_values"), row)
        if not isinstance(raw_values, dict):
            raise MCPContractError("Reviewed material relationship key-value payload is malformed.")
        key_values = dict(raw_values)
        for logical, physical in mapping.items():
            if physical is None:
                continue
            if physical not in row and logical in nullable_fields:
                continue
            if physical not in row:
                raise MCPContractError(f"Reviewed material relationship requires source field {physical}, which is absent.")
            if physical in row:
                target = _FIELD_TARGET_ALIASES.get(logical, logical)
                if target in key_values and key_values[target] != row[physical]:
                    raise MCPContractError(f"Material relationship key value conflicts with reviewed field {target}.")
                key_values[target] = row[physical]
        canonical["key_values"] = key_values
    return canonical


def _normalize_relationship_field_names(relation: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Bind engine-canonical key names to exact, reviewed physical descriptor keys."""
    mapping = plan.get("field_mapping")
    if mapping is None:
        return relation
    if not isinstance(mapping, dict):
        raise MCPContractError("Reviewed relationship field mapping is malformed.")
    physical_to_canonical = {}
    for logical, physical in mapping.items():
        if physical is None:
            continue
        target = _FIELD_TARGET_ALIASES.get(logical, logical)
        prior = physical_to_canonical.get(physical)
        if prior is not None and prior != target:
            raise MCPContractError("Reviewed source fields map one physical relationship key to conflicting canonical fields.")
        physical_to_canonical[physical] = target
    declared_keys = relation.get("keys")
    if not isinstance(declared_keys, list):
        raise MCPContractError("Reviewed source relationship keys are malformed.")
    canonical = dict(relation)
    canonical["source_declared_keys"] = list(declared_keys)
    canonical["field_aliases"] = {
        physical: target for physical, target in sorted(physical_to_canonical.items())
        if physical in declared_keys and physical != target
    }
    canonical["keys"] = sorted({physical_to_canonical.get(key, key) for key in declared_keys})
    return canonical


def _membership_conflict_candidate(evidence: dict[str, Any]) -> dict[str, Any] | None:
    for investigation in evidence.get("counterevidence", []):
        verification = investigation.get("next_authorized_verification", {})
        for candidate in verification.get("candidates", []):
            if candidate.get("category") == "LOT_MEMBERSHIP_CONFLICT":
                return candidate
    return None


async def investigate_with_mcp(
    adapter: ConfiguredMCPAdapter,
    approved_plan: dict[str, Any],
    permission_context: str,
    limits: dict[str, Any],
    entity_refs: list[dict[str, Any]],
    *,
    suspected_exposure: dict[str, Any] | None = None,
    cohort: list[str] | None = None,
    target_wafer_ids: list[str] | None = None,
    operation_id: str | None = None,
    follow_up_proposal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute approved bounded reads, analyze their verified record kinds, and attach audits.

    Dataset roles are accepted only when they match the record kind returned by
    verified source semantics. The legacy one-source call remains event-only.
    Remote fixture approval and permission labels never authenticate company use.
    """
    if not isinstance(approved_plan, dict):
        raise MCPContractError("approved_plan must be a structured object.")
    read_plans = _build_read_plans(approved_plan)
    sources_requested = approved_plan["source_ids"]
    relationship_ids_requested = approved_plan["relationship_ids"]
    time_window = approved_plan["time_window"]

    discovered = await adapter.discover()
    semantic_response = await adapter.semantics(sources_requested)
    relationship_response = await adapter.relationships(entity_refs, time_window)
    relation_by_id = {
        item["id"]: item for item in relationship_response.get("relationships", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for relationship_id in relationship_ids_requested:
        relation = relation_by_id.get(relationship_id)
        if relation is None or relation.get("approved") is not True:
            raise MCPContractError(f"Read plan relationship {relationship_id} is not source-approved by the configured server.")

    semantic_by_id = {
        item["source_id"]: item for item in semantic_response.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    for plan in read_plans:
        expected_kind = _ROLE_RECORD_KIND[plan["dataset_role"]]
        for source_id in plan["source_ids"]:
            semantic = semantic_by_id.get(source_id)
            if semantic is None:
                raise MCPContractError(f"Read plan source {source_id} has no verified source semantics.")
            actual_kind = semantic.get("record_kind")
            if actual_kind is None and plan["dataset_role"] == "events":
                # Backward-compatible single-source clients predate explicit record kinds.
                continue
            if actual_kind != expected_kind:
                raise MCPContractError(f"Read plan role {plan['dataset_role']} conflicts with source {source_id} record kind.")
            if (plan.get("expected_source_hash") is not None
                    and semantic.get("source_hash") != plan["expected_source_hash"]):
                raise MCPContractError(f"Source {source_id} changed after onboarding review; remapping is required.")
            if (plan.get("expected_semantic_version") is not None
                    and semantic.get("semantic_version") != plan["expected_semantic_version"]):
                raise MCPContractError(f"Source {source_id} semantic version changed after review; remapping is required.")
        if plan.get("expected_relationship_sha256") is not None:
            relation_id = plan["relationship_ids"][0]
            if _canonical_hash(relation_by_id[relation_id]) != plan["expected_relationship_sha256"]:
                raise MCPContractError(f"Relationship {relation_id} changed after onboarding review; remapping is required.")

    base_id = uuid.UUID(operation_id) if operation_id else uuid.uuid4()
    events: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    history_coverage_rows: list[dict[str, Any]] = []
    route_definitions: list[dict[str, Any]] = []
    route_coverage_rows: list[dict[str, Any]] = []
    material_relationship_rows: list[dict[str, Any]] = []
    source_ids_used: set[str] = set()
    relation_ids_used: set[str] = set()
    source_versions: dict[str, str] = {}
    read_records: list[dict[str, Any]] = []
    truncated = False

    for index, plan in enumerate(read_plans):
        read_operation_id = str(base_id if len(read_plans) == 1 else uuid.uuid5(base_id, f"p2-mcp-read-{index}"))
        try:
            bounded_read = await adapter.read_bounded(
                plan, permission_context, limits, operation_id=read_operation_id,
            )
        except asyncio.CancelledError:
            try:
                await asyncio.shield(adapter.cancel(read_operation_id))
            except Exception:
                pass
            raise
        audit_record = await adapter.audit(read_operation_id)
        if audit_record.get("query_hash") != bounded_read.get("query_hash"):
            raise MCPContractError("The MCP audit query hash does not match the bounded result.")
        rows = bounded_read.get("typed_rows")
        if not isinstance(rows, list):
            raise MCPContractError("The bounded MCP read returned malformed typed rows.")
        rows = [_normalize_mapped_row(plan, row) for row in rows]
        if plan["dataset_role"] == "events":
            events.extend({**row, "approved_relationship": True} for row in rows)
        elif plan["dataset_role"] == "outcomes":
            outcomes.extend({**row, "approved_relationship": True} for row in rows)
        elif plan["dataset_role"] == "coverage":
            coverage_rows.extend(rows)
        elif plan["dataset_role"] == "history_coverage":
            history_coverage_rows.extend(rows)
        elif plan["dataset_role"] == "route_definitions":
            route_definitions.extend(rows)
        elif plan["dataset_role"] == "route_coverage":
            route_coverage_rows.extend(rows)
        elif plan["dataset_role"] == "material_relationships":
            material_relationship_rows.extend(rows)
        source_ids_used.update(bounded_read.get("source_ids", []))
        relation_ids_used.update(bounded_read.get("relationship_ids", []))
        source_versions.update(bounded_read.get("source_versions", {}))
        truncated = truncated or bounded_read["truncated"]
        read_records.append({
            "dataset_role": plan["dataset_role"],
            "operation_id": bounded_read["operation_id"],
            "audit_id": bounded_read["audit_id"],
            "query_hash": bounded_read["query_hash"],
            "audit_query_hash": audit_record["query_hash"],
            "query_window": bounded_read["query_window"],
            "source_ids": bounded_read["source_ids"],
            "relationship_ids": bounded_read["relationship_ids"],
            "source_versions": bounded_read["source_versions"],
            "row_count": len(rows),
            "truncated": bounded_read["truncated"],
        })

    if not events:
        raise MCPContractError("The bounded MCP reads returned no process rows; no journey evidence can be analyzed.")
    if target_wafer_ids is not None:
        if (not isinstance(target_wafer_ids, list) or not target_wafer_ids
                or any(not isinstance(value, str) or not value for value in target_wafer_ids)
                or len(target_wafer_ids) != len(set(target_wafer_ids))):
            raise MCPContractError("target_wafer_ids must be a unique non-empty list of source-observed wafer identities.")
        abnormal_wafer_ids = {
            row.get("wafer_id") for row in outcomes if row.get("label") == "ABNORMAL"
        }
        if not set(target_wafer_ids).issubset(abnormal_wafer_ids):
            raise MCPContractError("Investigation targets must match source-observed ABNORMAL outcome rows.")
    if len(coverage_rows) > 1:
        raise MCPContractError("The bounded MCP reads returned multiple exposure coverage records for one investigation.")
    if len(history_coverage_rows) > 1:
        raise MCPContractError("The bounded MCP reads returned multiple process-history coverage records for one investigation.")
    if len(route_coverage_rows) > 1:
        raise MCPContractError("The bounded MCP reads returned multiple route coverage records for one investigation.")
    if not source_ids_used.issubset(semantic_by_id) or not relation_ids_used.issubset(relation_by_id):
        raise MCPContractError("Bounded rows do not resolve to the exact semantics and relationships retrieved in this session.")

    sources = []
    for source_id in sorted(source_ids_used):
        semantic = semantic_by_id[source_id]
        sources.append({
            "id": source_id,
            "approved_semantic_version": semantic["semantic_version"],
            "grain": semantic["grain"],
            "source_hash": semantic["source_hash"],
            "permissions_ref": f"MCP_PERMISSION_SCOPE_UNVERIFIED:{permission_context}",
        })
    plan_by_relationship = {
        relationship_id: plan
        for plan in read_plans for relationship_id in plan["relationship_ids"]
    }
    relationships = []
    reviewed_field_mappings = []
    for relationship_id in sorted(relation_ids_used):
        original = relation_by_id[relationship_id]
        plan = plan_by_relationship.get(relationship_id)
        if plan is None:
            raise MCPContractError(f"Read relationship {relationship_id} has no approved role mapping.")
        normalized = _normalize_relationship_field_names(original, plan)
        relation = {
            key: normalized[key]
            for key in (
                "id", "approved", "source_ids", "keys", "cardinality", "grain",
                "effective_start", "effective_end", "entity_identity", "relationship_type",
                "source_declared_keys", "field_aliases",
            )
            if key in normalized
        }
        relation["descriptor_sha256"] = _canonical_hash(original)
        relationships.append(relation)
        reviewed_field_mappings.append({
            "dataset_role": plan["dataset_role"],
            "source_ids": list(plan["source_ids"]),
            "relationship_id": relationship_id,
            "time_field": plan["time_field"],
            "field_mapping": dict(plan.get("field_mapping") or {}),
            "nullable_fields": list(plan.get("nullable_fields", [])),
            "source_declared_relationship_keys": list(original.get("keys", [])),
            "analysis_relationship_keys": list(normalized.get("keys", [])),
            "relationship_descriptor_sha256": _canonical_hash(original),
        })
    snapshot: dict[str, Any] = {
        "events": events,
        "outcomes": outcomes,
        "sources": sources,
        "relationships": relationships,
        "material_relationships": material_relationship_rows,
    }
    if coverage_rows:
        row = coverage_rows[0]
        snapshot["coverage"] = {
            "record_id": row.get("record_id"),
            "complete": row.get("complete"),
            "covered_wafer_ids": row.get("covered_wafer_ids"),
            "covered_lot_ids": row.get("covered_lot_ids"),
            "covered_operation_ids": row.get("covered_operation_ids"),
            "population_kind": row.get("population_kind"),
            "source_authority_claim": row.get("source_authority_claim"),
            "covered_source_ids": row.get("covered_source_ids"),
            "window_start": row.get("window_start"),
            "window_end": row.get("window_end"),
            "valid_until": row.get("valid_until"),
            "missing_record_ids": row.get("missing_record_ids"),
            "source_ids": row.get("source_ids"),
            "relationship_id": row.get("relationship_id"),
        }
    if history_coverage_rows:
        row = history_coverage_rows[0]
        snapshot["history_coverage"] = {
            "record_id": row.get("record_id"),
            "complete": row.get("complete"),
            "covered_wafer_ids": row.get("covered_wafer_ids"),
            "covered_lot_ids": row.get("covered_lot_ids"),
            "covered_operation_ids": row.get("covered_operation_ids"),
            "population_kind": row.get("population_kind"),
            "source_authority_claim": row.get("source_authority_claim"),
            "covered_source_ids": row.get("covered_source_ids"),
            "window_start": row.get("window_start"),
            "window_end": row.get("window_end"),
            "valid_until": row.get("valid_until"),
            "missing_record_ids": row.get("missing_record_ids"),
            "source_ids": row.get("source_ids"),
            "relationship_id": row.get("relationship_id"),
        }
    if route_definitions:
        snapshot["expected_routes"] = route_definitions
    if route_coverage_rows:
        row = route_coverage_rows[0]
        snapshot["route_coverage"] = {
            "record_id": row.get("record_id"),
            "complete": row.get("complete"),
            "covered_wafer_ids": row.get("covered_wafer_ids"),
            "covered_lot_ids": row.get("covered_lot_ids"),
            "covered_operation_ids": row.get("covered_operation_ids"),
            "population_kind": row.get("population_kind"),
            "source_authority_claim": row.get("source_authority_claim"),
            "covered_source_ids": row.get("covered_source_ids"),
            "window_start": row.get("window_start"),
            "window_end": row.get("window_end"),
            "valid_until": row.get("valid_until"),
            "missing_record_ids": row.get("missing_record_ids"),
            "source_ids": row.get("source_ids"),
            "relationship_id": row.get("relationship_id"),
        }
    if suspected_exposure is not None:
        snapshot["suspected_exposure"] = suspected_exposure
    if cohort is not None:
        snapshot["cohort"] = cohort
    if target_wafer_ids is not None:
        snapshot["target_wafer_ids"] = target_wafer_ids

    evidence = analyze(snapshot)
    follow_up_metadata = None
    if follow_up_proposal is not None:
        current_candidate = _membership_conflict_candidate(evidence)
        if current_candidate is None:
            raise MCPContractError("The refreshed MCP snapshot no longer contains the proposed lot-membership conflict.")
        supplied_candidate = follow_up_proposal.get("candidate")
        if not isinstance(supplied_candidate, dict) or _canonical_hash(supplied_candidate) != _canonical_hash(current_candidate):
            raise MCPContractError("Follow-up request does not match the current source-linked proposal.")
        if current_candidate.get("proposed_not_executed") is not True:
            raise MCPContractError("Only an explicitly unexecuted, source-linked proposal can be authorized for follow-up.")

        targets = current_candidate.get("target_wafer_ids", [])
        step_ids_by_pair: dict[tuple[str, str], set[str]] = {}
        for reference in current_candidate.get("step_instance_refs", []):
            pair = (reference.get("source_id"), reference.get("relationship_id"))
            step_id = reference.get("step_instance_id")
            if all(pair) and isinstance(step_id, str):
                step_ids_by_pair.setdefault(pair, set()).add(step_id)
        reviewed_plan_by_pair = {
            (source_id, relationship_id): plan
            for plan in read_plans
            for source_id in plan["source_ids"]
            for relationship_id in plan["relationship_ids"]
        }
        follow_up_read_records = []
        base_uuid = uuid.UUID(operation_id) if operation_id else uuid.uuid4()
        for index, pair_spec in enumerate(current_candidate.get("source_relationships", [])):
            source_id, relationship_id = pair_spec.get("source_id"), pair_spec.get("relationship_id")
            pair = (source_id, relationship_id)
            relation = relation_by_id.get(relationship_id)
            if (not isinstance(source_id, str) or not isinstance(relationship_id, str)
                    or relation is None or relation.get("approved") is not True
                    or source_id not in relation.get("source_ids", [])):
                raise MCPContractError("Follow-up source/relationship pair is not approved by current MCP descriptors.")
            reviewed_plan = reviewed_plan_by_pair.get(pair)
            if not isinstance(reviewed_plan, dict):
                raise MCPContractError("Follow-up source/relationship pair has no matching reviewed P2 role mapping.")
            requested_keys = pair_spec.get("requested_declared_keys")
            normalized_relation = _normalize_relationship_field_names(relation, reviewed_plan)
            if not isinstance(requested_keys, list) or any(
                key not in normalized_relation.get("keys", []) for key in requested_keys
            ):
                raise MCPContractError("Follow-up relationship keys do not match the approved pair-specific descriptor.")
            field_mapping = reviewed_plan.get("field_mapping") or {}
            if not isinstance(field_mapping, dict):
                raise MCPContractError("Follow-up source field mapping is malformed.")

            def source_field(logical_name: str) -> str:
                mapped = field_mapping.get(logical_name)
                return mapped if isinstance(mapped, str) and mapped else logical_name

            dataset_role = reviewed_plan.get("dataset_role")
            if dataset_role == "events":
                wafer_field, step_field = source_field("wafer_id"), source_field("step_instance_id")
                filters = {
                    wafer_field: sorted(targets),
                    step_field: sorted(step_ids_by_pair.get(pair, set())),
                }
                if not filters[step_field]:
                    raise MCPContractError("Follow-up process read has no source-linked step instance IDs.")
            elif dataset_role == "material_relationships":
                target_field = source_field("to_entity_id")
                filters = {target_field: sorted(targets)}
            else:
                raise MCPContractError("The synthetic follow-up role is not supported for this proposal.")
            time_field = reviewed_plan.get("time_field")
            if not isinstance(time_field, str) or not time_field:
                raise MCPContractError("Follow-up source has no reviewed time field.")
            plan = {
                "source_ids": [source_id], "relationship_ids": [relationship_id],
                "time_window": time_window, "time_field": time_field, "filters": filters,
                "dataset_role": dataset_role,
                "field_mapping": reviewed_plan.get("field_mapping"),
                "nullable_fields": reviewed_plan.get("nullable_fields", []),
                "relationship_type": reviewed_plan.get("relationship_type"),
                "expected_source_hash": reviewed_plan.get("expected_source_hash"),
                "expected_semantic_version": reviewed_plan.get("expected_semantic_version"),
                "expected_relationship_sha256": reviewed_plan.get("expected_relationship_sha256"),
            }
            read_operation_id = str(uuid.uuid5(base_uuid, f"p2-mcp-follow-up-{index}"))
            try:
                bounded_read = await adapter.read_bounded(
                    plan, permission_context,
                    {"max_rows": 8, "max_bytes": min(limits["max_bytes"], 16000), "max_seconds": limits["max_seconds"]},
                    operation_id=read_operation_id,
                )
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(adapter.cancel(read_operation_id))
                except Exception:
                    pass
                raise
            audit_record = await adapter.audit(read_operation_id)
            if audit_record.get("query_hash") != bounded_read.get("query_hash"):
                raise MCPContractError("The follow-up MCP audit query hash does not match its bounded result.")
            rows = bounded_read.get("typed_rows")
            if not isinstance(rows, list) or bounded_read.get("truncated") is True:
                raise MCPContractError("The follow-up bounded read returned malformed or truncated rows.")
            rows = [_normalize_mapped_row(plan, row) for row in rows]
            if dataset_role == "events":
                target_set = set(targets)
                step_set = set(step_ids_by_pair.get(pair, set()))
                events = [row for row in events if not (
                    row.get("source_id") == source_id and row.get("relationship_id") == relationship_id
                    and row.get("wafer_id") in target_set and row.get("step_instance_id") in step_set
                )]
                events.extend({**row, "approved_relationship": True} for row in rows)
            else:
                material_relationship_rows = [row for row in material_relationship_rows if not (
                    row.get("source_id") == source_id and row.get("relationship_id") == relationship_id
                    and (row.get("to_entity") or {}).get("id") in set(targets)
                )]
                material_relationship_rows.extend(rows)
                snapshot["material_relationships"] = material_relationship_rows
            follow_up_read_records.append({
                "dataset_role": dataset_role, "operation_id": bounded_read["operation_id"],
                "audit_id": bounded_read["audit_id"], "query_hash": bounded_read["query_hash"],
                "audit_query_hash": audit_record["query_hash"], "query_window": bounded_read["query_window"],
                "filters": filters, "source_ids": bounded_read["source_ids"],
                "relationship_ids": bounded_read["relationship_ids"],
                "source_versions": bounded_read["source_versions"], "row_count": len(rows),
                "truncated": bounded_read["truncated"],
            })
            source_ids_used.update(bounded_read.get("source_ids", []))
            relation_ids_used.update(bounded_read.get("relationship_ids", []))
            source_versions.update(bounded_read.get("source_versions", {}))
        snapshot["events"] = events
        evidence = analyze(snapshot)
        follow_up_metadata = {
            "status": "AUTHORIZED_SYNTHETIC_READ_COMPLETED",
            "authorization_decision": "EXPLICIT_SYNTHETIC_OPERATOR_APPROVAL",
            "candidate_category": "LOT_MEMBERSHIP_CONFLICT",
            "candidate_sha256": _canonical_hash(current_candidate),
            "proposed_not_executed_before_decision": True,
            "read_operations": follow_up_read_records,
            "refresh_interpretation": "Re-analysis uses rows returned by the exact bounded follow-up reads; new or conflicting rows may increase uncertainty and are not assumed to resolve the proposal.",
        }
    first = read_records[0]
    evidence["provenance"]["mcp_integration"] = {
        "mode": "SYNTHETIC_PROTOCOL_COMPATIBILITY_ONLY",
        "server_mode": discovered.get("mode", "UNSPECIFIED"),
        "protocol_version": adapter.protocol_version,
        "logical_tool_bindings": dict(sorted(adapter.config["tools"].items())),
        "operations_completed": ["discover", "semantics", "relationships", "read_bounded", "audit"],
        "permission_scope_label": permission_context,
        "permission_scope_authenticated_for_company_use": False,
        "operation_id": first["operation_id"],
        "audit_id": first["audit_id"],
        "read_query_hash": first["query_hash"],
        "audit_query_hash": first["audit_query_hash"],
        "query_window": first["query_window"],
        "read_operations": read_records,
        "source_ids": sorted(source_ids_used),
        "relationship_ids": sorted(relation_ids_used),
        "source_versions": dict(sorted(source_versions.items())),
        "reviewed_field_mappings": reviewed_field_mappings,
        "truncated": truncated,
    }
    if follow_up_metadata is not None:
        evidence["provenance"]["mcp_integration"]["follow_up"] = follow_up_metadata
    evidence["limitations"].append(
        "MCP evidence is from the configured synthetic protocol peer; its fixture approval and permission labels do not establish company authorization or source qualification."
    )
    if truncated:
        evidence["status"] = "PARTIAL"
        evidence["limitations"].append(
            "At least one MCP source read was truncated; this snapshot cannot be treated as a complete event history."
        )
    return evidence
