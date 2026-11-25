"""Deterministic, read-only P2 wafer journey and exposure reconstruction.

This engine accepts a bounded, already-selected evidence snapshot. It is not a
Fab Insight connector and cannot establish real source permissions or meanings.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Callable

from fabintel.contracts import claim, envelope, validate_envelope

ENGINE_VERSION = "0.3.0"
MAX_EVENTS = 100000
MAX_OUTCOMES = 100000
_CANCEL_CHECK: ContextVar[Callable[[], bool] | None] = ContextVar("p2_cancel_check", default=None)
_COVERAGE_AUTHORITY: ContextVar[Callable[[dict[str, Any]], Any] | None] = ContextVar(
    "p2_coverage_authority", default=None,
)

_COVERAGE_LEVELS = {"SOURCE_VERIFIED", "ASSERTED_UNVERIFIED", "PARTIAL", "UNKNOWN", "CONTRADICTORY"}


class InputError(ValueError):
    """Raised internally for malformed or scientifically unsafe input."""


class AnalysisCancelled(RuntimeError):
    """Raised when an operator cancels a bounded local analysis."""


def _check_cancelled() -> None:
    check = _CANCEL_CHECK.get()
    if check is not None and check():
        raise AnalysisCancelled("Analysis was cancelled by the operator.")


def _dt(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise InputError(f"{label} must be an ISO-8601 timestamp with a timezone.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"{label} is not a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InputError(f"{label} has no timezone; chronological order is ambiguous.")
    return parsed.astimezone(timezone.utc)


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a non-empty string.")
    return value


def _seconds(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise InputError(f"{label} must be finite and non-negative.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{label} must be finite and non-negative.") from exc
    if not math.isfinite(result) or result < 0:
        raise InputError(f"{label} must be finite and non-negative.")
    return result


def _material_edges_intersecting_time(index, low: datetime, high: datetime, edge_times):
    """Yield only edges whose half-open effectivity intersects [low, high]."""
    if index is None:
        return
    edges, starts, prefix_max_ends = index
    stop = bisect_right(starts, high)
    start = bisect_right(prefix_max_ends, low, 0, stop)
    for edge in edges[start:stop]:
        edge_start, edge_end = edge_times[edge["record_id"]]
        if low < edge_end and high >= edge_start:
            yield edge


def _build_material_edge_interval_indexes(edges_by_entity, edge_times):
    """Build per-entity interval indexes for time-scoped material relationships."""
    indexes = {}
    for entity, entity_edges in edges_by_entity.items():
        entity_edges.sort(key=lambda edge: (edge_times[edge["record_id"]][0], edge["record_id"]))
        sorted_edges = entity_edges
        starts = []
        prefix_max_ends = []
        latest_end = None
        for edge in sorted_edges:
            edge_start, edge_end = edge_times[edge["record_id"]]
            starts.append(edge_start)
            latest_end = edge_end if latest_end is None else max(latest_end, edge_end)
            prefix_max_ends.append(latest_end)
        indexes[entity] = (sorted_edges, starts, prefix_max_ends)
    return indexes


def _add_lot_lineage_seed(seed_by_lot, lot_id, basis, certainty, provenance):
    existing = seed_by_lot.get(lot_id)
    if existing is None:
        seed_by_lot[lot_id] = {
            "lot_id": lot_id, "basis": basis, "certainty": certainty,
            "provenance": [provenance],
        }
        return
    if existing["basis"] != basis:
        existing["basis"] = "MULTIPLE_SOURCE_LINKED_SEEDS"
    if certainty != "SOURCE_LINKED":
        existing["certainty"] = certainty
    existing["provenance"].append(provenance)


def _trace_lot_lineage(seed_lots, low: datetime, high: datetime, indexes, edge_times):
    """Trace only explicitly typed, time-relevant lot split/merge relationships."""
    allowed_types = {"SPLIT_FROM", "MERGED_FROM"}
    paths = []
    relationships = {}
    for seed in sorted(seed_lots, key=lambda item: item["lot_id"]):
        _check_cancelled()
        seed_id = seed["lot_id"]
        best_path = {seed_id: []}
        pending = deque([seed_id])
        while pending:
            _check_cancelled()
            current_id = pending.popleft()
            for edge in sorted(
                _material_edges_intersecting_time(
                    indexes.get(("lot", current_id)), low, high, edge_times,
                ),
                key=lambda item: item["record_id"],
            ):
                if (edge["relationship_type"] not in allowed_types
                        or edge["from_entity"]["type"] != "lot"
                        or edge["to_entity"]["type"] != "lot"):
                    continue
                record_id = edge["record_id"]
                edge_start, edge_end = edge_times[record_id]
                edge_status = (
                    "EFFECTIVE_ACROSS_EVENT_TIME_UNCERTAINTY"
                    if edge_start <= low and high < edge_end
                    else "POSSIBLY_EFFECTIVE_DUE_TO_CLOCK_UNCERTAINTY"
                )
                relationships.setdefault(record_id, {
                    "record_id": record_id,
                    "relationship_type": edge["relationship_type"],
                    "from_entity": edge["from_entity"],
                    "to_entity": edge["to_entity"],
                    "temporal_status": edge_status,
                    "provenance": edge["provenance"],
                })
                neighbor = (
                    edge["to_entity"]["id"]
                    if edge["from_entity"]["id"] == current_id
                    else edge["from_entity"]["id"]
                )
                if neighbor in best_path:
                    continue
                traversal_step = {
                    "record_id": record_id,
                    "relationship_type": edge["relationship_type"],
                    "from_entity": edge["from_entity"],
                    "to_entity": edge["to_entity"],
                    "traversal_direction": (
                        "FROM_TO" if edge["from_entity"]["id"] == current_id else "TO_FROM"
                    ),
                    "temporal_status": edge_status,
                    "provenance": edge["provenance"],
                }
                path = [*best_path[current_id], traversal_step]
                best_path[neighbor] = path
                pending.append(neighbor)
                uncertain_seed = seed.get("certainty") != "SOURCE_LINKED"
                uncertain_edge = any(
                    item["temporal_status"] != "EFFECTIVE_ACROSS_EVENT_TIME_UNCERTAINTY"
                    for item in path
                )
                paths.append({
                    "start_lot_id": seed_id,
                    "end_lot_id": neighbor,
                    "seed_basis": seed["basis"],
                    "seed_provenance": seed["provenance"],
                    "status": (
                        "POSSIBLE_DUE_TO_TIME_OR_MEMBERSHIP_UNCERTAINTY"
                        if uncertain_seed or uncertain_edge
                        else "SOURCE_LINKED_AT_EVENT_TIME"
                    ),
                    "relationships": path,
                    "meaning": "Connected source-declared lot split/merge edges; direction is retained and no wafer identity or process ordering is inferred.",
                })
    paths.sort(key=lambda item: (item["start_lot_id"], item["end_lot_id"], tuple(edge["record_id"] for edge in item["relationships"])))
    return paths, [relationships[key] for key in sorted(relationships)]


def _refusal(data: Any, reason: str):
    result = envelope("p2", data, "REFUSED", [], [reason])
    result["provenance"]["engine_version"] = ENGINE_VERSION
    validate_envelope(result)
    return result


def _normalize_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    events = data.get("events")
    if not isinstance(events, list) or not events:
        raise InputError("No event records were supplied.")
    if len(events) > MAX_EVENTS:
        raise InputError(f"Event count exceeds the {MAX_EVENTS}-row local analysis bound.")
    normalized = []
    seen_step_instances: dict[tuple[str, str], tuple[dict[str, Any], int]] = {}
    for index, raw in enumerate(events):
        _check_cancelled()
        if not isinstance(raw, dict):
            raise InputError(f"Event {index + 1} is not an object.")
        wafer = _id(raw.get("wafer_id"), f"Event {index + 1} wafer_id")
        step = _id(raw.get("step_instance_id"), f"Event {index + 1} step_instance_id")
        operation = _id(raw.get("operation"), f"Event {index + 1} operation")
        if raw.get("approved_relationship") is not True:
            raise InputError(f"Event {step} has no approved source relationship.")
        source_id = raw.get("source_id")
        if source_id is not None:
            source_id = _id(source_id, f"Event {index + 1} source_id")
        for field in ("chamber_id", "tool_id", "lot_id", "route_id", "route_version", "operation_definition_id", "rework_of_step_instance_id", "rework_of_source_id", "relationship_id", "identity_relationship_id"):
            if raw.get(field) is not None:
                _id(raw[field], f"Event {step} {field}")
        identity = (source_id or "INPUT_SNAPSHOT", step)
        if identity in seen_step_instances:
            original, normalized_index = seen_step_instances[identity]
            if raw != original:
                raise InputError(f"Conflicting duplicate step instance {step} in source {source_id}; the history is ambiguous.")
            normalized[normalized_index]["duplicate_record_copies"] += 1
            continue

        timestamp = _dt(raw.get("timestamp"), f"Event {step} timestamp")
        recorded_at = _dt(raw["recorded_at"], f"Event {step} recorded_at") if "recorded_at" in raw else None
        uncertainty = _seconds(raw.get("time_uncertainty_seconds", 0), f"Event {step} time_uncertainty_seconds")
        try:
            low, high = timestamp - timedelta(seconds=uncertainty), timestamp + timedelta(seconds=uncertainty)
        except (OverflowError, ValueError) as exc:
            if isinstance(exc, InputError):
                raise
            raise InputError(f"Event {step} time uncertainty is outside the supported range.") from exc
        start = end = None
        start_low = start_high = end_low = end_high = None
        if "processing_start" in raw or "processing_end" in raw:
            if "processing_start" not in raw or "processing_end" not in raw:
                raise InputError(f"Event {step} must provide both processing_start and processing_end.")
            start = _dt(raw["processing_start"], f"Event {step} processing_start")
            end = _dt(raw["processing_end"], f"Event {step} processing_end")
            if end <= start:
                raise InputError(f"Event {step} has a non-positive processing interval.")
            start_uncertainty = raw.get("processing_start_uncertainty_seconds", 0)
            end_uncertainty = raw.get("processing_end_uncertainty_seconds", 0)
            start_uncertainty = _seconds(start_uncertainty, f"Event {step} processing_start_uncertainty_seconds")
            end_uncertainty = _seconds(end_uncertainty, f"Event {step} processing_end_uncertainty_seconds")
            try:
                start_low = start - timedelta(seconds=start_uncertainty)
                start_high = start + timedelta(seconds=start_uncertainty)
                end_low = end - timedelta(seconds=end_uncertainty)
                end_high = end + timedelta(seconds=end_uncertainty)
            except (OverflowError, ValueError) as exc:
                raise InputError(f"Event {step} processing-time uncertainty is outside the supported range.") from exc
        else:
            if "processing_start_uncertainty_seconds" in raw or "processing_end_uncertainty_seconds" in raw:
                raise InputError(f"Event {step} processing-time uncertainty requires processing_start and processing_end.")

        row = dict(raw)
        row["duplicate_record_copies"] = 0
        row.update({
            "wafer_id": wafer,
            "step_instance_id": step,
            "operation": operation,
            "source_id": source_id,
            "_source_key": source_id or "INPUT_SNAPSHOT",
            "identity_relationship_id": raw.get("identity_relationship_id"),
            "_time": timestamp,
            "_recorded_at": recorded_at,
            "_low": low,
            "_high": high,
            "_time_uncertainty_seconds": uncertainty,
            "_start": start,
            "_end": end,
            "_start_low": start_low,
            "_start_high": start_high,
            "_end_low": end_low,
            "_end_high": end_high,
        })
        seen_step_instances[identity] = (dict(raw), len(normalized))
        normalized.append(row)
    return normalized


def _bounded_outcomes(data: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes = data.get("outcomes", [])
    if not isinstance(outcomes, list):
        raise InputError("outcomes must be a list.")
    if len(outcomes) > MAX_OUTCOMES:
        raise InputError(f"Outcome count exceeds the {MAX_OUTCOMES}-row local analysis bound.")
    return outcomes


def _sort_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[list[str]], list[list[str]]]:
    ordered = sorted(events, key=lambda row: (
        row["_time"], row["_source_key"], row["step_instance_id"], row["wafer_id"]
    ))
    groups: dict[tuple[str, datetime], list[str]] = defaultdict(list)
    by_wafer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        _check_cancelled()
        groups[(row["wafer_id"], row["_time"])].append(row["step_instance_id"])
        by_wafer[row["wafer_id"]].append(row)
    ties = [ids for ids in groups.values() if len(ids) > 1]
    uncertain_groups = []
    for rows in by_wafer.values():
        _check_cancelled()
        intervals = sorted(rows, key=lambda row: (row["_low"], row["_high"], row["step_instance_id"]))
        cluster = []
        cluster_end = None
        for row in intervals:
            _check_cancelled()
            if cluster and row["_low"] <= cluster_end:
                cluster.append(row["step_instance_id"])
                cluster_end = max(cluster_end, row["_high"])
            else:
                if len(cluster) > 1:
                    uncertain_groups.append(sorted(cluster))
                cluster = [row["step_instance_id"]]
                cluster_end = row["_high"]
        if len(cluster) > 1:
            uncertain_groups.append(sorted(cluster))
    return ordered, ties, sorted(uncertain_groups)


def _approved_sources(data: dict[str, Any]) -> list[dict[str, Any]]:
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise InputError("sources must be a list of approved source references.")
    normalized = []
    source_ids = set()
    for item in sources:
        _check_cancelled()
        if not isinstance(item, dict):
            raise InputError("Each source reference must be an object.")
        required = ("id", "approved_semantic_version", "grain", "source_hash")
        if any(not isinstance(item.get(key), str) or not item[key] for key in required):
            raise InputError("A source reference is missing its approved version, grain, or content hash.")
        if set(item) - set(required) - {"permissions_ref", "observed_at"}:
            raise InputError("A source reference contains fields outside the frozen evidence contract.")
        if any(key in item and not isinstance(item[key], str) for key in ("permissions_ref", "observed_at")):
            raise InputError("Optional source permission and observation references must be strings.")
        if item["id"] in source_ids:
            raise InputError(f"Duplicate source reference {item['id']}.")
        source_ids.add(item["id"])
        normalized.append({key: value for key, value in item.items() if key in {
            "id", "approved_semantic_version", "grain", "source_hash", "permissions_ref", "observed_at"
        }})
    return sorted(normalized, key=lambda item: item["id"])


def _validate_relationships(data: dict[str, Any], events: list[dict[str, Any]], known_source_ids: set[str]):
    # A caller's boolean flag is not source provenance. Even synthetic snapshots
    # must carry explicit source and relationship records before events are used.
    if not known_source_ids:
        raise InputError("Events require source records; approved_relationship flags alone are not evidence.")
    relationships = data.get("relationships")
    if not isinstance(relationships, list) or not relationships:
        raise InputError("Source-linked events require approved relationship metadata.")
    by_id = {}
    for relation in relationships:
        _check_cancelled()
        if not isinstance(relation, dict):
            raise InputError("Relationship metadata must be a list of objects.")
        relation_id = _id(relation.get("id"), "relationship id")
        if relation_id in by_id:
            raise InputError(f"Duplicate relationship id {relation_id}.")
        if relation.get("approved") is not True:
            raise InputError(f"Relationship {relation_id} is not approved.")
        source_ids = relation.get("source_ids")
        keys = relation.get("keys")
        if (not isinstance(source_ids, list) or not source_ids or
                any(not isinstance(source_id, str) or source_id not in known_source_ids for source_id in source_ids)):
            raise InputError(f"Relationship {relation_id} has no approved source references.")
        if not isinstance(keys, list) or not keys or any(not isinstance(key, str) or not key for key in keys):
            raise InputError(f"Relationship {relation_id} has no declared join keys.")
        for field in ("cardinality", "grain"):
            _id(relation.get(field), f"relationship {relation_id} {field}")
        effective_start = _dt(relation.get("effective_start"), f"relationship {relation_id} effective_start")
        effective_end = _dt(relation.get("effective_end"), f"relationship {relation_id} effective_end")
        if effective_end <= effective_start:
            raise InputError(f"Relationship {relation_id} has invalid effectivity bounds.")
        by_id[relation_id] = (set(source_ids), set(keys), effective_start, effective_end, relation)
    for event in events:
        _check_cancelled()
        if not event["source_id"] or event["source_id"] not in known_source_ids:
            raise InputError(f"Event {event['step_instance_id']} has no approved source record.")
        relation_id = event.get("relationship_id")
        if relation_id not in by_id:
            raise InputError(f"Event {event['step_instance_id']} has no approved relationship reference.")
        relation_sources, relation_keys, effective_start, effective_end, _relation = by_id[relation_id]
        if event["source_id"] not in relation_sources:
            raise InputError(f"Relationship {relation_id} does not cover event source {event['source_id']}.")
        if not {"wafer_id", "step_instance_id", "timestamp"}.issubset(relation_keys):
            raise InputError(
                f"Event relationship {relation_id} must authorize wafer_id, step_instance_id, and timestamp."
            )
        if any(key not in event for key in relation_keys):
            raise InputError(f"Relationship {relation_id} join keys are missing from event {event['step_instance_id']}.")
        if event.get("rework_of_step_instance_id") is not None and "rework_of_step_instance_id" not in relation_keys:
            raise InputError(f"Rework link for step {event['step_instance_id']} is not covered by its approved relationship keys.")
        if event.get("rework_of_source_id") is not None and "rework_of_source_id" not in relation_keys:
            raise InputError(f"Cross-source rework link for step {event['step_instance_id']} is not covered by its approved relationship keys.")
        if event.get("operation_definition_id") is not None and "operation_definition_id" not in relation_keys:
            raise InputError(f"Operation definition reference for step {event['step_instance_id']} is not covered by its approved relationship keys.")
        if not effective_start <= event["_time"] < effective_end:
            raise InputError(f"Relationship {relation_id} is not effective at event {event['step_instance_id']} time.")
    by_wafer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        _check_cancelled()
        by_wafer[event["wafer_id"]].append(event)
    for wafer_id, rows in by_wafer.items():
        _check_cancelled()
        source_ids = {row["source_id"] for row in rows if row["source_id"]}
        if len(source_ids) <= 1:
            continue
        identity_ids = {row["identity_relationship_id"] for row in rows}
        if len(identity_ids) != 1 or None in identity_ids:
            raise InputError(f"Wafer token {wafer_id} appears in multiple sources without an approved identity relationship.")
        identity_id = next(iter(identity_ids))
        if identity_id not in by_id:
            raise InputError(f"Wafer token {wafer_id} references an unknown identity relationship.")
        identity_sources, identity_keys, identity_start, identity_end, identity_relation = by_id[identity_id]
        if identity_relation.get("entity_identity") is not True or "wafer_id" not in identity_keys or not source_ids.issubset(identity_sources):
            raise InputError(f"Identity relationship {identity_id} does not approve wafer equivalence across these sources.")
        if any(not identity_start <= row["_low"] or row["_high"] >= identity_end for row in rows):
            raise InputError(
                f"Identity relationship {identity_id} is not effective across the full event-time uncertainty interval for wafer token {wafer_id}."
            )
    return by_id


def _validate_outcome_provenance(data: dict[str, Any], outcomes: list[dict[str, Any]], known_source_ids: set[str], relationships: dict[str, Any]) -> None:
    for outcome in outcomes:
        _check_cancelled()
        if not isinstance(outcome, dict):
            raise InputError("Each outcome must be an object.")
        if outcome.get("approved_relationship") is not True:
            raise InputError("Outcome row has no approved relationship.")
        source_id = outcome.get("source_id")
        if not isinstance(source_id, str) or source_id not in known_source_ids:
            raise InputError("Outcome row has no approved source metadata.")
        relation_id = outcome.get("relationship_id")
        if relation_id not in relationships:
            raise InputError("Outcome row has no approved relationship metadata.")
        relation_sources, keys, start, end, _relation = relationships[relation_id]
        if source_id not in relation_sources or "wafer_id" not in keys:
            raise InputError(f"Outcome relationship {relation_id} does not support its source and wafer key.")
        if "timestamp" not in keys:
            raise InputError(f"Outcome relationship {relation_id} does not declare the timestamp used for temporal analysis.")
        if any(key not in outcome for key in keys):
            raise InputError(f"Outcome relationship {relation_id} join keys are missing from an outcome row.")
        timestamp = _dt(outcome.get("timestamp"), "outcome timestamp")
        if not start <= timestamp < end:
            raise InputError(f"Outcome relationship {relation_id} is not effective at the outcome timestamp.")


def _relationship_evidence(relationships: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    for relation_id, (source_ids, keys, start, end, relation) in sorted(relationships.items()):
        record = {
            "id": relation_id,
            "status": "CALLER_DECLARED_APPROVED",
            "source_ids": sorted(source_ids),
            "keys": sorted(keys),
            "cardinality": relation["cardinality"],
            "grain": relation["grain"],
            "effective_start_utc": start.isoformat(),
            "effective_end_utc": end.isoformat(),
        }
        if relation.get("entity_identity") is True:
            record["entity_identity"] = True
        if isinstance(relation.get("relationship_type"), str) and relation["relationship_type"]:
            record["relationship_type"] = relation["relationship_type"]
        if isinstance(relation.get("source_declared_keys"), list):
            record["source_declared_keys"] = sorted(relation["source_declared_keys"])
        if isinstance(relation.get("field_aliases"), dict):
            record["field_aliases"] = dict(sorted(relation["field_aliases"].items()))
        if isinstance(relation.get("descriptor_sha256"), str):
            record["descriptor_sha256"] = relation["descriptor_sha256"]
        evidence.append(record)
    return evidence


def _approved_operation_definitions(
    data: dict[str, Any], known_source_ids: set[str], relationships: dict[str, Any], events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    definitions = data.get("operation_definitions", [])
    if not isinstance(definitions, list):
        raise InputError("operation_definitions must be a list of approved source records.")
    sources = {item["id"]: item for item in data.get("sources", []) if isinstance(item, dict) and item.get("id") in known_source_ids}
    by_id: dict[str, dict[str, Any]] = {}
    for item in definitions:
        _check_cancelled()
        if not isinstance(item, dict) or item.get("approved") is not True:
            raise InputError("Operation definitions must be explicit approved records.")
        definition_id = _id(item.get("operation_definition_id"), "operation_definition_id")
        operation = _id(item.get("operation"), f"operation definition {definition_id} operation")
        source_id = _id(item.get("source_id"), f"operation definition {definition_id} source_id")
        relation_id = _id(item.get("relationship_id"), f"operation definition {definition_id} relationship_id")
        version = _id(item.get("semantic_version"), f"operation definition {definition_id} semantic_version")
        if source_id not in known_source_ids or sources[source_id]["approved_semantic_version"] != version:
            raise InputError(f"Operation definition {definition_id} does not match an approved source semantic version.")
        if relation_id not in relationships:
            raise InputError(f"Operation definition {definition_id} has no approved relationship.")
        relation_sources, keys, rel_start, rel_end, _ = relationships[relation_id]
        if source_id not in relation_sources or not {"operation_definition_id", "operation"}.issubset(keys):
            raise InputError(f"Operation definition {definition_id} is not linked by its declared source relationship keys.")
        start = _dt(item.get("effective_start"), f"operation definition {definition_id} effective_start")
        end = _dt(item.get("effective_end"), f"operation definition {definition_id} effective_end")
        if end <= start or start < rel_start or end > rel_end:
            raise InputError(f"Operation definition {definition_id} has invalid effective bounds.")
        if definition_id in by_id:
            raise InputError(f"Duplicate operation definition ID {definition_id}.")
        by_id[definition_id] = {
            "operation_definition_id": definition_id,
            "operation": operation,
            "source_id": source_id,
            "semantic_version": version,
            "relationship_id": relation_id,
            "effective_start": start,
            "effective_end": end,
        }
    if by_id:
        for event in events:
            _check_cancelled()
            definition_id = event.get("operation_definition_id")
            if definition_id not in by_id:
                raise InputError(f"Event {event['step_instance_id']} does not resolve to an approved operation definition.")
            definition = by_id[definition_id]
            if definition["operation"] != event["operation"]:
                raise InputError(f"Event {event['step_instance_id']} operation label conflicts with its operation definition.")
            if not definition["effective_start"] <= event["_time"] < definition["effective_end"]:
                raise InputError(f"Operation definition {definition_id} is not effective at event {event['step_instance_id']} time.")
            event_relation = relationships[event["relationship_id"]]
            if definition["source_id"] not in event_relation[0]:
                raise InputError(f"Event {event['step_instance_id']} relationship does not connect its operation definition source.")
    elif any(event.get("operation_definition_id") is not None for event in events):
        raise InputError("An event names an operation definition but no definition record was supplied.")
    return by_id


def _material_relationships(
    data: dict[str, Any], known_source_ids: set[str], relationships: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_edges = data.get("material_relationships", [])
    if not isinstance(raw_edges, list):
        raise InputError("material_relationships must be a list of source-linked relationships.")
    sources = {item["id"]: item for item in data.get("sources", []) if isinstance(item, dict) and item.get("id") in known_source_ids}
    seen_ids = set()
    edges = []
    for index, item in enumerate(raw_edges):
        _check_cancelled()
        if not isinstance(item, dict):
            raise InputError(f"Material relationship {index + 1} must be an object.")
        edge_id = _id(item.get("record_id"), f"material relationship {index + 1} record_id")
        relationship_type = _id(item.get("relationship_type"), f"material relationship {edge_id} relationship_type")
        source_id = _id(item.get("source_id"), f"material relationship {edge_id} source_id")
        relation_id = _id(item.get("relationship_id"), f"material relationship {edge_id} relationship_id")
        if edge_id in seen_ids:
            raise InputError(f"Duplicate material relationship record ID {edge_id}.")
        seen_ids.add(edge_id)
        if source_id not in known_source_ids or relation_id not in relationships:
            raise InputError(f"Material relationship {edge_id} has no approved source or relationship record.")
        relation_sources, keys, rel_start, rel_end, relation = relationships[relation_id]
        if source_id not in relation_sources or relation.get("relationship_type") != relationship_type:
            raise InputError(f"Material relationship {edge_id} does not match its approved source relationship type.")
        from_entity = item.get("from_entity")
        to_entity = item.get("to_entity")
        if not isinstance(from_entity, dict) or not isinstance(to_entity, dict):
            raise InputError(f"Material relationship {edge_id} must preserve both typed entity endpoints.")
        from_type = _id(from_entity.get("type"), f"material relationship {edge_id} from entity type")
        from_id = _id(from_entity.get("id"), f"material relationship {edge_id} from entity ID")
        to_type = _id(to_entity.get("type"), f"material relationship {edge_id} to entity type")
        to_id = _id(to_entity.get("id"), f"material relationship {edge_id} to entity ID")
        key_values = item.get("key_values")
        if not isinstance(key_values, dict) or any(key not in key_values for key in keys):
            raise InputError(f"Material relationship {edge_id} is missing declared relationship key values.")
        key_endpoint_values = {
            "from_entity_id": from_id, "from_entity_type": from_type,
            "to_entity_id": to_id, "to_entity_type": to_type,
        }
        if any(key in key_endpoint_values and key_values[key] != key_endpoint_values[key] for key in keys):
            raise InputError(f"Material relationship {edge_id} endpoint values conflict with declared join keys.")
        start = _dt(item.get("effective_start"), f"material relationship {edge_id} effective_start")
        end = _dt(item.get("effective_end"), f"material relationship {edge_id} effective_end")
        observed_at = _dt(item.get("observed_at"), f"material relationship {edge_id} observed_at")
        if end <= start or start < rel_start or end > rel_end or not rel_start <= observed_at < rel_end:
            raise InputError(f"Material relationship {edge_id} is outside its approved effective interval.")
        declared_hash = item.get("source_hash")
        if declared_hash is not None and declared_hash != sources[source_id]["source_hash"]:
            raise InputError(f"Material relationship {edge_id} source hash does not match its source record.")
        edges.append({
            "record_id": edge_id,
            "relationship_type": relationship_type,
            "from_entity": {"type": from_type, "id": from_id},
            "to_entity": {"type": to_type, "id": to_id},
            "effective_start": start.isoformat(),
            "effective_end": end.isoformat(),
            "observed_at": observed_at.isoformat(),
            "key_values": {key: key_values[key] for key in sorted(key_values)},
            "provenance": {
                "source_id": source_id,
                "source_semantic_version": sources[source_id]["approved_semantic_version"],
                "source_hash": sources[source_id]["source_hash"],
                "relationship_id": relation_id,
                "relationship_keys": sorted(keys),
                "relationship_type": relationship_type,
            },
        })
    return sorted(edges, key=lambda edge: edge["record_id"])


def _material_lineage_coverage(
    data: dict[str, Any], event: dict[str, Any], seeds: list[dict[str, Any]],
    paths: list[dict[str, Any]], material_edges: list[dict[str, Any]],
    known_source_ids: set[str], relationships: dict[str, Any],
) -> dict[str, Any]:
    """Assess caller-declared source coverage for this event's material lineage scope.

    The result is deliberately a caller-declared evidence state, never authentication
    of a live source or an approval supplied by the caller alone.
    """
    raw = data.get("material_relationship_coverage")
    if not isinstance(raw, dict) or not seeds:
        return {
            "status": "NOT_ESTABLISHED",
            "coverage_evidence_level": "UNKNOWN",
            "record_id": None,
            "relationship_id": None,
            "covered_source_ids": [],
            "covered_relationship_types": [],
            "covered_entities": [],
            "missing_record_ids": [],
            "assessment": "No material coverage record and verified lot seed jointly establish graph completeness for this event.",
            "company_source_authenticated": False,
        }

    def incomplete(reason: str, *, level: str = "PARTIAL", **details: Any) -> dict[str, Any]:
        return {
            "status": "INCOMPLETE_OR_UNKNOWN",
            "coverage_evidence_level": level,
            "record_id": raw.get("record_id") if isinstance(raw.get("record_id"), str) else None,
            "relationship_id": raw.get("relationship_id") if isinstance(raw.get("relationship_id"), str) else None,
            "covered_source_ids": raw.get("covered_source_ids", []) if isinstance(raw.get("covered_source_ids"), list) else [],
            "covered_relationship_types": raw.get("covered_relationship_types", []) if isinstance(raw.get("covered_relationship_types"), list) else [],
            "covered_entities": raw.get("covered_entities", []) if isinstance(raw.get("covered_entities"), list) else [],
            "missing_record_ids": raw.get("missing_record_ids", []) if isinstance(raw.get("missing_record_ids"), list) else [],
            "assessment": reason,
            "company_source_authenticated": False,
            **details,
        }

    required_keys = {
        "record_id", "complete", "covered_entities", "covered_relationship_types",
        "covered_source_ids", "window_start", "window_end", "missing_record_ids",
    }
    record_id, relation_id = raw.get("record_id"), raw.get("relationship_id")
    if not isinstance(record_id, str) or not record_id or not isinstance(relation_id, str) or relation_id not in relationships:
        return incomplete("Material coverage has no approved source relationship or record ID.")
    if raw.get("complete") is not True:
        return incomplete("Material coverage does not assert a complete source snapshot.")
    coverage_sources = raw.get("source_ids")
    covered_source_ids = raw.get("covered_source_ids")
    types = raw.get("covered_relationship_types")
    entities = raw.get("covered_entities")
    missing = raw.get("missing_record_ids")
    if (not isinstance(coverage_sources, list) or not coverage_sources
            or any(not isinstance(value, str) or value not in known_source_ids for value in coverage_sources)
            or len(coverage_sources) != len(set(coverage_sources))):
        return incomplete("Material coverage source IDs are missing, duplicated, or not approved in source metadata.")
    relation_sources, relation_keys, relation_start, relation_end, _relation = relationships[relation_id]
    if (not set(coverage_sources).issubset(relation_sources)
            or not required_keys.issubset(relation_keys)):
        return incomplete("Material coverage relationship does not authorize its source and required coverage fields.")
    if not isinstance(covered_source_ids, list) or not covered_source_ids or any(
            not isinstance(value, str) or value not in known_source_ids for value in covered_source_ids):
        return incomplete("Material coverage must list approved sources for the material relationship records.")
    if len(covered_source_ids) != len(set(covered_source_ids)):
        return incomplete("Material coverage repeats a covered material source ID.")
    if not isinstance(types, list) or any(not isinstance(value, str) or not value for value in types):
        return incomplete("Material coverage relationship types are missing or invalid.")
    if len(types) != len(set(types)):
        return incomplete("Material coverage repeats a relationship type.")
    if not set(types).issubset({"SPLIT_FROM", "MERGED_FROM", "LOT_MEMBERSHIP"}):
        return incomplete("Material coverage contains a relationship type outside the typed lot-lineage contract.")
    required_types = {"SPLIT_FROM", "MERGED_FROM"}
    if any(seed.get("basis") == "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP" for seed in seeds):
        required_types.add("LOT_MEMBERSHIP")
    if not required_types.issubset(set(types)):
        return incomplete("Material coverage omits a relationship type needed for the lineage query.", required_relationship_types=sorted(required_types))
    if not isinstance(entities, list):
        return incomplete("Material coverage has no typed covered-entity population.")
    entity_refs = set()
    for item in entities:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str) or not item["type"] or not isinstance(item.get("id"), str) or not item["id"]:
            return incomplete("Material coverage contains an invalid typed entity reference.")
        ref = (item["type"], item["id"])
        if ref in entity_refs:
            return incomplete("Material coverage repeats a typed entity reference.")
        entity_refs.add(ref)
    required_entities = {("lot", seed["lot_id"]) for seed in seeds}
    for path in paths:
        required_entities.add(("lot", path["start_lot_id"]))
        required_entities.add(("lot", path["end_lot_id"]))
    if any(seed.get("basis") == "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP" for seed in seeds):
        required_entities.add(("wafer", event["wafer_id"]))
    if not required_entities.issubset(entity_refs):
        return incomplete("Material coverage does not include every event seed and observed lineage endpoint.",
                          uncovered_entities=[{"type": kind, "id": identifier}
                                              for kind, identifier in sorted(required_entities - entity_refs)])
    if not isinstance(missing, list) or any(not isinstance(value, str) or not value for value in missing):
        return incomplete("Material coverage missing_record_ids must be a list of explicit record IDs.")
    if missing:
        return incomplete("Material coverage declares missing records.", level="CONTRADICTORY")
    try:
        cover_start = _dt(raw.get("window_start"), "material coverage window_start")
        cover_end = _dt(raw.get("window_end"), "material coverage window_end")
    except InputError:
        return incomplete("Material coverage has invalid timezone-aware window bounds.")
    if cover_end <= cover_start or cover_start > event["_low"] or event["_high"] >= cover_end:
        return incomplete("Material coverage does not contain the full event-time uncertainty interval.")
    if cover_start < relation_start or cover_end > relation_end:
        return incomplete("Material coverage window is outside its approved relationship effectivity.")

    endpoint_keys = {"from_entity_type", "from_entity_id", "to_entity_type", "to_entity_id"}
    required_edge_types = set(types)
    for edge_type in required_edge_types:
        applicable = [
            (source_ids, keys, effective_start, effective_end, relation)
            for source_ids, keys, effective_start, effective_end, relation in relationships.values()
            if relation.get("relationship_type") == edge_type
            and set(covered_source_ids).intersection(source_ids)
            and endpoint_keys.issubset(keys)
            and effective_start <= cover_start and cover_end <= effective_end
        ]
        if not applicable:
            return incomplete("No covered source relationship authorizes the declared material edge type over the coverage window.",
                              unsupported_relationship_type=edge_type)
    declared_sources = set(covered_source_ids)
    declared_types = set(types)
    for edge in material_edges:
        if edge["relationship_type"] not in declared_types:
            continue
        endpoints = {
            (edge["from_entity"]["type"], edge["from_entity"]["id"]),
            (edge["to_entity"]["type"], edge["to_entity"]["id"]),
        }
        if endpoints & entity_refs and not edge["provenance"]["source_id"] in declared_sources:
            return incomplete("A material edge in the declared entity scope comes from an omitted source.",
                              omitted_edge_record_id=edge["record_id"])
    return {
        "status": "CALLER_DECLARED_SOURCE_LINKED_COMPLETE",
        "coverage_evidence_level": "ASSERTED_UNVERIFIED",
        "record_id": record_id,
        "relationship_id": relation_id,
        "source_ids": sorted(coverage_sources),
        "covered_source_ids": sorted(covered_source_ids),
        "covered_relationship_types": sorted(types),
        "covered_entities": [{"type": kind, "id": identifier} for kind, identifier in sorted(entity_refs)],
        "window_start": cover_start.isoformat(),
        "window_end": cover_end.isoformat(),
        "missing_record_ids": [],
        "assessment": "The caller-declared coverage record and effective source relationship span the query uncertainty and all observed lineage seeds/endpoints. This is ASSERTED_UNVERIFIED and is not authenticated against a live source service.",
        "company_source_authenticated": False,
    }


def _coverage_authorization(raw: dict[str, Any], relationship_id: str, source_ids: list[str],
                            covered_source_ids: list[str], covered_wafer_ids: list[str],
                            covered_lot_ids: list[str], covered_operation_ids: list[str],
                            window_start: str, window_end: str, valid_until: str) -> dict[str, Any] | None:
    """Only an out-of-band host authority can authenticate a complete claim.

    Evidence JSON fields such as ``coverage_level`` or ``source_authority`` are
    descriptive claims and are never consulted here. The verifier must return
    the exact scope it independently authorized.
    """
    verifier = _COVERAGE_AUTHORITY.get()
    if verifier is None:
        return None
    scope = {
        "record_id": raw.get("record_id"),
        "relationship_id": relationship_id,
        "source_ids": sorted(source_ids),
        "covered_source_ids": sorted(covered_source_ids),
        "population_kind": raw.get("population_kind"),
        "covered_wafer_ids": sorted(covered_wafer_ids),
        "covered_lot_ids": sorted(covered_lot_ids),
        "covered_operation_ids": sorted(covered_operation_ids),
        "window_start": window_start,
        "window_end": window_end,
        "valid_until": valid_until,
    }
    try:
        grant = verifier({"scope": scope, "source_authority_claim": raw.get("source_authority_claim")})
    except Exception:
        return None
    if (not isinstance(grant, dict) or grant.get("authorized") is not True
            or not isinstance(grant.get("authority_id"), str) or not grant["authority_id"]
            or not isinstance(grant.get("authorization_ref"), str) or not grant["authorization_ref"]
            or grant.get("scope") != scope):
        return None
    return {"authority_id": grant["authority_id"], "authorization_ref": grant["authorization_ref"]}


def _coverage_scope_index(coverage: Any) -> dict[str, tuple[bool, frozenset[str]]]:
    """Index repeated coverage membership checks without changing their validation rules."""
    if not isinstance(coverage, dict):
        return {}
    indexed = {}
    for field in ("covered_wafer_ids", "covered_lot_ids", "covered_operation_ids"):
        values = coverage.get(field)
        valid = (
            isinstance(values, list)
            and all(isinstance(item, str) and item for item in values)
            and len(values) == len(set(values))
        )
        indexed[field] = (valid, frozenset(values) if valid else frozenset())
    return indexed


def _coverage_event_index(events: list[dict[str, Any]]) -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    operations_by_wafer: dict[str, set[str]] = defaultdict(set)
    lots_by_wafer: dict[str, set[str]] = defaultdict(set)
    for row in events:
        _check_cancelled()
        wafer_id = row.get("wafer_id")
        if not isinstance(wafer_id, str):
            continue
        if isinstance(row.get("operation"), str):
            operations_by_wafer[wafer_id].add(row["operation"])
        if isinstance(row.get("lot_id"), str):
            lots_by_wafer[wafer_id].add(row["lot_id"])
    return {
        wafer_id: (frozenset(operations_by_wafer[wafer_id]), frozenset(lots_by_wafer[wafer_id]))
        for wafer_id in operations_by_wafer.keys() | lots_by_wafer.keys()
    }


def _coverage_level(data: dict[str, Any], population: set[str], start: datetime, end: datetime,
                    known_source_ids: set[str], relationships: dict[str, Any],
                    required_source_ids: set[str] | None = None,
                    observation_keys: set[str] | None = None,
                    required_operation_ids: set[str] | None = None,
                    required_lot_ids: set[str] | None = None,
                    coverage_scope_index: dict[str, tuple[bool, frozenset[str]]] | None = None) -> tuple[str, str]:
    coverage = data.get("coverage")
    if coverage is None:
        return "UNKNOWN", "No completeness evidence was supplied; absence of process rows cannot establish nonexposure."
    if not isinstance(coverage, dict):
        return "PARTIAL", "Completeness evidence is not a structured source record."
    complete = coverage.get("complete")
    if not isinstance(complete, bool):
        return "PARTIAL", "Completeness evidence has no explicit complete/incomplete value."
    missing_records = coverage.get("missing_record_ids")
    if (not isinstance(missing_records, list)
            or any(not isinstance(item, str) or not item for item in missing_records)
            or len(missing_records) != len(set(missing_records))):
        return "CONTRADICTORY" if complete is True else "PARTIAL", "Missing-record scope is malformed or duplicated."
    if complete and missing_records:
        return "CONTRADICTORY", "The source claims complete coverage while also naming missing records: " + ", ".join(sorted(missing_records)) + "."
    if not complete:
        return "PARTIAL", "The source explicitly marks the requested observation scope incomplete."

    covered = coverage.get("covered_wafer_ids")
    covered_lots = coverage.get("covered_lot_ids")
    covered_operations = coverage.get("covered_operation_ids")
    scope_index = coverage_scope_index if coverage_scope_index is not None else _coverage_scope_index(coverage)
    covered_valid, covered_set = scope_index.get("covered_wafer_ids", (False, frozenset()))
    covered_lots_valid, covered_lot_set = scope_index.get("covered_lot_ids", (False, frozenset()))
    covered_operations_valid, covered_operation_set = scope_index.get("covered_operation_ids", (False, frozenset()))
    refs = coverage.get("source_ids")
    covered_sources = coverage.get("covered_source_ids")
    population_kind = coverage.get("population_kind")
    authority_claim = coverage.get("source_authority_claim")
    if not covered_valid:
        return "CONTRADICTORY", "The claimed wafer population is malformed or duplicated."
    if not population.issubset(covered_set):
        return "PARTIAL", "Coverage does not include every wafer in the requested population."
    if not covered_lots_valid:
        return "PARTIAL", "Completeness evidence does not define a unique lot-membership scope."
    if required_lot_ids and not required_lot_ids.issubset(covered_lot_set):
        return "CONTRADICTORY", "Observed lot identities fall outside the declared completeness scope."
    if population_kind != "WAFER":
        return "PARTIAL", "The completeness record must explicitly define its population as wafer identities."
    if not covered_operations_valid or not covered_operations:
        return "PARTIAL", "Completeness evidence does not define a unique operation scope."
    if required_operation_ids and not required_operation_ids.issubset(covered_operation_set):
        return "CONTRADICTORY", "Observed operation IDs fall outside the declared completeness scope."
    if not isinstance(authority_claim, str) or not authority_claim.strip():
        return "PARTIAL", "The completeness record does not identify its claimed source authority."
    if (not isinstance(refs, list) or not refs or any(not isinstance(item, str) or not item for item in refs)
            or not set(refs).issubset(known_source_ids)):
        return "PARTIAL", "Coverage source provenance is missing or does not resolve to approved source metadata."
    if (not isinstance(covered_sources, list) or not covered_sources
            or any(not isinstance(item, str) or item not in known_source_ids for item in covered_sources)):
        return "PARTIAL", "The covered observation sources do not resolve to approved source metadata."
    if required_source_ids and not required_source_ids.issubset(set(covered_sources)):
        return "CONTRADICTORY", "Completeness is asserted despite observed source IDs omitted from the covered-source scope."
    if observation_keys:
        for source_id in required_source_ids or set():
            matching = [
                (relation_start, relation_end)
                for source_ids, keys, relation_start, relation_end, _relation in relationships.values()
                if source_id in source_ids and observation_keys.issubset(keys)
            ]
            if not matching or not any(relation_start <= start and end <= relation_end
                                        for relation_start, relation_end in matching):
                return "PARTIAL", "No approved observation relationship spans the requested source fields and time window."
    relation_id = coverage.get("relationship_id")
    record_id = coverage.get("record_id")
    if not isinstance(relation_id, str) or relation_id not in relationships or not isinstance(record_id, str) or not record_id:
        return "PARTIAL", "Coverage has no approved source relationship and record provenance."
    relation_sources, relation_keys, relation_start, relation_end, _relation = relationships[relation_id]
    required_keys = {
        "record_id", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids",
        "covered_source_ids", "population_kind", "source_authority_claim", "window_start", "window_end",
        "valid_until", "missing_record_ids",
    }
    if not set(refs).issubset(relation_sources) or not required_keys.issubset(relation_keys):
        return "PARTIAL", "The approved coverage relationship does not declare every scope and provenance field."
    try:
        cover_start = _dt(coverage.get("window_start"), "coverage window_start")
        cover_end = _dt(coverage.get("window_end"), "coverage window_end")
        valid_until = _dt(coverage.get("valid_until"), "coverage valid_until")
    except InputError:
        return "PARTIAL", "Coverage bounds or validity are missing or timezone-ambiguous."
    if (cover_end <= cover_start or cover_start > start or cover_end < end
            or valid_until < end or cover_start < relation_start or cover_end > relation_end):
        return "PARTIAL", "Coverage is expired, outside its approved effectivity, or does not contain the requested window."
    if required_source_ids and not required_source_ids.issubset(set(covered_sources)):
        return "CONTRADICTORY", "Coverage omits an observed source required to interpret the requested population."
    auth = _coverage_authorization(
        coverage, relation_id, refs, covered_sources, covered, covered_lots, covered_operations,
        cover_start.isoformat(), cover_end.isoformat(), valid_until.isoformat(),
    )
    if auth is not None:
        return "SOURCE_VERIFIED", (
            "An out-of-band host authority verified the exact source, population, operation, time, relationship, and provenance scope "
            f"({auth['authority_id']} / {auth['authorization_ref']})."
        )
    return "ASSERTED_UNVERIFIED", "Coverage is structurally source-linked but caller-asserted; no independent authorized source-completeness grant was supplied."


def _history_coverage(data: dict[str, Any], events: list[dict[str, Any]], known_source_ids: set[str], relationships: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("history_coverage")
    if raw is None:
        return {"status": "UNKNOWN", "coverage_evidence_level": "UNKNOWN", "covered_wafer_ids": [], "covered_lot_ids": [], "covered_operation_ids": [], "covered_source_ids": [], "source_references": [], "missing_record_ids": [], "source_authority_claim": None, "source_authority": None}
    if not isinstance(raw, dict):
        raise InputError("history_coverage must be an object.")
    complete = raw.get("complete")
    if not isinstance(complete, bool):
        raise InputError("history_coverage complete must be explicit true or false.")
    covered = raw.get("covered_wafer_ids")
    source_ids = raw.get("source_ids")
    if not isinstance(covered, list) or any(not isinstance(value, str) or not value for value in covered):
        raise InputError("history_coverage covered_wafer_ids must be a list of wafer IDs.")
    if len(covered) != len(set(covered)):
        raise InputError("history_coverage covered_wafer_ids must not contain duplicates.")
    if not isinstance(source_ids, list) or not source_ids or any(source_id not in known_source_ids for source_id in source_ids):
        raise InputError("history_coverage must reference known source IDs.")
    covered_source_ids = raw.get("covered_source_ids")
    if (not isinstance(covered_source_ids, list) or not covered_source_ids
            or any(not isinstance(source_id, str) or source_id not in known_source_ids for source_id in covered_source_ids)):
        raise InputError("history_coverage must identify known source IDs whose process observations it covers.")
    if len(covered_source_ids) != len(set(covered_source_ids)):
        raise InputError("history_coverage covered_source_ids must not contain duplicates.")
    relation_id = _id(raw.get("relationship_id"), "history_coverage relationship_id")
    record_id = _id(raw.get("record_id"), "history_coverage record_id")
    if relation_id not in relationships:
        raise InputError("history_coverage has no approved source relationship.")
    relation_sources, relation_keys, rel_start, rel_end, _ = relationships[relation_id]
    required_coverage_keys = {"record_id", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids", "covered_source_ids", "population_kind", "source_authority_claim", "window_start", "window_end", "valid_until", "missing_record_ids"}
    relationship_scope_declared = set(source_ids).issubset(relation_sources) and required_coverage_keys.issubset(relation_keys)
    start = _dt(raw.get("window_start"), "history_coverage window_start")
    end = _dt(raw.get("window_end"), "history_coverage window_end")
    if end <= start or start < rel_start or end > rel_end:
        raise InputError("history_coverage window is outside its approved relationship effectivity.")
    missing = raw.get("missing_record_ids", [])
    if not isinstance(missing, list) or any(not isinstance(value, str) or not value for value in missing):
        raise InputError("history_coverage missing_record_ids must be a list of explicit record IDs.")
    by_wafer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_wafer[event["wafer_id"]].append(event)
    observed_sources = {
        event["source_id"] for wafer in covered for event in by_wafer.get(wafer, [])
        if event.get("source_id")
    }
    covers_events = all(
        start <= event["_low"] and event["_high"] < end
        for wafer in covered for event in by_wafer.get(wafer, [])
    )
    required_observation_keys = {"wafer_id", "step_instance_id", "timestamp"}
    observations_linked = observed_sources.issubset(set(covered_source_ids))
    observation_relationships_cover_window = all(
        any(
            source_id in relation_sources
            and required_observation_keys.issubset(keys)
            and relation_start <= start and end <= relation_end
            for relation_sources, keys, relation_start, relation_end, _relation in relationships.values()
        )
        for source_id in covered_source_ids
    )
    required_operations = {
        event.get("operation") for wafer in covered for event in by_wafer.get(wafer, [])
        if event.get("operation") and start <= event["_low"] and event["_high"] < end
    }
    required_lots = {
        event.get("lot_id") for wafer in covered for event in by_wafer.get(wafer, [])
        if event.get("lot_id") and start <= event["_low"] and event["_high"] < end
    }
    if not relationship_scope_declared:
        level, reason = "PARTIAL", "The approved history relationship does not declare every completeness scope and provenance field."
    elif complete and missing:
        level, reason = "CONTRADICTORY", "The source asserts complete history while listing missing process records."
    elif not complete or not covers_events or not observations_linked or not observation_relationships_cover_window:
        level, reason = "PARTIAL", "History coverage has known gaps, omits an observed source, or lacks an effective observation relationship."
    else:
        level, reason = _coverage_level(
            {"coverage": raw}, set(covered), start, end, known_source_ids, relationships,
            set(observed_sources), required_observation_keys, required_operations, required_lots,
        )
    accepted_complete = level == "SOURCE_VERIFIED"
    raw_source_ids = raw.get("source_ids", [])
    raw_lot_ids = raw.get("covered_lot_ids", [])
    raw_operations = raw.get("covered_operation_ids", [])
    authority = None
    if level == "SOURCE_VERIFIED":
        authority = _coverage_authorization(
            raw, relation_id, raw_source_ids, covered_source_ids, covered, raw_lot_ids, raw_operations,
            start.isoformat(), end.isoformat(), _dt(raw.get("valid_until"), "history_coverage valid_until").isoformat(),
        )
    return {
        "status": level,
        "coverage_evidence_level": level,
        "complete_assertion": complete,
        "accepted_for_history": accepted_complete,
        "covered_wafer_ids": sorted(set(covered)),
        "covered_lot_ids": sorted(set(raw_lot_ids)) if isinstance(raw_lot_ids, list) else [],
        "covered_operation_ids": sorted(set(raw_operations)) if isinstance(raw_operations, list) else [],
        "covered_source_ids": sorted(set(covered_source_ids)),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "source_references": [{"source_id": source_id, "relationship_id": relation_id, "record_id": record_id} for source_id in sorted(set(source_ids))],
        "missing_record_ids": sorted(set(missing)),
        "population_kind": raw.get("population_kind"),
        "source_authority_claim": raw.get("source_authority_claim"),
        "source_authority": authority,
        "record_type": "SOURCE_AUTHORIZED_HISTORY_COVERAGE" if authority else "CALLER_ASSERTED_HISTORY_COVERAGE",
        "assessment": reason,
    }


def _coverage(
    data: dict[str, Any], population: set[str], start: datetime, end: datetime,
    known_source_ids: set[str], relationships: dict[str, Any],
    required_source_ids: set[str] | None = None,
    observation_keys: set[str] | None = None,
    event_scope_index: dict[str, tuple[frozenset[str], frozenset[str]]] | None = None,
    coverage_scope_index: dict[str, tuple[bool, frozenset[str]]] | None = None,
) -> tuple[str, str]:
    coverage = data.get("coverage")
    raw_events = data.get("events", [])
    operations = set()
    lots = set()
    if event_scope_index is not None:
        for wafer_id in population:
            operations.update(event_scope_index.get(wafer_id, (frozenset(), frozenset()))[0])
            lots.update(event_scope_index.get(wafer_id, (frozenset(), frozenset()))[1])
    elif isinstance(raw_events, list):
        for row in raw_events:
            if not isinstance(row, dict) or row.get("wafer_id") not in population:
                continue
            if isinstance(row.get("operation"), str):
                operations.add(row["operation"])
            if isinstance(row.get("lot_id"), str):
                lots.add(row["lot_id"])
    return _coverage_level(
        data, population, start, end, known_source_ids, relationships,
        required_source_ids, observation_keys, operations, lots, coverage_scope_index,
    )


def _coverage_evidence(data: dict[str, Any], coverage_level: str, coverage_reason: str) -> dict[str, Any]:
    raw = data.get("coverage")
    if not isinstance(raw, dict):
        raw = {}
    source_ids = raw.get("source_ids", [])
    covered = raw.get("covered_wafer_ids", [])
    covered_lots = raw.get("covered_lot_ids", [])
    operations = raw.get("covered_operation_ids", [])
    if not isinstance(source_ids, list):
        source_ids = []
    if not isinstance(covered, list):
        covered = []
    authority = None
    if coverage_level == "SOURCE_VERIFIED":
        authority = _coverage_authorization(
            raw, raw.get("relationship_id"), source_ids, raw.get("covered_source_ids", []), covered,
            covered_lots if isinstance(covered_lots, list) else [],
            operations if isinstance(operations, list) else [],
            _dt(raw.get("window_start"), "coverage window_start").isoformat(),
            _dt(raw.get("window_end"), "coverage window_end").isoformat(),
            _dt(raw.get("valid_until"), "coverage valid_until").isoformat(),
        )
    return {
        "record_type": "SOURCE_AUTHORIZED_COVERAGE" if coverage_level == "SOURCE_VERIFIED" else "CALLER_ASSERTED_COVERAGE",
        "coverage_evidence_level": coverage_level,
        "complete_assertion": raw.get("complete") is True,
        "covered_wafer_ids": sorted({value for value in covered if isinstance(value, str) and value}),
        "covered_lot_ids": sorted({value for value in covered_lots if isinstance(value, str) and value}) if isinstance(covered_lots, list) else [],
        "covered_operation_ids": sorted({value for value in operations if isinstance(value, str) and value}) if isinstance(operations, list) else [],
        "population_kind": raw.get("population_kind"),
        "source_authority_claim": raw.get("source_authority_claim"),
        "source_ids": sorted({value for value in source_ids if isinstance(value, str) and value}),
        "covered_source_ids": sorted({value for value in raw.get("covered_source_ids", []) if isinstance(value, str) and value}) if isinstance(raw.get("covered_source_ids", []), list) else [],
        "relationship_id": raw.get("relationship_id") if isinstance(raw.get("relationship_id"), str) else None,
        "record_id": raw.get("record_id") if isinstance(raw.get("record_id"), str) else None,
        "window_start": raw.get("window_start") if isinstance(raw.get("window_start"), str) else None,
        "window_end": raw.get("window_end") if isinstance(raw.get("window_end"), str) else None,
        "missing_record_ids": sorted({value for value in raw.get("missing_record_ids", []) if isinstance(value, str) and value}) if isinstance(raw.get("missing_record_ids", []), list) else [],
        "accepted_for_query": coverage_level == "SOURCE_VERIFIED",
        "authority": authority,
        "assessment": coverage_reason,
    }


def _observation_sources(
    events: list[dict[str, Any]], population: set[str], start: datetime, end: datetime,
    relationships: dict[str, Any], observation_keys: set[str],
) -> set[str]:
    source_ids = {
        event["source_id"] for event in events
        if event["wafer_id"] in population and event.get("source_id")
    }
    for relation_sources, relation_keys, effective_start, effective_end, _relation in relationships.values():
        if (observation_keys.issubset(relation_keys) and effective_start < end and effective_end > start):
            source_ids.update(relation_sources)
    return source_ids


def _verified_condition_events(data: dict[str, Any], known_source_ids: set[str], relationships: dict[str, Any]) -> list[dict[str, Any]]:
    raw_events = data.get("condition_events", [])
    if not isinstance(raw_events, list) or len(raw_events) > MAX_EVENTS:
        raise InputError(f"condition_events must be a list with at most {MAX_EVENTS} records.")
    sources = {item["id"]: item for item in data.get("sources", []) if isinstance(item, dict) and item.get("id") in known_source_ids}
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_events):
        _check_cancelled()
        if not isinstance(item, dict):
            raise InputError(f"Condition event {index + 1} must be an object.")
        if item.get("approved_relationship") is not True:
            raise InputError(f"Condition event {index + 1} has no approved relationship reference.")
        event_id = _id(item.get("condition_event_id"), f"condition event {index + 1} ID")
        condition_type = item.get("condition_type")
        if condition_type not in {"PROCESS", "MAINTENANCE", "CHANGE"}:
            raise InputError(f"Condition event {event_id} has an unsupported source-declared condition type.")
        equipment_type = item.get("equipment_type")
        if equipment_type not in {"TOOL", "CHAMBER"}:
            raise InputError(f"Condition event {event_id} must identify exact TOOL or CHAMBER scope.")
        equipment_id = _id(item.get("equipment_id"), f"condition event {event_id} equipment_id")
        source_id = _id(item.get("source_id"), f"condition event {event_id} source_id")
        relation_id = _id(item.get("relationship_id"), f"condition event {event_id} relationship_id")
        if source_id not in known_source_ids or relation_id not in relationships:
            raise InputError(f"Condition event {event_id} has no approved source or relationship metadata.")
        relation_sources, keys, rel_start, rel_end, _ = relationships[relation_id]
        required_keys = {"condition_event_id", "condition_type", "equipment_type", "equipment_id", "event_start", "event_end"}
        if source_id not in relation_sources or not required_keys.issubset(keys):
            raise InputError(f"Condition event {event_id} relationship does not declare its source and required event fields.")
        start = _dt(item.get("event_start"), f"condition event {event_id} event_start")
        end = _dt(item.get("event_end"), f"condition event {event_id} event_end")
        if end <= start or start < rel_start or end > rel_end:
            raise InputError(f"Condition event {event_id} has invalid or unapproved event-time bounds.")
        uncertainty = _seconds(item.get("time_uncertainty_seconds", 0), f"Condition event {event_id} time_uncertainty_seconds")
        if item.get("recorded_at") is not None:
            _dt(item["recorded_at"], f"condition event {event_id} recorded_at")
        if item.get("source_hash") is not None and item["source_hash"] != sources[source_id]["source_hash"]:
            raise InputError(f"Condition event {event_id} source hash conflicts with its source reference.")
        if event_id in by_id:
            if item != by_id[event_id]["raw"]:
                raise InputError(f"Conflicting duplicate condition event ID {event_id}.")
            by_id[event_id]["duplicate_record_copies"] += 1
            continue
        by_id[event_id] = {
            "condition_event_id": event_id,
            "condition_type": condition_type,
            "equipment_type": equipment_type,
            "equipment_id": equipment_id,
            "event_start": item["event_start"],
            "event_end": item["event_end"],
            "time_uncertainty_seconds": uncertainty,
            "source_id": source_id,
            "relationship_id": relation_id,
            "source_hash": sources[source_id]["source_hash"],
            "recorded_at": item.get("recorded_at"),
            "_start": start,
            "_end": end,
            "_uncertainty": uncertainty,
            "duplicate_record_copies": 0,
            "raw": dict(item),
        }
    return [by_id[event_id] for event_id in sorted(by_id)]


def _target_wafer_ids(
    data: dict[str, Any],
    event_wafer_ids: set[str],
    outcomes: list[dict[str, Any]] | None = None,
    relationships: dict[str, Any] | None = None,
) -> list[str]:
    target = data.get("wafer_id")
    raw_targets = data.get("target_wafer_ids")
    raw_lot = data.get("target_lot_id")
    if raw_lot is not None:
        lot_id = _id(raw_lot, "target_lot_id")
        if outcomes is None or relationships is None:
            raise InputError("A target lot requires caller-supplied outcome and relationship records.")
        lot_outcomes = []
        for outcome in outcomes:
            _check_cancelled()
            if isinstance(outcome, dict) and outcome.get("lot_id") == lot_id:
                lot_outcomes.append(outcome)
        if not lot_outcomes:
            raise InputError(f"No caller-supplied outcome rows declare target lot {lot_id}.")
        derived_targets = []
        abnormal_present = False
        for outcome in lot_outcomes:
            _check_cancelled()
            wafer_id = _id(outcome.get("wafer_id"), "target lot outcome wafer_id")
            if outcome.get("label") not in ("ABNORMAL", "NORMAL"):
                raise InputError(f"Target lot outcome for wafer {wafer_id} must be ABNORMAL or NORMAL.")
            abnormal_present |= outcome.get("label") == "ABNORMAL"
            relation_id = outcome.get("relationship_id")
            if relation_id not in relationships:
                raise InputError(f"Target lot outcome for wafer {wafer_id} has no declared relationship.")
            relation_sources, keys, _start, _end, _relation = relationships[relation_id]
            if not {"wafer_id", "lot_id"}.issubset(keys) or outcome.get("source_id") not in relation_sources:
                raise InputError(
                    f"Outcome relationship {relation_id} does not declare the source, lot_id, and wafer_id needed for lot membership."
                )
            derived_targets.append(wafer_id)
        if not abnormal_present:
            raise InputError(f"Target lot {lot_id} has no caller-supplied ABNORMAL outcome.")
        if len(derived_targets) != len(set(derived_targets)):
            raise InputError(f"Target lot {lot_id} has repeated outcome rows for a wafer.")
        targets = sorted(derived_targets)
        if raw_targets is not None:
            if not isinstance(raw_targets, list) or not raw_targets:
                raise InputError("target_wafer_ids must be a non-empty list when supplied.")
            supplied_targets = [_id(value, "target_wafer_ids entry") for value in raw_targets]
            if len(supplied_targets) != len(set(supplied_targets)):
                raise InputError("target_wafer_ids must not contain duplicates.")
            if set(supplied_targets) != set(targets):
                raise InputError("target_wafer_ids must exactly match the wafer members in target lot outcome rows.")
        if target is not None and _id(target, "wafer_id") not in targets:
            raise InputError("wafer_id must be one of the target lot's declared outcome wafers.")
    elif raw_targets is None:
        targets = [] if target is None else [_id(target, "wafer_id")]
    else:
        if not isinstance(raw_targets, list) or not raw_targets:
            raise InputError("target_wafer_ids must be a non-empty list when supplied.")
        targets = [_id(value, "target_wafer_ids entry") for value in raw_targets]
        if len(targets) != len(set(targets)):
            raise InputError("target_wafer_ids must not contain duplicates.")
        if target is not None and _id(target, "wafer_id") not in targets:
            raise InputError("wafer_id must be one of the declared target_wafer_ids.")
    missing = sorted(set(targets) - event_wafer_ids)
    if missing:
        raise InputError("No verified events for target wafer(s): " + ", ".join(missing))
    return sorted(targets)


def _exposure_scope(spec: dict[str, Any]) -> tuple[str, str]:
    # A chamber remains the selected scope when tool_id is also supplied as
    # context. Tool-level exposure is explicit when chamber_id is absent.
    if spec.get("chamber_id") is not None:
        field = "chamber_id"
        scope_type = "CHAMBER"
    elif spec.get("tool_id") is not None:
        field = "tool_id"
        scope_type = "TOOL"
    else:
        raise InputError("suspected_exposure must declare chamber_id or tool_id.")
    return scope_type, _id(spec.get(field), f"suspected_exposure {field}")


def _exposure_condition_context(spec: dict[str, Any]) -> dict[str, str]:
    value = spec.get("condition_type")
    if value is None:
        return {"condition_type": "UNSPECIFIED", "evidence_status": "NOT_SUPPLIED"}
    if not isinstance(value, str) or value not in {"PROCESS", "MAINTENANCE", "CHANGE"}:
        raise InputError("suspected_exposure condition_type must be PROCESS, MAINTENANCE, or CHANGE.")
    return {"condition_type": value, "evidence_status": "CALLER_SUPPLIED_UNVERIFIED"}


def _event_window_relation(event: dict[str, Any], start: datetime, end: datetime) -> str:
    """Return definite, possible, or outside temporal overlap using event uncertainty."""
    if event["_start"] is not None:
        possible = event["_start_low"] < end and event["_end_high"] > start
        definite = event["_start_high"] < end and event["_end_low"] > start
        return "DEFINITE" if definite else "POSSIBLE" if possible else "OUTSIDE"
    if event["_low"] >= end or event["_high"] < start:
        return "OUTSIDE"
    if event["_low"] >= start and event["_high"] < end:
        return "DEFINITE"
    return "POSSIBLE"


def _exposure(
    data: dict[str, Any], events: list[dict[str, Any]], known_source_ids: set[str],
    target_wafer_ids: list[str], condition_events: list[dict[str, Any]],
    relationships: dict[str, Any],
) -> dict[str, Any] | None:
    spec = data.get("suspected_exposure")
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise InputError("suspected_exposure must be an object.")
    scope_type, scope_id = _exposure_scope(spec)
    scope_field = "chamber_id" if scope_type == "CHAMBER" else "tool_id"
    condition_context = _exposure_condition_context(spec)
    start = _dt(spec.get("start"), "suspected_exposure start")
    end = _dt(spec.get("end"), "suspected_exposure end")
    if end <= start:
        raise InputError("suspected_exposure end must be after start.")

    cohort = data.get("cohort")
    if cohort is None and target_wafer_ids:
        population = set(target_wafer_ids)
    elif cohort is None:
        population = {event["wafer_id"] for event in events}
    else:
        if not isinstance(cohort, list) or any(not isinstance(value, str) or not value for value in cohort):
            raise InputError("cohort must be a list of wafer IDs.")
        population = set(cohort)
    if not set(target_wafer_ids).issubset(population):
        raise InputError("Exposure cohort must include every target wafer.")
    if not population:
        raise InputError("Exposure population is empty.")

    exact = set()
    potentially_exposed = set()
    relationship_unknown = set()
    evidence = []
    for event in events:
        _check_cancelled()
        if event["wafer_id"] not in population:
            continue
        temporal_match = _event_window_relation(event, start, end)
        if temporal_match == "OUTSIDE":
            continue
        event_scope = event.get(scope_field)
        _relation_sources, relation_keys, _relation_start, _relation_end, _relation = relationships[event["relationship_id"]]
        required_scope_fields = {"wafer_id", "step_instance_id", "timestamp", scope_field}
        if event.get("processing_start") is not None or event.get("processing_end") is not None:
            required_scope_fields.update(("processing_start", "processing_end"))
        scope_fields_verified = required_scope_fields.issubset(relation_keys)
        relationship_covers_time_uncertainty = (
            _relation_start <= event["_low"] and event["_high"] < _relation_end
        )
        if event["_start"] is not None:
            # Exposure may be established by actual processing bounds, so the
            # source relationship must cover their full independent uncertainty
            # interval as well as the event timestamp.
            relationship_covers_time_uncertainty = (
                relationship_covers_time_uncertainty
                and _relation_start <= event["_start_low"]
                and event["_end_high"] <= _relation_end
            )
        if not scope_fields_verified:
            relationship_unknown.add(event["wafer_id"])
            evidence.append({
                "wafer_id": event["wafer_id"], "step_instance_id": event["step_instance_id"],
                "classification": "SCOPE_OR_TIME_FIELD_NOT_APPROVED_BY_RELATIONSHIP",
                "source_id": event["source_id"], "relationship_id": event["relationship_id"],
                "timestamp_utc": event["_time"].isoformat(), "scope_type": scope_type,
                "scope_id": scope_id,
            })
        elif not relationship_covers_time_uncertainty:
            # A nominally valid row does not support an exact field/time join when
            # timestamp or actual processing uncertainty crosses relationship validity.
            relationship_unknown.add(event["wafer_id"])
            evidence.append({
                "wafer_id": event["wafer_id"], "step_instance_id": event["step_instance_id"],
                "classification": "SOURCE_RELATIONSHIP_EFFECTIVITY_UNCERTAIN",
                "source_id": event["source_id"], "relationship_id": event["relationship_id"],
                "timestamp": event["timestamp"], "timestamp_utc": event["_time"].isoformat(),
                "event_time_interval": [event["_low"].isoformat(), event["_high"].isoformat()],
                "processing_time_interval_uncertainty_bounds": (
                    [event["_start_low"].isoformat(), event["_end_high"].isoformat()]
                    if event["_start"] is not None else None
                ),
                "relationship_effective_interval": [_relation_start.isoformat(), _relation_end.isoformat()],
                "scope_type": scope_type, "scope_id": scope_id,
                "meaning": "The event intersects the suspected window, but the source relationship is not effective across the full event timestamp or actual-processing uncertainty interval; scope and nonmatch interpretation remain unknown.",
            })
        elif event_scope == scope_id and temporal_match == "DEFINITE":
            exact.add(event["wafer_id"])
            evidence.append({
                "wafer_id": event["wafer_id"], "step_instance_id": event["step_instance_id"],
                "classification": f"EXACT_{scope_type}_WINDOW_MATCH", "source_id": event["source_id"],
                "relationship_id": event["relationship_id"], "timestamp": event["timestamp"],
                "timestamp_utc": event["_time"].isoformat(),
                "processing_start": event.get("processing_start"), "processing_end": event.get("processing_end"),
                "processing_start_uncertainty_seconds": event.get("processing_start_uncertainty_seconds", 0),
                "processing_end_uncertainty_seconds": event.get("processing_end_uncertainty_seconds", 0),
                "scope_type": scope_type, "scope_id": scope_id,
            })
        elif event_scope == scope_id or event_scope is None:
            # Missing equipment assignment or an uncertain clock is only a possible match.
            potentially_exposed.add(event["wafer_id"])
            evidence.append({
                "wafer_id": event["wafer_id"], "step_instance_id": event["step_instance_id"],
                "classification": (
                    "TIME_BOUNDARY_UNCERTAIN" if event_scope == scope_id
                    else f"UNKNOWN_{scope_type}"
                ),
                "source_id": event["source_id"],
                "relationship_id": event["relationship_id"], "timestamp": event["timestamp"],
                "timestamp_utc": event["_time"].isoformat(),
                "processing_start": event.get("processing_start"), "processing_end": event.get("processing_end"),
                "processing_start_uncertainty_seconds": event.get("processing_start_uncertainty_seconds", 0),
                "processing_end_uncertainty_seconds": event.get("processing_end_uncertainty_seconds", 0),
                "scope_type": scope_type, "scope_id": scope_id,
            })

    observation_keys = {"wafer_id", "step_instance_id", "timestamp", scope_field}
    if any(event["wafer_id"] in population and
           (event.get("processing_start") is not None or event.get("processing_end") is not None)
           for event in events):
        observation_keys.update(("processing_start", "processing_end"))
    used_source_ids = _observation_sources(events, population, start, end, relationships, observation_keys)
    coverage_level, coverage_reason = _coverage(
        data, population, start, end, known_source_ids, relationships, used_source_ids, observation_keys,
    )
    coverage_ok = coverage_level == "SOURCE_VERIFIED"
    coverage_record = _coverage_evidence(data, coverage_level, coverage_reason)
    potentially_exposed -= exact
    unknown = ((population - exact - potentially_exposed if not coverage_ok else set()) | relationship_unknown) - exact
    potentially_exposed -= exact | unknown
    not_observed = population - exact - potentially_exposed - unknown
    asserted_not_observed = (
        population - exact - potentially_exposed - relationship_unknown
        if coverage_level == "ASSERTED_UNVERIFIED" else set()
    )

    condition_evidence = []
    matching_condition_count = 0
    for condition in condition_events:
        _check_cancelled()
        if condition["equipment_type"] != scope_type or condition["equipment_id"] != scope_id:
            continue
        matching_condition_count += 1
        uncertainty = timedelta(seconds=condition["_uncertainty"])
        low_start = condition["_start"] - uncertainty
        high_start = condition["_start"] + uncertainty
        low_end = condition["_end"] - uncertainty
        high_end = condition["_end"] + uncertainty
        if high_end <= start:
            temporal_context = "BEFORE_SUSPECTED_WINDOW"
        elif low_start >= end:
            temporal_context = "AFTER_SUSPECTED_WINDOW"
        elif high_start < end and low_end > start:
            temporal_context = "OVERLAPS_SUSPECTED_WINDOW"
        else:
            temporal_context = "BOUNDARY_TIMING_UNCERTAIN"
        condition_evidence.append({
            "condition_event_id": condition["condition_event_id"],
            "condition_type": condition["condition_type"],
            "matches_caller_condition_label": condition["condition_type"] == condition_context["condition_type"],
            "equipment_type": condition["equipment_type"],
            "equipment_id": condition["equipment_id"],
            "event_start": condition["event_start"],
            "event_end": condition["event_end"],
            "time_uncertainty_seconds": condition["time_uncertainty_seconds"],
            "temporal_context": temporal_context,
            "source_id": condition["source_id"],
            "relationship_id": condition["relationship_id"],
            "source_hash": condition["source_hash"],
            "recorded_at": condition.get("recorded_at"),
            "duplicate_record_copies_collapsed": condition["duplicate_record_copies"],
            "meaning": "Source-linked condition-event context only; temporal overlap does not establish exposure effect or root cause.",
        })
    if matching_condition_count:
        condition_status = "SOURCE_LINKED_EXACT_SCOPE_EVENTS_PRESENT"
    elif condition_events:
        condition_status = "NO_EXACT_SCOPE_CONDITION_EVENT_RECORD"
    else:
        condition_status = "NO_CONDITION_EVENT_RECORDS_SUPPLIED"
    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        scope_field: scope_id,
        "condition_context": condition_context,
        "window": {"start": spec["start"], "end": spec["end"]},
        "population": sorted(population),
        "definitely_exposed": sorted(exact),
        "potentially_exposed": sorted(potentially_exposed),
        "unknown": sorted(unknown),
        "not_observed_exposed": sorted(not_observed),
        "not_observed_exposed_under_unverified_coverage": sorted(asserted_not_observed),
        # Compatibility fields retained for consumers of evidence schema v1.
        "possibly_exposed": sorted(potentially_exposed | unknown),
        "verified_unexposed": sorted(not_observed),
        "coverage_complete": coverage_ok,
        "coverage_claim_structurally_complete": coverage_level in {"ASSERTED_UNVERIFIED", "SOURCE_VERIFIED"},
        "coverage_evidence_level": coverage_level,
        "coverage_reason": coverage_reason,
        "coverage_evidence": coverage_record,
        "condition_event_status": condition_status,
        "condition_event_evidence": condition_evidence,
        "evidence": sorted(evidence, key=lambda item: (item["wafer_id"], item["step_instance_id"])),
    }


def _outcomes_and_counterevidence(
    data: dict[str, Any], exposure: dict[str, Any] | None,
    events: list[dict[str, Any]], relationships: dict[str, Any], journey: dict[str, Any],
):
    outcomes = _bounded_outcomes(data)
    by_wafer = {}
    source_evidence = {}
    for item in outcomes:
        _check_cancelled()
        if not isinstance(item, dict):
            raise InputError("Each outcome must be an object.")
        if item.get("approved_relationship") is not True or not item.get("source_id") or not item.get("relationship_id"):
            raise InputError("Outcome rows require approved source and relationship provenance.")
        wafer = _id(item.get("wafer_id"), "outcome wafer_id")
        if item.get("label") not in ("ABNORMAL", "NORMAL"):
            raise InputError(f"Outcome for {wafer} must be ABNORMAL or NORMAL.")
        if wafer in by_wafer:
            raise InputError(f"Conflicting or repeated outcome for wafer {wafer}.")
        by_wafer[wafer] = item["label"]
        relation = relationships[item["relationship_id"]]
        product_id = item.get("product_id") if "product_id" in relation[1] else None
        source_evidence[wafer] = {
            "wafer_id": wafer,
            "label": item["label"],
            "timestamp": item["timestamp"],
            "source_id": item["source_id"],
            "relationship_id": item["relationship_id"],
            **({"lot_id": item["lot_id"]} if isinstance(item.get("lot_id"), str) else {}),
            **({"product_id": product_id} if isinstance(product_id, str) and product_id else {}),
        }
    if exposure is None:
        return []
    exposed = set(exposure["definitely_exposed"])
    potentially_exposed = set(exposure["potentially_exposed"])
    unknown = set(exposure["unknown"])
    not_observed = set(exposure["not_observed_exposed"])
    asserted_not_observed = set(exposure.get("not_observed_exposed_under_unverified_coverage", []))
    population = set(exposure["population"])
    abnormal_exposed = sorted(w for w, label in by_wafer.items() if label == "ABNORMAL" and w in exposed)
    normal_exposed = sorted(w for w, label in by_wafer.items() if label == "NORMAL" and w in exposed)
    abnormal_unexposed = sorted(w for w, label in by_wafer.items() if label == "ABNORMAL" and w in not_observed)
    normal_unexposed = sorted(w for w, label in by_wafer.items() if label == "NORMAL" and w in not_observed)
    abnormal_unobserved_asserted = sorted(w for w, label in by_wafer.items() if label == "ABNORMAL" and w in asserted_not_observed)
    normal_unobserved_asserted = sorted(w for w, label in by_wafer.items() if label == "NORMAL" and w in asserted_not_observed)
    potential_outcomes = sorted(w for w in by_wafer if w in potentially_exposed)
    unknown_outcomes_only = sorted(w for w in by_wafer if w in unknown)
    unknown_outcomes = sorted(set(potential_outcomes) | set(unknown_outcomes_only))
    missing_outcomes = sorted(population - set(by_wafer))
    outcome_evidence = []
    for wafer in sorted(set(by_wafer) & population):
        _check_cancelled()
        item = dict(source_evidence[wafer])
        if wafer in exposed:
            item["exposure_classification"] = "EXPOSED"
        elif wafer in potentially_exposed:
            item["exposure_classification"] = "POTENTIALLY_EXPOSED"
        elif wafer in unknown:
            item["exposure_classification"] = "UNKNOWN"
        else:
            item["exposure_classification"] = "NOT_OBSERVED_EXPOSED"
        outcome_evidence.append(item)
    journey_rows = journey.get("journeys", []) if isinstance(journey, dict) else []
    journey_by_wafer = {
        row["wafer_id"]: row for row in journey_rows
        if isinstance(row, dict) and isinstance(row.get("wafer_id"), str)
    }
    route_pattern_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for wafer in sorted(population & set(journey_by_wafer)):
        _check_cancelled()
        wafer_journey = journey_by_wafer[wafer]
        segments = wafer_journey.get("route_segments", [])
        route_context = []
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                step_ids = set(segment.get("step_instance_ids", []))
                segment_steps = [step for step in wafer_journey.get("steps", [])
                                 if isinstance(step, dict) and step.get("step_instance_id") in step_ids]
                route_context.append({
                    "route_id": segment.get("route_id"),
                    "route_version": segment.get("route_version"),
                    "observed_operations_excluding_explicit_rework": segment.get(
                        "observed_operations_excluding_explicit_rework", []
                    ),
                    "conformance_status": segment.get("status", wafer_journey.get("route_conformance")),
                    "route_definition_evidence": ([{
                        "source_id": segment["approved_route_source_id"],
                        "relationship_id": segment["approved_route_relationship_id"],
                        "route_id": segment.get("route_id"),
                        "route_version": segment.get("route_version"),
                    }] if segment.get("approved_route_source_id") and segment.get("approved_route_relationship_id") else []),
                    "process_step_evidence": [{
                        "wafer_id": wafer,
                        "step_instance_id": step.get("step_instance_id"),
                        "source_id": step.get("source_id"),
                        "relationship_id": step.get("relationship_id"),
                        "timestamp_utc": step.get("timestamp_utc"),
                    } for step in segment_steps],
                })
        signature = tuple((
            item.get("route_id"), item.get("route_version"),
            tuple(item["observed_operations_excluding_explicit_rework"])
            if isinstance(item.get("observed_operations_excluding_explicit_rework"), list) else (),
            item.get("conformance_status"),
        ) for item in route_context)
        conformance = wafer_journey.get("route_conformance", "UNKNOWN")
        history_status = wafer_journey.get("history_status", "UNKNOWN")
        key = (signature, conformance, history_status)
        group = route_pattern_groups.setdefault(key, {
            "route_segments": route_context,
            "route_conformance": conformance,
            "history_status": history_status,
            "wafer_ids": [],
            "abnormal_wafer_ids": [],
            "normal_wafer_ids": [],
            "wafer_ids_missing_outcome": [],
            "exposed_wafer_ids": [],
            "potentially_exposed_wafer_ids": [],
            "unknown_exposure_wafer_ids": [],
            "not_observed_exposed_wafer_ids": [],
        })
        group["wafer_ids"].append(wafer)
        label = by_wafer.get(wafer)
        if label == "ABNORMAL":
            group["abnormal_wafer_ids"].append(wafer)
        elif label == "NORMAL":
            group["normal_wafer_ids"].append(wafer)
        else:
            group["wafer_ids_missing_outcome"].append(wafer)
        for name, members in (
            ("exposed_wafer_ids", exposed),
            ("potentially_exposed_wafer_ids", potentially_exposed),
            ("unknown_exposure_wafer_ids", unknown),
            ("not_observed_exposed_wafer_ids", not_observed),
        ):
            if wafer in members:
                group[name].append(wafer)
    route_patterns = sorted(
        route_pattern_groups.values(),
        key=lambda item: (str(item["route_conformance"]), str(item["history_status"]), item["wafer_ids"]),
    )
    route_context = {
        "status": "DESCRIPTIVE_SOURCE_LINKED_ROUTE_CONTEXT" if route_patterns else "ROUTE_CONTEXT_NOT_AVAILABLE",
        "patterns": route_patterns,
        "wafers_without_event_history": sorted(population - set(journey_by_wafer)),
        "population_coverage": journey.get("route_population_summary", {}) if isinstance(journey, dict) else {},
        "statistical_association": {"status": "NOT_COMPUTED"},
        "causal_conclusion": {"status": "NOT_ESTABLISHED"},
        "interpretation": "Route and outcome patterns are descriptive review context. Route mismatch requires an approved effective definition and source-linked route coverage; missing history remains unknown and no route effect or cause is inferred.",
    }
    abnormal_without_exposure = sorted(set(abnormal_unexposed) | {w for w, label in by_wafer.items() if label == "ABNORMAL" and w in unknown})
    abnormal_without_observed_match = sorted(w for w, label in by_wafer.items() if label == "ABNORMAL" and w not in exposed)
    window_start = _dt(exposure["window"]["start"], "exposure window start")
    window_end = _dt(exposure["window"]["end"], "exposure window end")
    relevant_events = [
        event for event in events
        if event["wafer_id"] in population
        and _event_window_relation(event, window_start, window_end) != "OUTSIDE"
    ]
    equipment_by_wafer: dict[str, set[tuple[str, str]]] = defaultdict(set)
    unverified_equipment_context = []
    equipment_evidence_refs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    possible_equipment_by_scope: dict[tuple[str, str], set[str]] = defaultdict(set)
    unassigned_equipment_by_field: dict[str, set[str]] = defaultdict(set)
    unresolved_equipment_by_field: dict[str, set[str]] = defaultdict(set)
    for event in relevant_events:
        _check_cancelled()
        _, relation_keys, relation_start, relation_end, _ = relationships[event["relationship_id"]]
        source_time_covers_uncertainty = relation_start <= event["_low"] and event["_high"] < relation_end
        temporal_match = _event_window_relation(event, window_start, window_end)
        for field in ("tool_id", "chamber_id"):
            value = event.get(field)
            if not isinstance(value, str) or not value:
                if field in relation_keys and source_time_covers_uncertainty:
                    unassigned_equipment_by_field[field].add(event["wafer_id"])
                else:
                    unresolved_equipment_by_field[field].add(event["wafer_id"])
                continue
            if field not in relation_keys:
                reason = "FIELD_NOT_DECLARED_BY_SOURCE_RELATIONSHIP"
                unresolved_equipment_by_field[field].add(event["wafer_id"])
            elif not source_time_covers_uncertainty:
                reason = "SOURCE_RELATIONSHIP_EFFECTIVITY_UNCERTAIN"
                unresolved_equipment_by_field[field].add(event["wafer_id"])
            elif temporal_match != "DEFINITE":
                reason = "EVENT_WINDOW_OVERLAP_UNCERTAIN"
                possible_equipment_by_scope[(field, value)].add(event["wafer_id"])
            else:
                equipment_by_wafer[event["wafer_id"]].add((field, value))
                equipment_evidence_refs[(field, value)].append({
                    "wafer_id": event["wafer_id"],
                    "step_instance_id": event["step_instance_id"],
                    "source_id": event["source_id"],
                    "relationship_id": event["relationship_id"],
                    "timestamp_utc": event["_time"].isoformat(),
                })
                continue
            unverified_equipment_context.append({
                "wafer_id": event["wafer_id"],
                "step_instance_id": event["step_instance_id"],
                "equipment_field": field,
                "equipment_id": value,
                "classification": reason,
                "source_id": event["source_id"],
                "relationship_id": event["relationship_id"],
                "event_time_interval": [event["_low"].isoformat(), event["_high"].isoformat()],
            })
    equipment_by_label = {}
    for label in ("ABNORMAL", "NORMAL"):
        wafers = {wafer for wafer, outcome in by_wafer.items() if outcome == label}
        equipment_by_label[label] = {
            "tool_ids": sorted({value for wafer in wafers for field, value in equipment_by_wafer.get(wafer, set()) if field == "tool_id"}),
            "chamber_ids": sorted({value for wafer in wafers for field, value in equipment_by_wafer.get(wafer, set()) if field == "chamber_id"}),
        }
    product_rows = [row for row in outcome_evidence if row.get("product_id")]
    product_strata = defaultdict(lambda: defaultdict(list))
    for row in product_rows:
        _check_cancelled()
        product_strata[row["product_id"]][(row["label"], row["exposure_classification"])].append(row["wafer_id"])
    product_strata_output = {
        product: {f"{label}__{classification}": sorted(wafers) for (label, classification), wafers in sorted(groups.items())}
        for product, groups in sorted(product_strata.items())
    }
    time_strata = defaultdict(lambda: defaultdict(list))
    for row in outcome_evidence:
        _check_cancelled()
        day = _dt(row["timestamp"], "outcome timestamp").date().isoformat()
        time_strata[day][(row["label"], row["exposure_classification"])].append(row["wafer_id"])
    time_strata_output = {
        day: {f"{label}__{classification}": sorted(wafers) for (label, classification), wafers in sorted(groups.items())}
        for day, groups in sorted(time_strata.items())
    }
    exposure_start = _dt(exposure["window"]["start"], "exposure window start")
    exposure_end = _dt(exposure["window"]["end"], "exposure window end")
    known_source_ids = {
        source_id for relation_sources, _keys, _start, _end, _relation in relationships.values()
        for source_id in relation_sources
    }
    equipment_field_coverage = {}
    primary_scope_field = "chamber_id" if exposure["scope_type"] == "CHAMBER" else "tool_id"
    for field in ("tool_id", "chamber_id"):
        observation_keys = {"wafer_id", "step_instance_id", "timestamp", field}
        if any(event["wafer_id"] in population and
               (event.get("processing_start") is not None or event.get("processing_end") is not None)
               for event in events):
            observation_keys.update(("processing_start", "processing_end"))
        if field == primary_scope_field:
            level, reason = exposure["coverage_evidence_level"], exposure["coverage_reason"]
        else:
            source_ids = _observation_sources(events, population, exposure_start, exposure_end, relationships, observation_keys)
            level, reason = _coverage(
                data, population, exposure_start, exposure_end, known_source_ids,
                relationships, source_ids, observation_keys,
            )
        equipment_field_coverage[field] = (level, reason)
    primary_scope = (primary_scope_field, exposure["scope_id"])
    alternative_equipment_hypotheses = []
    for field, equipment_id in sorted(equipment_evidence_refs):
        if (field, equipment_id) == primary_scope:
            continue
        exact_wafers = {ref["wafer_id"] for ref in equipment_evidence_refs[(field, equipment_id)]}
        possible_wafers = (
            possible_equipment_by_scope.get((field, equipment_id), set())
            | unassigned_equipment_by_field[field]
        ) - exact_wafers
        mapping_unknown = unresolved_equipment_by_field[field] - exact_wafers - possible_wafers
        coverage_level, coverage_reason = equipment_field_coverage[field]
        coverage_accepted = coverage_level == "SOURCE_VERIFIED"
        unknown_wafers = (
            mapping_unknown
            if coverage_accepted else population - exact_wafers - possible_wafers
        )
        not_observed_wafers = (
            population - exact_wafers - possible_wafers - mapping_unknown
            if coverage_accepted else set()
        )
        asserted_not_observed_wafers = (
            population - exact_wafers - possible_wafers - mapping_unknown
            if coverage_level == "ASSERTED_UNVERIFIED" else set()
        )
        observed_abnormal = sorted(wafer for wafer in exact_wafers if by_wafer.get(wafer) == "ABNORMAL")
        observed_normal = sorted(wafer for wafer in exact_wafers if by_wafer.get(wafer) == "NORMAL")
        alternative_equipment_hypotheses.append({
            "category": "ALTERNATIVE_EQUIPMENT_PATTERN",
            "status": "DESCRIPTIVE_CANDIDATE_ONLY",
            "equipment_field": field,
            "equipment_type": "CHAMBER" if field == "chamber_id" else "TOOL",
            "equipment_id": equipment_id,
            "observation_event_refs": sorted(
                equipment_evidence_refs[(field, equipment_id)],
                key=lambda ref: (ref["wafer_id"], ref["timestamp_utc"], ref["step_instance_id"]),
            ),
            "abnormal_wafers_with_observed_exact_event": observed_abnormal,
            "normal_wafers_with_observed_exact_event": observed_normal,
            "abnormal_wafers_without_observed_exact_event": sorted(
                wafer for wafer in not_observed_wafers if by_wafer.get(wafer) == "ABNORMAL"
            ),
            "normal_wafers_without_observed_exact_event": sorted(
                wafer for wafer in not_observed_wafers if by_wafer.get(wafer) == "NORMAL"
            ),
            "abnormal_wafers_not_observed_under_unverified_coverage": sorted(
                wafer for wafer in asserted_not_observed_wafers if by_wafer.get(wafer) == "ABNORMAL"
            ),
            "normal_wafers_not_observed_under_unverified_coverage": sorted(
                wafer for wafer in asserted_not_observed_wafers if by_wafer.get(wafer) == "NORMAL"
            ),
            "potentially_exposed_wafers": sorted(possible_wafers),
            "unknown_wafers": sorted(unknown_wafers),
            "population_wafers_missing_outcome": sorted(wafer for wafer in population if wafer not in by_wafer),
            "coverage": {
                "accepted_for_nonmatch_classification": coverage_accepted,
                "coverage_evidence_level": coverage_level,
                "assessment": coverage_reason,
                "record_type": "CALLER_DECLARED_SOURCE_LINKED_COVERAGE",
            },
            "statistical_association": {"status": "NOT_COMPUTED"},
            "causal_conclusion": {"status": "NOT_ESTABLISHED"},
            "meaning": "A separate source-linked equipment co-occurrence pattern inside the same time window; it is not a competing cause or causal finding.",
        })
    event_refs_by_wafer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in exposure["evidence"]:
        _check_cancelled()
        if record["classification"].startswith("EXACT_"):
            event_refs_by_wafer[record["wafer_id"]].append({
                "step_instance_id": record["step_instance_id"], "source_id": record["source_id"],
                "relationship_id": record["relationship_id"], "scope_type": record["scope_type"],
                "scope_id": record["scope_id"], "timestamp_utc": record["timestamp_utc"],
            })
    missing_or_ambiguous = {
        "outcomes_missing": missing_outcomes,
        "potentially_exposed_outcomes": potential_outcomes,
        "unknown_exposure_outcomes": unknown_outcomes_only,
        "population_unknown_exposure": sorted(unknown),
        "population_potential_exposure": sorted(potentially_exposed),
        "condition_event_status": exposure["condition_event_status"],
        "condition_event_evidence": exposure["condition_event_evidence"],
    }
    verification_candidates = []

    def add_verification_candidate(
        category, priority, operation, purpose, question, distinguishing_value,
        priority_basis, pairs, requested_keys=(), target_wafers=(), step_refs=(),
        missing_record_ids=(), coverage_record_ids=(), information_value_count=0,
        requested_keys_by_pair=None, material_relationship_refs=(),
    ):
        target_ids = sorted(set(target_wafers))
        valid_pairs = []
        for source_id, relationship_id in sorted(set(pairs)):
            relation = relationships.get(relationship_id)
            if relation and source_id in relation[0]:
                valid_pairs.append((source_id, relationship_id))
        if operation != "audit" and not valid_pairs:
            return
        declared_keys = set.intersection(*(
            set(relationships[relationship_id][1]) for _, relationship_id in valid_pairs
        )) if valid_pairs else set()
        selected_keys = sorted(set(requested_keys) & declared_keys)
        keys_by_pair = requested_keys_by_pair or {}
        step_ref_values = list(step_refs)
        references = []
        for source_id, relationship_id in valid_pairs:
            pair = (source_id, relationship_id)
            pair_keys = set(keys_by_pair.get(pair, requested_keys))
            declared_pair_keys = set(relationships[relationship_id][1])
            references.append({
                "source_id": source_id,
                "relationship_id": relationship_id,
                "requested_declared_keys": sorted(pair_keys & declared_pair_keys),
            })
        material_ref_tuples = sorted({
            (item.get("source_id"), item.get("relationship_id"), item.get("record_id"), item.get("relationship_type"))
            for item in material_relationship_refs
            if item.get("source_id") and item.get("relationship_id") and item.get("record_id")
        }, key=lambda item: (item[0], item[1], item[2], item[3] or ""))
        verification_candidates.append({
            "_priority": priority,
            "category": category,
            "logical_operation": operation,
            "purpose": purpose,
            "question": question,
            "distinguishing_value": distinguishing_value,
            "priority_basis": priority_basis,
            "source_relationships": references,
            "requested_declared_keys": selected_keys,
            "target_wafer_ids": target_ids,
            "step_instance_refs": [
                {"source_id": source_id, "relationship_id": relationship_id, "step_instance_id": step_id}
                for source_id, relationship_id, step_id in sorted(
                    { (item.get("source_id"), item.get("relationship_id"), item.get("step_instance_id"))
                      for item in step_ref_values if item.get("source_id") and item.get("relationship_id") and item.get("step_instance_id") },
                )
            ],
            "material_relationship_refs": [
                {"source_id": source_id, "relationship_id": relationship_id,
                 "record_id": record_id, "relationship_type": relationship_type}
                for source_id, relationship_id, record_id, relationship_type in material_ref_tuples
            ],
            "missing_record_ids": sorted(set(missing_record_ids)),
            "coverage_record_ids": sorted(set(coverage_record_ids)),
            "maximum_directly_addressed_members": max(0, information_value_count),
            "information_value_basis": (
                "This is an upper bound from currently unresolved cohort members, not a probability of resolution, effect estimate, or causal score."
            ),
            "review_factors": {
                "dependency_priority": priority,
                "affected_wafer_count": len(target_ids),
                "step_instance_ref_count": len({
                    (item.get("source_id"), item.get("relationship_id"), item.get("step_instance_id"))
                    for item in step_ref_values
                    if item.get("source_id") and item.get("relationship_id") and item.get("step_instance_id")
                }),
                "source_relationship_pair_count": len(valid_pairs),
                "bounded_read_request_count_proxy": len(valid_pairs) if operation == "read_bounded" else 0,
                "coverage_evidence_level": exposure.get("coverage_evidence_level", "UNKNOWN"),
                "negative_evidence_interpretation_risk": (
                    "HIGH" if exposure.get("coverage_evidence_level") != "SOURCE_VERIFIED"
                    else "SCOPE_LIMITED"
                ),
                "coverage_risk_basis": (
                    "Incomplete, asserted, unknown, or contradictory coverage means a missing row cannot prove nonexposure."
                    if exposure.get("coverage_evidence_level") != "SOURCE_VERIFIED"
                    else "Absence applies only within the verified population, operation, source, and time scope."
                ),
                "distinguishing_capacity": distinguishing_value,
                "cost_limit": "Pair count is a bounded-request-count proxy, not measured query latency or a cost estimate.",
            },
            "authorization_status": "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER",
            "proposed_not_executed": True,
        })

    coverage = exposure.get("coverage_evidence") or {}
    if exposure.get("coverage_evidence_level") != "SOURCE_VERIFIED":
        coverage_pairs = {
            (source_id, coverage.get("relationship_id"))
            for source_id in coverage.get("source_ids", [])
            if isinstance(source_id, str) and isinstance(coverage.get("relationship_id"), str)
        }
        unobserved_without_event = unknown - {row.get("wafer_id") for row in exposure.get("evidence", [])}
        add_verification_candidate(
            "EXPOSURE_COVERAGE", 0, "read_bounded",
            "Reconcile the exposure coverage record with its named missing records before interpreting nonmatches.",
            "Does the exact source, population, operation scope, and time window support complete observation coverage?",
            "A source-verified resolution could distinguish truly observed nonmatches from population members whose process records are absent; it cannot establish a causal effect.",
            f"Coverage is {exposure.get('coverage_evidence_level', 'UNKNOWN')} and currently limits negative evidence for {len(unobserved_without_event)} members.",
            coverage_pairs,
            requested_keys=("record_id", "window_start", "window_end", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids", "covered_source_ids", "missing_record_ids"),
            target_wafers=unobserved_without_event,
            missing_record_ids=coverage.get("missing_record_ids", []),
            coverage_record_ids=([coverage["record_id"]] if coverage.get("record_id") else []),
            information_value_count=len(unobserved_without_event),
        )

    lot_conflict_wafers = set()
    lot_conflict_pairs = set()
    lot_conflict_keys_by_pair = {}
    lot_conflict_step_refs = []
    lot_conflict_material_refs = []
    for wafer_journey in journey.get("journeys", []):
        _check_cancelled()
        edges_by_id = {
            edge.get("record_id"): edge
            for edge in wafer_journey.get("material_relationships", [])
            if edge.get("record_id")
        }
        for step in wafer_journey.get("steps", []):
            if step.get("membership_state") != "CONFLICTS_WITH_EVENT_ROW_LOT_ID":
                continue
            lot_conflict_wafers.add(wafer_journey["wafer_id"])
            process_pair = (step.get("source_id"), step.get("relationship_id"))
            if all(process_pair):
                lot_conflict_pairs.add(process_pair)
                lot_conflict_keys_by_pair[process_pair] = (
                    "wafer_id", "step_instance_id", "lot_id", "timestamp", "time_uncertainty_seconds",
                )
            lot_conflict_step_refs.append(step)
            for seed in (step.get("lot_lineage") or {}).get("seeds", []):
                for provenance in seed.get("provenance", []):
                    record_id = provenance.get("material_relationship_id")
                    edge = edges_by_id.get(record_id)
                    if not edge or edge.get("relationship_type") != "LOT_MEMBERSHIP":
                        continue
                    edge_provenance = edge.get("provenance") or {}
                    source_id = edge.get("source_id") or edge_provenance.get("source_id")
                    relationship_id = edge.get("relationship_id") or edge_provenance.get("relationship_id")
                    if not source_id or not relationship_id:
                        continue
                    material_pair = (source_id, relationship_id)
                    lot_conflict_pairs.add(material_pair)
                    lot_conflict_keys_by_pair[material_pair] = (
                        "from_entity_id", "from_entity_type", "to_entity_id", "to_entity_type",
                    )
                    lot_conflict_material_refs.append({
                        "source_id": source_id,
                        "relationship_id": relationship_id,
                        "record_id": record_id,
                        "relationship_type": edge.get("relationship_type"),
                    })
    if lot_conflict_wafers and lot_conflict_pairs:
        add_verification_candidate(
            "LOT_MEMBERSHIP_CONFLICT", 1, "read_bounded",
            "Reconcile process-row lot values with effective-dated wafer membership edges for the listed step instances.",
            "Does each process-step lot value agree with the source-linked wafer-to-lot membership effective at its event time?",
            "An authorized bounded read of the exact process rows and membership-edge records could resolve the lot association for these steps; it cannot establish an exposure effect or root cause.",
            f"{len(lot_conflict_step_refs)} process step instance(s) across {len(lot_conflict_wafers)} wafer(s) have event-row lot IDs that conflict with time-scoped membership.",
            lot_conflict_pairs,
            requested_keys_by_pair=lot_conflict_keys_by_pair,
            target_wafers=lot_conflict_wafers,
            step_refs=lot_conflict_step_refs,
            material_relationship_refs=lot_conflict_material_refs,
            information_value_count=len(lot_conflict_wafers),
        )

    evidence_by_class = defaultdict(list)
    for row in exposure.get("evidence", []):
        if row.get("classification") in {
            "UNKNOWN_CHAMBER", "UNKNOWN_TOOL", "TIME_BOUNDARY_UNCERTAIN",
            "SCOPE_OR_TIME_FIELD_NOT_APPROVED_BY_RELATIONSHIP",
            "SOURCE_RELATIONSHIP_EFFECTIVITY_UNCERTAIN",
        }:
            evidence_by_class[(row["classification"], row["source_id"], row["relationship_id"])].append(row)
    for (classification, source_id, relationship_id), rows in sorted(evidence_by_class.items()):
        target_field = "chamber_id" if classification == "UNKNOWN_CHAMBER" else "tool_id" if classification == "UNKNOWN_TOOL" else None
        time_fields = ("timestamp", "time_uncertainty_seconds")
        if target_field:
            operation = "read_bounded"
            requested = ("wafer_id", "step_instance_id", target_field, "timestamp")
            purpose = f"Verify the source-declared {target_field} assignment for the listed process-step instances."
            question = f"Do these records have a source-supported exact {target_field.replace('_id', '')} assignment?"
            distinguishing = "This could separate a match to the selected equipment from another or unknown equipment assignment; it does not establish an outcome mechanism or cause."
            priority = 1
            basis = f"{len(rows)} source-linked step records have an unknown exact equipment assignment."
        elif classification == "TIME_BOUNDARY_UNCERTAIN":
            operation = "read_bounded"
            requested = ("wafer_id", "step_instance_id", *time_fields)
            purpose = "Review source-supported event time and clock uncertainty for the listed boundary steps."
            question = "Can the event-time interval be resolved relative to the selected exposure window?"
            distinguishing = "This could resolve an exposure-window boundary classification for these records; it does not establish a causal effect."
            priority = 3
            basis = f"{len(rows)} source-linked step records have event-time uncertainty crossing the window boundary."
        else:
            operation = "semantics"
            requested = ()
            purpose = "Review whether the source relationship and semantic version support the equipment/time fields required for exact classification."
            question = "Are the source-declared equipment and time fields valid for this row grain and effective interval?"
            distinguishing = "This may determine whether a bounded read is valid; a caller-declared relationship alone is not authorization or company qualification."
            priority = 1
            basis = f"{len(rows)} source-linked records could not be classified under the declared relationship semantics."
        pairs = {(source_id, relationship_id)}
        add_verification_candidate(
            classification, priority, operation, purpose, question, distinguishing, basis, pairs,
            requested_keys=requested,
            target_wafers=(row["wafer_id"] for row in rows), step_refs=rows,
            information_value_count=len({row["wafer_id"] for row in rows}),
        )

    observed_outcome_pairs = {
        (row.get("source_id"), row.get("relationship_id"))
        for row in outcomes if row.get("source_id") and row.get("relationship_id")
    }
    if missing_outcomes:
        add_verification_candidate(
            "MISSING_OUTCOMES", 2, "read_bounded",
            "Check whether the source has an outcome row for the listed cohort members.",
            "Are source-linked outcome observations available for these population members?",
            "A returned row may complete outcome denominators and product/time strata; no label is presumed for a missing row.",
            f"{len(missing_outcomes)} cohort members currently lack an outcome record.",
            observed_outcome_pairs,
            requested_keys=("wafer_id", "label", "timestamp", "product_id", "lot_id"),
            target_wafers=missing_outcomes,
            information_value_count=len(missing_outcomes),
        )

    if not product_rows:
        product_pairs = observed_outcome_pairs
        add_verification_candidate(
            "PRODUCT_MIX_SEMANTICS", 4, "semantics",
            "Confirm whether product_id is meaningful and populated at the declared outcome row grain before product-mix comparison.",
            "Does the outcome source provide an approved, interpretable product field for these observations?",
            "If supported and populated, product strata could test whether product mix changes the descriptive comparison; this is not causal adjustment.",
            "Product-mix confounding is not assessed because source-linked outcome rows contain no usable product values.",
            product_pairs,
            requested_keys=("product_id",),
            target_wafers=(set(by_wafer) & population),
            information_value_count=len(set(by_wafer) & population),
        )

    verification_candidates.sort(key=lambda item: (
        item["_priority"], -item["maximum_directly_addressed_members"], item["category"],
        item["review_factors"]["bounded_read_request_count_proxy"],
    ))
    merged_candidates = []
    for candidate in verification_candidates:
        candidate_steps = {
            (item.get("source_id"), item.get("relationship_id"), item.get("step_instance_id"))
            for item in candidate["step_instance_refs"]
        }
        merge_target = None
        if (candidate["logical_operation"] == "read_bounded"
                and candidate["target_wafer_ids"] and candidate_steps
                and not candidate["missing_record_ids"]
                and not candidate["coverage_record_ids"]):
            for current in merged_candidates:
                current_steps = {
                    (item.get("source_id"), item.get("relationship_id"), item.get("step_instance_id"))
                    for item in current["step_instance_refs"]
                }
                if (current["logical_operation"] == "read_bounded"
                        and current["target_wafer_ids"] == candidate["target_wafer_ids"]
                        and current["target_wafer_ids"]
                        and candidate_steps & current_steps
                        and not current["missing_record_ids"]
                        and not current["coverage_record_ids"]):
                    merge_target = current
                    break
        if merge_target is None:
            merged_candidates.append(candidate)
            continue

        # One exact, bounded source-step read can answer overlapping questions.
        # Keep the union limited to already identified wafer/step refs and keep
        # every source relationship's key set separate.
        pair_keys = {
            (item["source_id"], item["relationship_id"]): set(item["requested_declared_keys"])
            for item in merge_target["source_relationships"]
        }
        for item in candidate["source_relationships"]:
            pair_keys.setdefault((item["source_id"], item["relationship_id"]), set()).update(
                item["requested_declared_keys"]
            )
        merge_target["source_relationships"] = [
            {"source_id": source_id, "relationship_id": relationship_id,
             "requested_declared_keys": sorted(keys)}
            for (source_id, relationship_id), keys in sorted(pair_keys.items())
        ]
        pair_declared_keys = [
            set(item["requested_declared_keys"])
            for item in merge_target["source_relationships"]
        ]
        merge_target["requested_declared_keys"] = sorted(
            set.intersection(*pair_declared_keys) if pair_declared_keys else set()
        )
        refs_by_key = {
            (item["source_id"], item["relationship_id"], item["step_instance_id"]): item
            for item in merge_target["step_instance_refs"]
        }
        refs_by_key.update({
            (item["source_id"], item["relationship_id"], item["step_instance_id"]): item
            for item in candidate["step_instance_refs"]
        })
        merge_target["step_instance_refs"] = [refs_by_key[key] for key in sorted(refs_by_key)]
        merge_target["review_factors"]["step_instance_ref_count"] = len(refs_by_key)
        merge_target["review_factors"]["source_relationship_pair_count"] = len(merge_target["source_relationships"])
        merge_target["review_factors"]["bounded_read_request_count_proxy"] = len(merge_target["source_relationships"])
        material_refs_by_key = {
            (item["source_id"], item["relationship_id"], item["record_id"]): item
            for item in merge_target["material_relationship_refs"]
        }
        material_refs_by_key.update({
            (item["source_id"], item["relationship_id"], item["record_id"]): item
            for item in candidate["material_relationship_refs"]
        })
        merge_target["material_relationship_refs"] = [
            material_refs_by_key[key] for key in sorted(material_refs_by_key)
        ]
        additional = merge_target.setdefault("covers_additional_checks", [])
        candidate_checks = [
            {"category": candidate["category"], "purpose": candidate["purpose"],
             "question": candidate["question"],
             "distinguishing_value": candidate["distinguishing_value"],
             "priority_basis": candidate["priority_basis"]},
            *candidate.get("covers_additional_checks", []),
        ]
        seen_categories = {item["category"] for item in additional}
        additional.extend(item for item in candidate_checks if item["category"] not in seen_categories)
        additional.sort(key=lambda item: (item["category"], item["question"]))
        merge_target["maximum_directly_addressed_members"] = max(
            merge_target["maximum_directly_addressed_members"],
            candidate["maximum_directly_addressed_members"],
        )
        merge_target["_priority"] = min(merge_target["_priority"], candidate["_priority"])
    verification_candidates = merged_candidates
    for rank, candidate in enumerate(verification_candidates, start=1):
        candidate["rank"] = rank
        candidate.pop("_priority", None)
    if verification_candidates:
        first_check = verification_candidates[0]
        next_authorized_verification = {
            "logical_operation": first_check["logical_operation"],
            "purpose": first_check["purpose"],
            "authorization_status": first_check["authorization_status"],
            "proposed_not_executed": True,
            "selection_rule": "Ranked by scientific dependency: coverage needed for negative evidence; exact equipment attribution and conflicting lot-identity links; outcome denominators; clock boundaries; then product-mix semantics. Within a category, explicitly affected members break ties, followed by category and exact relationship-read count. The relationship-read count is only a bounded request-count proxy; it is not query latency or information gain. Rank remains triage relevance, not causal probability.",
            "candidates": verification_candidates,
        }
    elif exposure["condition_event_status"] == "SOURCE_LINKED_EXACT_SCOPE_EVENTS_PRESENT":
        next_authorized_verification = {
            "logical_operation": "audit",
            "purpose": "Review the exact source, scope, and query trace supporting this descriptive investigation.",
            "authorization_status": "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER",
            "proposed_not_executed": True,
            "candidates": [],
        }
    else:
        next_authorized_verification = {
            "logical_operation": "semantics",
            "purpose": "Review the source and relationship semantics needed for the unresolved evidence scope.",
            "authorization_status": "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER",
            "proposed_not_executed": True,
            "candidates": [],
        }
    return [{
        "question": "Does the suspected exposure explain the observed outcome?",
        "abnormal_wafers_with_exact_exposure": abnormal_exposed,
        "normal_wafers_with_exact_exposure": normal_exposed,
        "abnormal_wafers_verified_unexposed": abnormal_unexposed,
        "normal_wafers_verified_unexposed": normal_unexposed,
        "abnormal_wafers_not_observed_under_unverified_coverage": abnormal_unobserved_asserted,
        "normal_wafers_not_observed_under_unverified_coverage": normal_unobserved_asserted,
        "coverage_evidence_level": exposure["coverage_evidence_level"],
        "abnormal_wafers_not_observed_exposed": abnormal_unexposed,
        "normal_wafers_not_observed_exposed": normal_unexposed,
        "abnormal_wafers_without_observed_exact_exposure": abnormal_without_observed_match,
        "abnormal_wafers_without_exposure_evidence": abnormal_without_exposure,
        "outcomes_with_potential_exposure": potential_outcomes,
        "outcomes_with_unknown_exposure_only": unknown_outcomes_only,
        "outcomes_with_unknown_exposure": unknown_outcomes,
        "population_wafers_missing_outcome": missing_outcomes,
        "outcome_evidence": outcome_evidence,
        "supporting_observations": [{
            "wafer_id": wafer, "outcome": "ABNORMAL", "exposure": "EXACT_SELECTED_EQUIPMENT_AND_WINDOW",
            "process_event_refs": event_refs_by_wafer.get(wafer, []),
            "interpretation": "Observed co-occurrence is descriptive support for review only.",
        } for wafer in abnormal_exposed],
        "contradicting_observations": {
            "normal_wafers_sharing_exact_exposure": [{"wafer_id": wafer, "process_event_refs": event_refs_by_wafer.get(wafer, [])} for wafer in normal_exposed],
            "abnormal_wafers_without_observed_exact_exposure": abnormal_without_observed_match,
        },
        "missing_or_ambiguous_evidence": missing_or_ambiguous,
        "confounders": {
            "selection_and_coverage": {
                "population_count": len(population), "outcome_count_in_population": len(set(by_wafer) & population),
                "missing_outcome_wafer_ids": missing_outcomes,
                "exposure_coverage_complete": exposure["coverage_complete"],
                "coverage_assessment": exposure["coverage_reason"],
                "status": "LIMITED_BY_MISSING_OUTCOMES_OR_COVERAGE" if missing_outcomes or not exposure["coverage_complete"] else "CALLER_DECLARED_COVERAGE_ONLY",
            },
            "product_mix": {
                "status": "SOURCE_LINKED_PRODUCT_STRATA_AVAILABLE" if product_rows else "NOT_ASSESSED_PRODUCT_FIELD_NOT_VERIFIED",
                "product_ids": sorted(product_strata_output), "strata": product_strata_output,
            },
            "time": {
                "status": "OUTCOME_DAY_STRATA_DESCRIPTIVE_ONLY" if outcome_evidence else "NOT_ASSESSED_NO_OUTCOME_ROWS",
                "utc_day_strata": time_strata_output,
                "limitation": "Outcome-day grouping does not adjust for time-varying selection or establish temporal causality.",
            },
            "equipment": {
                "status": (
                    "NOT_ASSESSED_NO_IN_WINDOW_EQUIPMENT_EVENTS" if not relevant_events
                    else "PARTIALLY_SOURCE_VERIFIED_EVENT_CONTEXT" if unverified_equipment_context and any(
                        item["tool_ids"] or item["chamber_ids"] for item in equipment_by_label.values()
                    )
                    else "NOT_ASSESSED_UNVERIFIED_EQUIPMENT_FIELDS" if unverified_equipment_context
                    else "SOURCE_LINKED_EVENT_CONTEXT_DESCRIPTIVE_ONLY"
                ),
                "equipment_by_outcome": equipment_by_label,
                "alternative_equipment_hypotheses": alternative_equipment_hypotheses,
                "unverified_or_ambiguous_event_fields": sorted(
                    unverified_equipment_context,
                    key=lambda item: (item["wafer_id"], item["step_instance_id"], item["equipment_field"]),
                ),
                "limitation": "Only equipment fields declared by source relationships and effective across event-time uncertainty during definite window overlap appear in the outcome strata. Other fields remain explicit unverified context; verified co-occurrence is descriptive and does not infer shared chamber membership or an effect.",
            },
            "route": route_context,
        },
        "statistical_association": {"status": "NOT_COMPUTED", "method": None, "reason": "The output is a deterministic cross-tabulation without a prespecified adjustment design."},
        "proposed_explanation": {
            "category": "PROPOSED_EXPLANATION",
            "status": "CANDIDATE_FOR_ENGINEER_REVIEW",
            "statement": "The selected equipment/time window is a candidate exposure to review against the observed outcome pattern.",
            "evidence_refs": sorted({ref["relationship_id"] for refs in event_refs_by_wafer.values() for ref in refs}),
        },
        "causal_conclusion": {"category": "CAUSAL_CONCLUSION", "status": "NOT_ESTABLISHED", "reason": "No causal design, intervention, or confounder adjustment has been validated."},
        "next_authorized_verification": next_authorized_verification,
        "interpretation": "This source-linked snapshot reports descriptive support, contradiction, missingness, and confounder context. It does not compute a statistical association or establish a causal conclusion.",
    }]


def _approved_expected_routes(
    data: dict[str, Any], known_source_ids: set[str], relationships: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    expected_routes = data.get("expected_routes", [])
    if not isinstance(expected_routes, list):
        raise InputError("expected_routes must be a list.")
    expected = {}
    for route in expected_routes:
        _check_cancelled()
        if not isinstance(route, dict) or route.get("approved") is not True:
            raise InputError("Expected route definitions must be explicit approved records.")
        route_id = _id(route.get("route_id"), "expected route_id")
        version = _id(route.get("route_version"), "expected route_version")
        source_id = _id(route.get("source_id"), "expected route source_id")
        relationship_id = _id(route.get("relationship_id"), "expected route relationship_id")
        operations = route.get("operations")
        if source_id not in known_source_ids:
            raise InputError(f"Expected route {route_id}/{version} has no approved source metadata.")
        if not isinstance(operations, list) or not operations or any(not isinstance(op, str) or not op for op in operations):
            raise InputError(f"Expected route {route_id}/{version} has no operation sequence.")
        key = (route_id, version)
        if key in expected:
            raise InputError(f"Duplicate expected route definition {route_id}/{version}.")
        allowed_sequences = [tuple(operations)]
        alternatives = route.get("allowed_sequences", [])
        if not isinstance(alternatives, list):
            raise InputError(f"Expected route {route_id}/{version} allowed_sequences must be a list.")
        if relationship_id not in relationships:
            raise InputError(f"Expected route {route_id}/{version} has no approved definition relationship.")
        route_sources, route_keys, route_start, route_end, _route_relationship = relationships[relationship_id]
        required_route_keys = {"route_id", "route_version", "approved", "operations"}
        if alternatives:
            required_route_keys.add("allowed_sequences")
        if source_id not in route_sources or not required_route_keys.issubset(route_keys):
            raise InputError(
                f"Expected route {route_id}/{version} definition relationship does not authorize its source and declared fields."
            )
        for sequence in alternatives:
            if not isinstance(sequence, list) or not sequence or any(not isinstance(op, str) or not op for op in sequence):
                raise InputError(f"Expected route {route_id}/{version} has an invalid approved route exception sequence.")
            allowed_sequences.append(tuple(sequence))
        unique_sequences = list(dict.fromkeys(allowed_sequences))
        expected[key] = {
            "allowed_sequences": tuple(unique_sequences), "source_id": source_id,
            "relationship_id": relationship_id,
            "effective_start": route_start, "effective_end": route_end,
        }
    return expected


def snapshot_preflight(data: Any, *, payload_bytes: int | None = None) -> dict[str, Any]:
    """Validate local snapshot provenance and declared limits before analysis."""
    try:
        if not isinstance(data, dict):
            raise InputError("Input must be a JSON object.")
        max_payload_bytes = 25 * 1024 * 1024
        if payload_bytes is not None and (not isinstance(payload_bytes, int) or isinstance(payload_bytes, bool) or payload_bytes < 0 or payload_bytes > max_payload_bytes):
            raise InputError(f"Request body must be between 0 and {max_payload_bytes} bytes.")
        events = _normalize_events(data)
        sources = _approved_sources(data)
        known_source_ids = {item["id"] for item in sources}
        unreferenced = sorted({event["source_id"] for event in events if event["source_id"] and event["source_id"] not in known_source_ids})
        if unreferenced:
            raise InputError("Events refer to source IDs without approved semantic metadata: " + ", ".join(unreferenced))
        relationships = _validate_relationships(data, events, known_source_ids)
        operation_definitions = _approved_operation_definitions(data, known_source_ids, relationships, events)
        material_relationships = _material_relationships(data, known_source_ids, relationships)
        history_coverage = _history_coverage(data, events, known_source_ids, relationships)
        condition_events = _verified_condition_events(data, known_source_ids, relationships)
        outcomes = _bounded_outcomes(data)
        _validate_outcome_provenance(data, outcomes, known_source_ids, relationships)
        expected = _approved_expected_routes(data, known_source_ids, relationships)

        event_wafer_ids = {event["wafer_id"] for event in events}
        target_wafer_ids = _target_wafer_ids(data, event_wafer_ids, outcomes, relationships)
        cohort = data.get("cohort")
        if cohort is not None and (not isinstance(cohort, list) or any(not isinstance(value, str) or not value for value in cohort)):
            raise InputError("cohort must be a list of wafer IDs.")
        population = set(cohort) if cohort is not None else (set(target_wafer_ids) if target_wafer_ids else event_wafer_ids)
        if not population:
            raise InputError("Analysis population is empty.")
        if not set(target_wafer_ids).issubset(population):
            raise InputError("Analysis cohort must include every target wafer.")

        exposure_scope = None
        exposure_spec = data.get("suspected_exposure")
        if exposure_spec is not None:
            if not isinstance(exposure_spec, dict):
                raise InputError("suspected_exposure must be an object.")
            scope_type, scope_id = _exposure_scope(exposure_spec)
            scope_field = "chamber_id" if scope_type == "CHAMBER" else "tool_id"
            condition_context = _exposure_condition_context(exposure_spec)
            start = _dt(exposure_spec.get("start"), "suspected_exposure start")
            end = _dt(exposure_spec.get("end"), "suspected_exposure end")
            if end <= start:
                raise InputError("suspected_exposure end must be after start.")
            observation_keys = {"wafer_id", "step_instance_id", "timestamp", scope_field}
            if any(event["wafer_id"] in population and
                   (event.get("processing_start") is not None or event.get("processing_end") is not None)
                   for event in events):
                observation_keys.update(("processing_start", "processing_end"))
            used_source_ids = _observation_sources(events, population, start, end, relationships, observation_keys)
            coverage_level, coverage_reason = _coverage(
                data, population, start, end, known_source_ids, relationships, used_source_ids, observation_keys,
            )
            coverage_ok = coverage_level == "SOURCE_VERIFIED"
            coverage_evidence = _coverage_evidence(data, coverage_level, coverage_reason)
            exposure_scope = {
                "scope_type": scope_type,
                "scope_id": scope_id,
                scope_field: scope_id,
                "condition_context": condition_context,
                "window_start_utc": start.isoformat(),
                "window_end_utc": end.isoformat(),
                "population": sorted(population),
                "target_wafer_ids": target_wafer_ids,
                "coverage_accepted": coverage_ok,
                "coverage_evidence_level": coverage_level,
                "coverage_assessment": coverage_reason,
                "coverage_record": coverage_evidence,
            }

        usage = defaultdict(lambda: {"event_rows": 0, "outcome_rows": 0})
        for event in events:
            usage[event["relationship_id"]]["event_rows"] += 1
        for outcome in outcomes:
            if isinstance(outcome, dict) and isinstance(outcome.get("relationship_id"), str):
                usage[outcome["relationship_id"]]["outcome_rows"] += 1
        return {
            "status": "READY_FOR_LOCAL_ANALYSIS",
            "mode": "SYNTHETIC_DEMO",
            "analysis_performed": False,
            "external_service_contacted": False,
            "limits": {
                "payload_bytes": payload_bytes,
                "max_payload_bytes": max_payload_bytes,
                "event_rows": len(events),
                "max_event_rows": MAX_EVENTS,
                "outcome_rows": len(outcomes),
                "max_outcome_rows": MAX_OUTCOMES,
                "within_limits": True,
            },
            "scope": {
                "target_wafer_id": data.get("wafer_id"),
                "target_wafer_ids": target_wafer_ids,
                "target_lot_id": data.get("target_lot_id"),
                "population": sorted(population),
                "event_wafer_count": len(event_wafer_ids),
                "event_count": len(events),
                "outcome_count": len(outcomes),
                "expected_route_count": len(expected),
                "operation_definition_count": len(operation_definitions),
                "material_relationship_count": len(material_relationships),
                "condition_event_count": len(condition_events),
                "history_coverage_status": history_coverage.get("status"),
                "exposure": exposure_scope,
            },
            "source_records": [{**source, "provenance_status": "CALLER_DECLARED_SYNTHETIC"} for source in sources],
            "relationships": [
                {**record, **usage[record["id"]]}
                for record in _relationship_evidence(relationships)
            ],
            "limitations": [
                "This preflight validates only the local snapshot's declared structure and limits; it does not authenticate sources or permissions.",
                "No source query or engineering analysis has run. The output remains synthetic caller-supplied evidence.",
                *(["Target lot membership is derived only from the supplied outcome rows and declared lot_id/wafer_id relationship; snapshot completeness for that lot is not established."] if data.get("target_lot_id") is not None else []),
            ],
        }
    except InputError as exc:
        return {
            "status": "REFUSED",
            "analysis_performed": False,
            "external_service_contacted": False,
            "reason": str(exc),
        }


def _route_analysis(data: dict[str, Any], events: list[dict[str, Any]], ordered: list[dict[str, Any]],
                    known_source_ids: set[str], order_groups: list[list[str]],
                    relationship_index: dict[str, Any], operation_definitions: dict[str, dict[str, Any]],
                    material_edges: list[dict[str, Any]], history_coverage: dict[str, Any]) -> dict[str, Any]:
    expected = _approved_expected_routes(data, known_source_ids, relationship_index)
    route_coverage = data.get("route_coverage", {})
    if not isinstance(route_coverage, dict):
        raise InputError("route_coverage must be an object.")
    route_event_scope_index = _coverage_event_index(events)
    route_coverage_scope_index = _coverage_scope_index(route_coverage)
    route_covered_source_ids = route_coverage.get("covered_source_ids", [])
    route_covered_wafer_ids = route_coverage.get("covered_wafer_ids", [])
    by_wafer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in ordered:
        _check_cancelled()
        by_wafer[event["wafer_id"]].append(event)
    route_coverage_ok_by_wafer = {}
    for wafer, rows in by_wafer.items():
        _check_cancelled()
        observation_keys = {"wafer_id", "step_instance_id", "timestamp"}
        if any(expected.get((event.get("route_id"), event.get("route_version"))) for event in rows):
            observation_keys.update(("route_id", "route_version"))
        window_start = min(event["_low"] for event in rows)
        window_end = max(event["_high"] for event in rows) + timedelta(microseconds=1)
        required_sources = _observation_sources(
            rows, {wafer}, window_start, window_end, relationship_index, observation_keys,
        )
        level, _reason = _coverage(
            {"coverage": route_coverage, "events": events}, {wafer}, window_start, window_end,
            known_source_ids, relationship_index, required_sources, observation_keys,
            route_event_scope_index, route_coverage_scope_index,
        )
        route_coverage_ok_by_wafer[wafer] = level == "SOURCE_VERIFIED"
    route_population_coverage_accepted = False
    route_population_coverage_level = "UNKNOWN"
    route_population_coverage_reason = "No source-linked route coverage population was declared."
    declared_route_population = []
    declared_route_population_set: set[str] = set()
    if (isinstance(route_covered_wafer_ids, list)
            and all(isinstance(value, str) and value for value in route_covered_wafer_ids)
            and len(route_covered_wafer_ids) == len(set(route_covered_wafer_ids))):
        declared_route_population = sorted(route_covered_wafer_ids)
        declared_route_population_set = set(declared_route_population)
        try:
            population_start = _dt(route_coverage.get("window_start"), "route_coverage window_start")
            population_end = _dt(route_coverage.get("window_end"), "route_coverage window_end")
            if (population_end > population_start and isinstance(route_covered_source_ids, list)
                    and route_covered_source_ids
                    and all(isinstance(value, str) and value for value in route_covered_source_ids)):
                observation_keys = {"wafer_id", "step_instance_id", "timestamp"}
                route_observed_sources = {
                    event["source_id"] for event in events
                    if event["wafer_id"] in declared_route_population_set
                }
                linked_sources_ok = route_observed_sources.issubset(set(route_covered_source_ids))
                route_definition_sources = {
                    expected[(event.get("route_id"), event.get("route_version"))]["source_id"]
                    for event in events
                    if event["wafer_id"] in declared_route_population_set
                    and (event.get("route_id"), event.get("route_version")) in expected
                }
                route_population_coverage_level, route_population_coverage_reason = _coverage(
                    {"coverage": route_coverage, "events": events}, declared_route_population_set,
                    population_start, population_end, known_source_ids, relationship_index,
                    route_observed_sources, observation_keys,
                    route_event_scope_index, route_coverage_scope_index,
                )
                route_population_coverage_accepted = route_population_coverage_level == "SOURCE_VERIFIED"
                if not linked_sources_ok:
                    route_population_coverage_accepted = False
                    route_population_coverage_level = "CONTRADICTORY"
                    route_population_coverage_reason = "Route coverage omits one or more observed process event sources."
                elif not route_definition_sources.issubset(set(route_covered_source_ids)):
                    route_population_coverage_accepted = False
                    route_population_coverage_level = "CONTRADICTORY"
                    route_population_coverage_reason = "Route coverage omits one or more approved expected-route definition sources."
            else:
                route_population_coverage_reason = "Route coverage has invalid window bounds or covered source IDs."
        except InputError:
            route_population_coverage_reason = "Route coverage has invalid timezone-aware window bounds."
    material_edges_by_entity: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    material_edge_times = {}
    for edge in material_edges:
        _check_cancelled()
        material_edge_times[edge["record_id"]] = (
            _dt(edge["effective_start"], "material relationship effective_start"),
            _dt(edge["effective_end"], "material relationship effective_end"),
        )
        for endpoint in (edge["from_entity"], edge["to_entity"]):
            material_edges_by_entity[(endpoint["type"], endpoint["id"])].append(edge)
    material_edge_indexes = _build_material_edge_interval_indexes(
        material_edges_by_entity, material_edge_times,
    )
    variants: dict[tuple[tuple[str, str, str], ...], list[str]] = defaultdict(list)
    uncertain_wafers = []
    journeys = []
    for wafer in sorted(by_wafer):
        _check_cancelled()
        rows = by_wafer[wafer]
        row_step_ids = {step["step_instance_id"] for step in rows}
        ambiguous_groups = [group for group in order_groups if row_step_ids.intersection(group)]
        if ambiguous_groups:
            uncertain_wafers.append({"wafer_id": wafer, "step_instance_groups": ambiguous_groups})
        else:
            route_signature = tuple((str(event.get("route_id") or ""), str(event.get("route_version") or ""), event["operation"]) for event in rows)
            variants[route_signature].append(wafer)

        by_step_ref = {(event["source_id"], event["step_instance_id"]): event for event in rows}
        rework_edges = []
        for event in rows:
            _check_cancelled()
            rework_ref = event.get("rework_of_step_instance_id")
            if rework_ref is None:
                continue
            prior_source = event.get("rework_of_source_id") or event["source_id"]
            prior = by_step_ref.get((prior_source, rework_ref))
            if prior is None or prior["operation"] != event["operation"] or prior["_time"] >= event["_time"]:
                raise InputError(f"Event {event['step_instance_id']} has an invalid explicit rework link.")
            identity_ref = event.get("identity_relationship_id")
            if prior_source != event["source_id"] and (identity_ref is None or identity_ref != prior.get("identity_relationship_id")):
                raise InputError(f"Cross-source rework link for step {event['step_instance_id']} lacks one approved identity relationship.")
            rework_edges.append({
                "relationship_type": "EXPLICIT_REWORK_REFERENCE",
                "from_step_instance": {"source_id": event["source_id"], "step_instance_id": event["step_instance_id"]},
                "to_step_instance": {"source_id": prior_source, "step_instance_id": rework_ref},
                "provenance": [
                    {"source_id": event["source_id"], "relationship_id": event["relationship_id"], "step_instance_id": event["step_instance_id"]},
                    {"source_id": prior["source_id"], "relationship_id": prior["relationship_id"], "step_instance_id": prior["step_instance_id"]},
                    *([{"identity_relationship_id": identity_ref}] if identity_ref else []),
                ],
                "meaning": "Explicit source-row rework reference; not inferred from repeated operation labels.",
            })

        route_segments = []
        if rows:
            current_key = (rows[0].get("route_id"), rows[0].get("route_version"))
            current_rows = []
            for event in rows:
                key = (event.get("route_id"), event.get("route_version"))
                if key != current_key and current_rows:
                    route_segments.append((current_key, current_rows))
                    current_key, current_rows = key, []
                current_rows.append(event)
            if current_rows:
                route_segments.append((current_key, current_rows))

        segment_results = []
        if not expected:
            conformance = "ORDER_UNCERTAIN" if ambiguous_groups else "NO_APPROVED_EXPECTED_ROUTE"
        elif ambiguous_groups:
            conformance = "ORDER_UNCERTAIN"
            for (route_id, route_version), segment_rows in route_segments:
                segment_results.append({
                    "route_id": route_id, "route_version": route_version,
                    "step_instance_ids": [event["step_instance_id"] for event in segment_rows],
                    "status": "ORDER_UNCERTAIN",
                })
        else:
            for (route_id, route_version), segment_rows in route_segments:
                segment_status = "ROUTE_IDENTITY_UNKNOWN"
                route_key = (route_id, route_version)
                route_definition = expected.get(route_key)
                observed = tuple(event["operation"] for event in segment_rows if not event.get("rework_of_step_instance_id"))
                route_fields_verified = all(
                    {"route_id", "route_version"}.issubset(relationship_index[event["relationship_id"]][1])
                    for event in segment_rows
                )
                if not route_fields_verified:
                    segment_status = "ROUTE_IDENTITY_UNVERIFIED"
                elif route_id is not None and route_version is not None and route_definition is not None:
                    route_definition_effective = all(
                        route_definition["effective_start"] <= event["_low"]
                        and event["_high"] < route_definition["effective_end"]
                        for event in segment_rows
                    )
                    if not route_definition_effective:
                        segment_status = "ROUTE_DEFINITION_EFFECTIVITY_UNCERTAIN"
                    elif (not route_coverage_ok_by_wafer.get(wafer, False) or
                            not isinstance(route_covered_source_ids, list) or
                            route_definition["source_id"] not in route_covered_source_ids):
                        segment_status = "COVERAGE_INCOMPLETE"
                    elif observed in route_definition["allowed_sequences"]:
                        segment_status = "EXPECTED_ROUTE_MATCH"
                    else:
                        segment_status = "EXPECTED_ROUTE_MISMATCH"
                elif route_id is not None and route_version is not None:
                    segment_status = "NO_APPROVED_EXPECTED_ROUTE"
                segment_results.append({
                    "route_id": route_id, "route_version": route_version,
                    "step_instance_ids": [event["step_instance_id"] for event in segment_rows],
                    "observed_operations_excluding_explicit_rework": list(observed),
                    "approved_allowed_sequences": [list(sequence) for sequence in (route_definition or {}).get("allowed_sequences", ())],
                    "approved_route_source_id": (route_definition or {}).get("source_id"),
                    "approved_route_relationship_id": (route_definition or {}).get("relationship_id"),
                    "approved_route_effective_start_utc": (route_definition or {}).get("effective_start").isoformat() if route_definition else None,
                    "approved_route_effective_end_utc": (route_definition or {}).get("effective_end").isoformat() if route_definition else None,
                    "status": segment_status,
                })
            statuses = {item["status"] for item in segment_results}
            if "ROUTE_IDENTITY_UNKNOWN" in statuses:
                conformance = "ROUTE_IDENTITY_UNKNOWN"
            elif "ROUTE_IDENTITY_UNVERIFIED" in statuses:
                conformance = "ROUTE_IDENTITY_UNVERIFIED"
            elif "COVERAGE_INCOMPLETE" in statuses:
                conformance = "COVERAGE_INCOMPLETE"
            elif "ROUTE_DEFINITION_EFFECTIVITY_UNCERTAIN" in statuses:
                conformance = "ROUTE_DEFINITION_EFFECTIVITY_UNCERTAIN"
            elif "EXPECTED_ROUTE_MISMATCH" in statuses:
                conformance = "EXPECTED_ROUTE_MISMATCH"
            elif "NO_APPROVED_EXPECTED_ROUTE" in statuses:
                conformance = "NO_APPROVED_EXPECTED_ROUTE"
            elif statuses and statuses == {"EXPECTED_ROUTE_MATCH"}:
                conformance = "EXPECTED_ROUTE_MATCH"
            else:
                conformance = "NO_APPROVED_EXPECTED_ROUTE"

        sequence_edges = []
        for prior, following in zip(rows, rows[1:]):
            _check_cancelled()
            if prior["_high"] >= following["_low"]:
                continue
            source_refs = [
                {"source_id": prior["source_id"], "relationship_id": prior["relationship_id"], "step_instance_id": prior["step_instance_id"]},
                {"source_id": following["source_id"], "relationship_id": following["relationship_id"], "step_instance_id": following["step_instance_id"]},
            ]
            identity_ref = following.get("identity_relationship_id") or prior.get("identity_relationship_id")
            if prior["source_id"] != following["source_id"] and identity_ref:
                source_refs.append({"identity_relationship_id": identity_ref})
            sequence_edges.append({
                "relationship_type": "OBSERVED_CHRONOLOGICAL_ADJACENCY",
                "from_step_instance": {"source_id": prior["source_id"], "step_instance_id": prior["step_instance_id"]},
                "to_step_instance": {"source_id": following["source_id"], "step_instance_id": following["step_instance_id"]},
                "ordering_basis": "non-overlapping timezone-normalized event-time uncertainty intervals",
                "ordering_margin_seconds": (following["_low"] - prior["_high"]).total_seconds(),
                "provenance": source_refs,
                "meaning": "Derived ordering of adjacent observed records; not a causal or recipe-transition claim.",
            })

        if any(group for group in ambiguous_groups):
            history_status = "AMBIGUOUS_CHRONOLOGY"
        elif history_coverage.get("status") in {"PARTIAL", "CONTRADICTORY"}:
            history_status = "INCOMPLETE"
        elif history_coverage.get("status") == "UNKNOWN" or wafer not in history_coverage.get("covered_wafer_ids", []):
            history_status = "COVERAGE_UNKNOWN"
        elif history_coverage.get("status") == "ASSERTED_UNVERIFIED":
            history_status = "COVERAGE_ASSERTED_UNVERIFIED"
        else:
            history_status = "SOURCE_VERIFIED_COMPLETE"

        steps = []
        for event in rows:
            _check_cancelled()
            contextual_edges = []
            contextual_edge_assessments = []
            event_lot = event.get("lot_id")
            _, event_relation_keys, event_relation_start, event_relation_end, _ = relationship_index[event["relationship_id"]]
            event_lot_declared = "lot_id" in event_relation_keys
            event_lot_relation_covers_uncertainty = (
                event_lot_declared
                and event_relation_start <= event["_low"]
                and event["_high"] < event_relation_end
            )
            touched_entities = [("wafer", wafer)]
            if event_lot is not None and event_lot_relation_covers_uncertainty:
                touched_entities.append(("lot", event_lot))
            candidate_edges = {
                edge["record_id"]: edge
                for entity in touched_entities
                for edge in _material_edges_intersecting_time(
                    material_edge_indexes.get(entity), event["_low"], event["_high"], material_edge_times,
                )
            }
            for edge_id in sorted(candidate_edges):
                edge = candidate_edges[edge_id]
                edge_start, edge_end = material_edge_times[edge_id]
                contextual_edges.append(edge_id)
                edge_is_definite = edge_start <= event["_low"] and event["_high"] < edge_end
                contextual_edge_assessments.append({
                    "record_id": edge_id,
                    "temporal_status": (
                        "EFFECTIVE_ACROSS_EVENT_TIME_UNCERTAINTY"
                        if edge_is_definite else "POSSIBLY_EFFECTIVE_DUE_TO_CLOCK_UNCERTAINTY"
                    ),
                })
            definition = operation_definitions.get(event.get("operation_definition_id"))
            membership_edges = [
                edge for edge in candidate_edges.values()
                if edge["relationship_type"] == "LOT_MEMBERSHIP"
                and edge["from_entity"]["type"] == "lot"
                and edge["to_entity"] == {"type": "wafer", "id": wafer}
                and edge["record_id"] in candidate_edges
            ]
            definite_membership_lots = sorted({
                edge["from_entity"]["id"] for edge in membership_edges
                if material_edge_times[edge["record_id"]][0] <= event["_low"]
                and event["_high"] < material_edge_times[edge["record_id"]][1]
            })
            possible_membership_lots = sorted({edge["from_entity"]["id"] for edge in membership_edges})
            if len(definite_membership_lots) > 1:
                membership_state = "AMBIGUOUS_MULTIPLE_TIME_SCOPED_MEMBERSHIPS"
            elif len(possible_membership_lots) > 1:
                membership_state = "TEMPORALLY_AMBIGUOUS_MEMBERSHIP"
            elif possible_membership_lots and not definite_membership_lots:
                membership_state = "TEMPORALLY_AMBIGUOUS_MEMBERSHIP"
            elif definite_membership_lots and event.get("lot_id") and definite_membership_lots[0] != event["lot_id"]:
                membership_state = "CONFLICTS_WITH_EVENT_ROW_LOT_ID"
            elif definite_membership_lots:
                membership_state = "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP"
            elif event_lot is not None and event_lot_declared and not event_lot_relation_covers_uncertainty:
                membership_state = "EVENT_LOT_RELATIONSHIP_TIME_AMBIGUOUS"
            elif event_lot is not None and "lot_id" in event_relation_keys:
                membership_state = "EVENT_ROW_ONLY"
            elif event_lot is not None:
                membership_state = "EVENT_LOT_FIELD_UNVERIFIED"
            else:
                membership_state = "UNKNOWN"
            lineage_seed_by_lot = {}
            lineage_evidence_gaps = []

            assessment_by_id = {
                item["record_id"]: item["temporal_status"]
                for item in contextual_edge_assessments
            }
            for edge in membership_edges:
                edge_status = assessment_by_id[edge["record_id"]]
                ambiguous_membership = (
                    len(possible_membership_lots) > 1
                    or len(definite_membership_lots) > 1
                    or edge_status != "EFFECTIVE_ACROSS_EVENT_TIME_UNCERTAINTY"
                )
                _add_lot_lineage_seed(
                    lineage_seed_by_lot,
                    edge["from_entity"]["id"],
                    "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP",
                    "POSSIBLE" if ambiguous_membership else "SOURCE_LINKED",
                    {
                        "material_relationship_id": edge["record_id"],
                        "source_id": edge["provenance"]["source_id"],
                        "relationship_id": edge["provenance"]["relationship_id"],
                        "temporal_status": edge_status,
                    },
                )

            if event_lot is not None:
                if "lot_id" not in event_relation_keys:
                    lineage_evidence_gaps.append({
                        "reason": "EVENT_LOT_FIELD_NOT_DECLARED_BY_SOURCE_RELATIONSHIP",
                        "source_id": event["source_id"],
                        "relationship_id": event["relationship_id"],
                        "required_key": "lot_id",
                    })
                elif (membership_state != "CONFLICTS_WITH_EVENT_ROW_LOT_ID"
                      and (not possible_membership_lots or event_lot in possible_membership_lots)):
                    ambiguous_membership = membership_state in {
                        "AMBIGUOUS_MULTIPLE_TIME_SCOPED_MEMBERSHIPS",
                        "TEMPORALLY_AMBIGUOUS_MEMBERSHIP",
                        "EVENT_LOT_RELATIONSHIP_TIME_AMBIGUOUS",
                    } or not event_lot_relation_covers_uncertainty
                    _add_lot_lineage_seed(
                        lineage_seed_by_lot,
                        event_lot,
                        "SOURCE_DECLARED_EVENT_LOT_ID",
                        "POSSIBLE" if ambiguous_membership else "SOURCE_LINKED",
                        {
                            "source_id": event["source_id"],
                            "relationship_id": event["relationship_id"],
                            "step_instance_id": event["step_instance_id"],
                            "declared_key": "lot_id",
                            "temporal_status": (
                                "EFFECTIVE_ACROSS_EVENT_TIME_UNCERTAINTY"
                                if event_lot_relation_covers_uncertainty
                                else "POSSIBLY_EFFECTIVE_DUE_TO_CLOCK_UNCERTAINTY"
                            ),
                        },
                    )
                else:
                    lineage_evidence_gaps.append({
                        "reason": "EVENT_LOT_ID_CONFLICTS_WITH_TIME_SCOPED_MEMBERSHIP",
                        "source_id": event["source_id"],
                        "relationship_id": event["relationship_id"],
                        "event_lot_id": event_lot,
                        "candidate_lot_ids": possible_membership_lots,
                    })
                if event_lot_declared and not event_lot_relation_covers_uncertainty:
                    lineage_evidence_gaps.append({
                        "reason": "EVENT_LOT_RELATIONSHIP_NOT_EFFECTIVE_ACROSS_FULL_TIME_UNCERTAINTY",
                        "source_id": event["source_id"],
                        "relationship_id": event["relationship_id"],
                        "event_time_interval": [event["_low"].isoformat(), event["_high"].isoformat()],
                        "relationship_effective_interval": [event_relation_start.isoformat(), event_relation_end.isoformat()],
                    })
            lineage_seeds = [lineage_seed_by_lot[key] for key in sorted(lineage_seed_by_lot)]
            lineage_paths, lineage_relationship_assessments = _trace_lot_lineage(
                lineage_seeds, event["_low"], event["_high"],
                material_edge_indexes, material_edge_times,
            )
            material_coverage = _material_lineage_coverage(
                data, event, lineage_seeds, lineage_paths, material_edges,
                known_source_ids, relationship_index,
            )
            if material_coverage["status"] != "CALLER_DECLARED_SOURCE_LINKED_COMPLETE":
                lineage_evidence_gaps.append({
                    "reason": "MATERIAL_RELATIONSHIP_COVERAGE_NOT_ESTABLISHED",
                    "assessment": material_coverage["assessment"],
                    "coverage_status": material_coverage["status"],
                })
            if not lineage_seeds:
                lineage_status = "NO_VERIFIED_LOT_SEED"
                if not lineage_evidence_gaps:
                    lineage_evidence_gaps.append({
                        "reason": "NO_SOURCE_LINKED_LOT_MEMBERSHIP_OR_DECLARED_EVENT_LOT_ID",
                        "required_evidence": "A time-scoped LOT_MEMBERSHIP edge or an event relationship declaring lot_id.",
                    })
            elif not lineage_paths:
                lineage_status = "NO_CONNECTED_SPLIT_MERGE_EDGE_OBSERVED"
                lineage_evidence_gaps.append({
                    "reason": "NO_CONNECTED_TIME_SCOPED_SPLIT_MERGE_EDGE_OBSERVED_IN_SNAPSHOT",
                    "seed_lot_ids": [seed["lot_id"] for seed in lineage_seeds],
                    "relationship_types_checked": ["SPLIT_FROM", "MERGED_FROM"],
                })
            else:
                lineage_status = "SOURCE_DECLARED_LINEAGE_PATHS_FOUND"
            ambiguous_with = next((group for group in ambiguous_groups if event["step_instance_id"] in group), [])
            steps.append({
                "step_instance_id": event["step_instance_id"],
                "step_instance_ref": {"source_id": event["source_id"], "step_instance_id": event["step_instance_id"]},
                "operation_definition_id": event.get("operation_definition_id"),
                "operation_definition_status": "SOURCE_LINKED_APPROVED" if definition else "DEFINITION_NOT_PROVIDED",
                "operation_definition_source_id": definition["source_id"] if definition else None,
                "operation": event["operation"],
                "timestamp": event["timestamp"],
                "timestamp_utc": event["_time"].isoformat(),
                "recorded_at": event.get("recorded_at"),
                "time_uncertainty_seconds": event["_time_uncertainty_seconds"],
                "order_uncertain_with": ambiguous_with,
                "route_id": event.get("route_id"),
                "route_version": event.get("route_version"),
                "lot_id_at_event": event.get("lot_id"),
                "membership_state": membership_state,
                "candidate_time_scoped_lot_ids": possible_membership_lots,
                "time_scoped_material_relationship_ids": contextual_edges,
                "time_scoped_material_relationship_assessments": contextual_edge_assessments,
                "lot_lineage": {
                    "status": lineage_status,
                    "seeds": lineage_seeds,
                    "paths": lineage_paths,
                    "relationship_assessments": lineage_relationship_assessments,
                    "material_relationship_coverage": material_coverage,
                    "missing_evidence": lineage_evidence_gaps,
                    "meaning": "Only source-declared lot-to-lot SPLIT_FROM and MERGED_FROM edges are traversed. LOT_MEMBERSHIP edges do not propagate through sibling wafers.",
                },
                "time_scoped_lot_lineage_relationship_ids": [
                    item["record_id"] for item in lineage_relationship_assessments
                ],
                "tool_id": event.get("tool_id"),
                "chamber_id": event.get("chamber_id"),
                "source_id": event["source_id"],
                "relationship_id": event.get("relationship_id"),
                "identity_relationship_id": event.get("identity_relationship_id"),
                "rework_of_step_instance_id": event.get("rework_of_step_instance_id"),
                "rework_of_source_id": event.get("rework_of_source_id") or (event["source_id"] if event.get("rework_of_step_instance_id") else None),
                "duplicate_record_copies_collapsed": event.get("duplicate_record_copies", 0),
            })
        journey_edge_ids = {
            edge_id
            for step in steps
            for edge_id in (
                step["time_scoped_material_relationship_ids"]
                + step["time_scoped_lot_lineage_relationship_ids"]
            )
        }
        journey_edges = [edge for edge in material_edges if edge["record_id"] in journey_edge_ids]
        lot_lineage_paths = [
            {"step_instance_id": step["step_instance_id"], **path}
            for step in steps for path in step["lot_lineage"]["paths"]
        ]
        history_flags = []
        if ambiguous_groups:
            history_flags.append("CHRONOLOGY_AMBIGUOUS")
        if any(step["membership_state"] in {
            "AMBIGUOUS_MULTIPLE_TIME_SCOPED_MEMBERSHIPS", "TEMPORALLY_AMBIGUOUS_MEMBERSHIP",
            "EVENT_LOT_RELATIONSHIP_TIME_AMBIGUOUS",
        } for step in steps):
            history_flags.append("MATERIAL_MEMBERSHIP_AMBIGUOUS")
        if any(step["membership_state"] == "EVENT_LOT_FIELD_UNVERIFIED" for step in steps):
            history_flags.append("MATERIAL_MEMBERSHIP_UNVERIFIED")
        if history_coverage.get("status") in {"PARTIAL", "CONTRADICTORY"}:
            history_flags.append("OBSERVATION_COVERAGE_INCOMPLETE")
        elif history_coverage.get("status") == "UNKNOWN" or wafer not in history_coverage.get("covered_wafer_ids", []):
            history_flags.append("OBSERVATION_COVERAGE_UNKNOWN")
        elif history_coverage.get("status") == "ASSERTED_UNVERIFIED":
            history_flags.append("OBSERVATION_COVERAGE_ASSERTED_UNVERIFIED")
        journeys.append({
            "wafer_id": wafer,
            "history_status": history_status,
            "history_flags": history_flags,
            "history_coverage": history_coverage,
            "route_conformance": conformance,
            "route_segments": segment_results,
            "sequence_edges": sequence_edges,
            "rework_edges": rework_edges,
            "material_relationships": journey_edges,
            "lot_lineage_paths": lot_lineage_paths,
            "steps": steps,
        })
    route_variants = [{
        "operations": [signature[2] for signature in route_signature],
        "route_id_sequence": [signature[0] or None for signature in route_signature],
        "route_version_sequence": [signature[1] or None for signature in route_signature],
        "wafer_ids": sorted(wafers), "count": len(wafers),
        "order_status": "ORDERED",
        "meaning": "Observed event sequence; conformance is reported only against an approved expected route with complete route coverage.",
    } for route_signature, wafers in sorted(variants.items())]
    if uncertain_wafers:
        route_variants.append({
            "operations": [], "route_id_sequence": [], "route_version_sequence": [],
            "wafer_ids": [item["wafer_id"] for item in uncertain_wafers], "count": len(uncertain_wafers),
            "order_status": "ORDER_UNCERTAIN", "event_groups": uncertain_wafers,
            "meaning": "Event time uncertainty intervals overlap; no chronological route sequence is asserted.",
        })
    ordered_variant_wafer_ids = sorted(wafer for group in variants.values() for wafer in group)
    uncertain_wafer_ids = sorted(item["wafer_id"] for item in uncertain_wafers)
    declared_population_set = set(declared_route_population)
    observed_population_set = set(by_wafer)
    ordered_denominator = len(ordered_variant_wafer_ids)
    for item in route_variants:
        if item["order_status"] == "ORDERED":
            item["ordered_observed_history_denominator"] = ordered_denominator
            item["share_of_ordered_observed_histories"] = (
                item["count"] / ordered_denominator if ordered_denominator else None
            )
            item["count_basis"] = "Observed event-bearing wafers with determinate chronology; not a yield or full eligible-population rate."
        else:
            item["ordered_observed_history_denominator"] = ordered_denominator
            item["share_of_ordered_observed_histories"] = None
            item["count_basis"] = "Chronology-uncertain event-bearing wafers are listed separately and excluded from ordered route variants."
    route_population_summary = {
        "coverage_status": route_population_coverage_level,
        "coverage_evidence_level": route_population_coverage_level,
        "coverage_record_id": route_coverage.get("record_id") if isinstance(route_coverage.get("record_id"), str) else None,
        "coverage_assessment": route_population_coverage_reason,
        "missing_record_ids": sorted({value for value in route_coverage.get("missing_record_ids", []) if isinstance(value, str) and value}) if isinstance(route_coverage.get("missing_record_ids", []), list) else [],
        "declared_covered_wafer_ids": declared_route_population,
        "declared_covered_population_count": len(declared_route_population),
        "observed_event_wafer_ids": sorted(observed_population_set),
        "observed_event_wafer_count": len(observed_population_set),
        "ordered_observed_history_wafer_ids": ordered_variant_wafer_ids,
        "ordered_observed_history_denominator": ordered_denominator,
        "chronology_uncertain_wafer_ids": uncertain_wafer_ids,
        "declared_covered_wafer_ids_without_event_rows": sorted(declared_population_set - observed_population_set),
        "observed_event_wafer_ids_outside_declared_coverage": sorted(observed_population_set - declared_population_set),
        "meaning": "Route variant counts describe observed event-bearing wafer histories. A completeness label is trusted only when an out-of-band authority verifies the exact source, population, operation and time scope. No route is inferred for a covered wafer with no submitted event rows.",
    }
    return {
        "journeys": journeys,
        "route_variants": route_variants,
        "route_population_summary": route_population_summary,
        "material_relationships": material_edges,
    }


def _analyze(data: Any) -> dict[str, Any]:
    """Analyze an already bounded evidence snapshot; never asserts causal effect."""
    if not isinstance(data, dict):
        return _refusal(data, "Input must be a JSON object.")
    try:
        _check_cancelled()
        events = _normalize_events(data)
        sources = _approved_sources(data)
        known_source_ids = {item["id"] for item in sources}
        unreferenced = sorted({event["source_id"] for event in events if event["source_id"] and event["source_id"] not in known_source_ids})
        if unreferenced:
            raise InputError("Events refer to source IDs without approved semantic metadata: " + ", ".join(unreferenced))
        relationship_index = _validate_relationships(data, events, known_source_ids)
        operation_definitions = _approved_operation_definitions(data, known_source_ids, relationship_index, events)
        material_edges = _material_relationships(data, known_source_ids, relationship_index)
        history_coverage = _history_coverage(data, events, known_source_ids, relationship_index)
        condition_events = _verified_condition_events(data, known_source_ids, relationship_index)
        _check_cancelled()
        input_outcomes = _bounded_outcomes(data)
        _validate_outcome_provenance(data, input_outcomes, known_source_ids, relationship_index)
        event_wafer_ids = {event["wafer_id"] for event in events}
        target_wafer_ids = _target_wafer_ids(data, event_wafer_ids, input_outcomes, relationship_index)
        ordered, ties, order_groups = _sort_events(events)
        _check_cancelled()
        journey = _route_analysis(
            data, events, ordered, known_source_ids, order_groups, relationship_index,
            operation_definitions, material_edges, history_coverage,
        )

        _check_cancelled()
        exposure = _exposure(data, events, known_source_ids, target_wafer_ids, condition_events, relationship_index)
        _check_cancelled()
        counterevidence = _outcomes_and_counterevidence(data, exposure, events, relationship_index, journey)
    except InputError as exc:
        return _refusal(data, str(exc))

    relationship_records = _relationship_evidence(relationship_index)
    event_source_ids = sorted({event["source_id"] for event in events if event["source_id"]})
    journey_by_wafer = {item["wafer_id"]: item for item in journey["journeys"]}
    claims = []
    for target in target_wafer_ids:
        _check_cancelled()
        target_journey = journey_by_wafer.get(target)
        if target_journey:
            steps = target_journey["steps"]
            repeated = len({step["operation"] for step in steps}) < len(steps)
            target_source_ids = sorted({step["source_id"] for step in steps if step["source_id"]})
            claims.append(claim(
                f"Wafer {target} has {len(steps)} distinct step instances in the submitted snapshot; repeated operation = {repeated}.",
                method="typed_step_instance_chronology", source_ids=target_source_ids,
                certainty="CONDITIONAL" if order_groups else "SUPPORTED",
            ))
    claims.append(claim(
        f"Observed {sum(1 for variant in journey['route_variants'] if variant['order_status'] == 'ORDERED')} ordered route sequence variant(s) across {len(journey['journeys'])} wafer(s); chronology unresolved for {sum(1 for item in journey['journeys'] if item['route_conformance'] == 'ORDER_UNCERTAIN')} wafer(s).",
        method="exact_wafer_event_sequence_grouping", source_ids=event_source_ids,
        certainty="CONDITIONAL" if order_groups else "SUPPORTED",
    ))
    conformance_counts: dict[str, int] = defaultdict(int)
    for item in journey["journeys"]:
        _check_cancelled()
        conformance_counts[item["route_conformance"]] += 1
    if data.get("expected_routes"):
        claims.append(claim(
            "Approved-route comparison by wafer: " + repr(dict(sorted(conformance_counts.items()))) +
            ". A mismatch is an observed difference that requires engineering review, not an asserted process violation.",
            method="approved_route_sequence_comparison_with_coverage_gate",
            source_ids=sorted(set(event_source_ids) | {route["source_id"] for route in data.get("expected_routes", [])}),
            certainty="CONDITIONAL",
        ))
    if exposure:
        exposure_source_ids = sorted(
            {item["source_id"] for item in exposure["evidence"] if item.get("source_id")} |
            {item["source_id"] for item in exposure["condition_event_evidence"] if item.get("source_id")} |
            set(exposure["coverage_evidence"]["source_ids"]) |
            set(exposure["coverage_evidence"]["covered_source_ids"])
        )
        claims.append(claim(
            "Observed exact-" + exposure["scope_type"].lower() + "/window processing matches = " + repr(exposure["definitely_exposed"]) +
            "; potentially exposed from observed missing assignment or clock uncertainty = " + repr(exposure["potentially_exposed"]) +
            "; unknown under incomplete or unverified coverage = " + repr(exposure["unknown"]) +
            "; not observed exposed with SOURCE_VERIFIED coverage = " + repr(exposure["not_observed_exposed"]) +
            "; asserted nonmatches under unverified coverage = " + repr(exposure["not_observed_exposed_under_unverified_coverage"]) + ".",
            method=(
                "exact_chamber_and_timezone_aware_window_with_coverage_gate"
                if exposure["scope_type"] == "CHAMBER"
                else "exact_tool_and_timezone_aware_window_with_coverage_gate"
            ),
            source_ids=exposure_source_ids,
            certainty="CONDITIONAL" if exposure["possibly_exposed"] else "SUPPORTED",
        ))
    if counterevidence:
        item = counterevidence[0]
        counter_source_ids = sorted(
            {row["source_id"] for row in item["outcome_evidence"] if row.get("source_id")} |
            set(exposure_source_ids if exposure else [])
        )
        claims.append(claim(
            "Hypothesis comparison for the suspected exposure: abnormal wafers with exact exposure=" +
            repr(item["abnormal_wafers_with_exact_exposure"]) +
            "; normal wafers with exact exposure=" +
            repr(item["normal_wafers_with_exact_exposure"]) +
            "; abnormal wafers not observed exposed=" + repr(item["abnormal_wafers_not_observed_exposed"]) +
            "; normal wafers not observed exposed=" + repr(item["normal_wafers_not_observed_exposed"]) +
            "; unknown exposure=" + repr(item["outcomes_with_unknown_exposure"]) +
            "; missing outcome=" + repr(item["population_wafers_missing_outcome"]) + ".",
            method="descriptive_outcome_exposure_cross_tabulation",
            source_ids=counter_source_ids, certainty="CONDITIONAL",
        ))

    limitations = [
        "Synthetic or caller-supplied evidence is not proof of company data, authorization, or source semantics.",
        "This descriptive reconstruction does not establish a root cause or intervention effect.",
        "A complete route or route violation cannot be inferred without an approved expected-route definition and event coverage.",
        "Identity aliases are kept separate; no unapproved wafer or lot identity merge is performed.",
    ]
    if data.get("target_lot_id") is not None:
        limitations.append(
            "Target lot membership is derived only from supplied outcome rows and their declared lot_id/wafer_id relationship; snapshot completeness for that lot is not established."
        )
    status = "VALID"
    if order_groups:
        status = "PARTIAL"
        limitations.append("Event-time uncertainty intervals overlap. Central timestamps are shown for reference, but no order is asserted within each listed step group.")
    if conformance_counts.get("COVERAGE_INCOMPLETE"):
        status = "PARTIAL"
        limitations.append("Approved route definitions were present, but route coverage did not cover the full wafer population.")
    if conformance_counts.get("ROUTE_IDENTITY_UNKNOWN"):
        status = "PARTIAL"
        limitations.append("Route identity or version was missing or changed within at least one wafer journey.")
    if conformance_counts.get("ROUTE_IDENTITY_UNVERIFIED"):
        status = "PARTIAL"
        limitations.append("Route identity or version fields were not declared by every event relationship; route conformance was not asserted for those segments.")
    if conformance_counts.get("ROUTE_DEFINITION_EFFECTIVITY_UNCERTAIN"):
        status = "PARTIAL"
        limitations.append("An expected-route definition relationship did not cover the full event-time uncertainty interval; route conformance remains unknown for those segments.")
    if conformance_counts.get("ORDER_UNCERTAIN"):
        status = "PARTIAL"
        limitations.append("Route sequence comparison was skipped for wafers with overlapping event-time uncertainty intervals.")
    if conformance_counts.get("EXPECTED_ROUTE_MISMATCH"):
        limitations.append("Observed route sequence differs from the approved expected route; this is not classified as a process violation.")
    if history_coverage.get("status") != "SOURCE_VERIFIED":
        limitations.append(
            "Wafer history completeness level is " + str(history_coverage.get("coverage_evidence_level", "UNKNOWN"))
            + "; chronology describes submitted event records only, and an absent event is not proof that a process step did not occur."
        )
    if not operation_definitions:
        limitations.append("Operation definition records were not supplied; operation labels are retained as event values and are not upgraded to approved operation definitions.")
    duplicate_copies = sum(event.get("duplicate_record_copies", 0) for event in events)
    if duplicate_copies:
        limitations.append(f"Collapsed {duplicate_copies} byte-for-byte duplicate source rows at the declared process-step-instance grain; conflicting duplicate rows are refused.")
    if exposure and exposure["possibly_exposed"]:
        status = "PARTIAL"
        if not exposure["coverage_complete"]:
            limitations.append(exposure["coverage_reason"])
        classifications = {item["classification"] for item in exposure["evidence"]}
        if "UNKNOWN_CHAMBER" in classifications:
            limitations.append("Events with missing chamber assignment are classified as possible exposure, never exact chamber exposure.")
        if "UNKNOWN_TOOL" in classifications:
            limitations.append("Events with missing tool assignment are classified as possible tool exposure, never exact tool exposure.")
        if "TIME_BOUNDARY_UNCERTAIN" in classifications:
            limitations.append("Clock uncertainty overlaps the exposure-window boundary; these events are possible, not exact, matches.")
        if "SCOPE_OR_TIME_FIELD_NOT_APPROVED_BY_RELATIONSHIP" in classifications:
            limitations.append("Exact exposure was withheld because the event relationship did not declare the selected equipment or event-time field.")
        if "SOURCE_RELATIONSHIP_EFFECTIVITY_UNCERTAIN" in classifications:
            limitations.append("Exposure and comparator classification remain unknown because event-time uncertainty crosses the source relationship effectivity boundary.")
    if exposure and exposure["condition_event_status"] == "NO_CONDITION_EVENT_RECORDS_SUPPLIED" and exposure["condition_context"]["evidence_status"] == "CALLER_SUPPLIED_UNVERIFIED":
        limitations.append("The suspected maintenance/change/process label is caller-supplied and has no source-linked condition-event record in this snapshot.")
    if exposure and exposure["coverage_evidence_level"] != "SOURCE_VERIFIED":
        status = "PARTIAL"
        limitations.append(
            "Exposure coverage is " + exposure["coverage_evidence_level"]
            + "; nonmatches remain unknown and cannot be used as verified unaffected comparators."
        )

    result = envelope("p2", data, status, claims, limitations, sources=sources)
    result["provenance"]["engine_version"] = ENGINE_VERSION
    result["populations"] = [] if exposure is None else [
        {"classification": "EXPOSED", "wafer_ids": exposure["definitely_exposed"], "count": len(exposure["definitely_exposed"]), "basis": f"A source-linked process-step instance names the exact {exposure['scope_type'].lower()} and its time interval overlaps the query window."},
        {"classification": "POTENTIALLY_EXPOSED", "wafer_ids": exposure["potentially_exposed"], "count": len(exposure["potentially_exposed"]), "basis": "An observed event has missing selected-equipment assignment or time uncertainty that could overlap the query window."},
        {"classification": "UNKNOWN", "wafer_ids": exposure["unknown"], "count": len(exposure["unknown"]), "basis": "Coverage is incomplete or the source relationship does not approve the required equipment/time fields."},
        {"classification": "NOT_OBSERVED_EXPOSED", "wafer_ids": exposure["not_observed_exposed"], "count": len(exposure["not_observed_exposed"]), "basis": exposure["coverage_reason"]},
        {"classification": "NOT_OBSERVED_UNDER_UNVERIFIED_COVERAGE", "wafer_ids": exposure["not_observed_exposed_under_unverified_coverage"], "count": len(exposure["not_observed_exposed_under_unverified_coverage"]), "basis": "The source record asserts coverage, but no host authority verified it; these wafers are not comparator evidence."},
    ]
    result["transformations"] = [{
        "id": "p2-event-time-normalization-v1", "operation": "Normalize timezone-aware event times to UTC; retain original timestamp in journey.",
        "input_grain": "one approved process-step instance", "output_grain": "one event in one wafer journey",
    }, {
        "id": "p2-journey-and-route-variants-v1", "journeys": journey["journeys"],
        "route_variants": journey["route_variants"],
        "route_population_summary": journey["route_population_summary"],
        "material_relationships": journey["material_relationships"],
    }, {
        "id": "p2-exposure-evidence-v1", "exposure": exposure,
    }]
    result["units"] = {}
    result["counterevidence"] = counterevidence
    result["uncertainty"] = {
        "equal_timestamp_ties": ties,
        "order_uncertainty_groups": order_groups,
        "exposure_coverage_complete": None if exposure is None else exposure["coverage_complete"],
        "route_conformance_counts": dict(sorted(conformance_counts.items())),
        "history_coverage_status": history_coverage.get("status"),
        "collapsed_duplicate_source_records": duplicate_copies,
        "causal_identifiability": "NOT_ESTABLISHED",
    }
    result["artifacts"] = [{
        "kind": "investigation_snapshot", "format": "application/json",
        "content_sha256": result["provenance"]["input_sha256"],
        "note": "The deterministic envelope itself is the reproducible export.",
        "scope": {
            "target_lot_id": data.get("target_lot_id"),
            "target_wafer_ids": target_wafer_ids,
        },
        "target_outcomes": [],
        "source_relationships": relationship_records,
        "journey": journey,
        "exposure_analysis": exposure,
    }]
    # Preserve cancellation responsiveness while constructing a large evidence
    # export. No partial envelope escapes if the operator cancels this phase.
    target_outcomes = []
    target_set = set(target_wafer_ids)
    for outcome in input_outcomes:
        _check_cancelled()
        if isinstance(outcome, dict) and outcome.get("wafer_id") in target_set:
            target_outcomes.append({
                "wafer_id": outcome["wafer_id"],
                "label": outcome["label"],
                "timestamp": outcome["timestamp"],
                "source_id": outcome["source_id"],
                "relationship_id": outcome["relationship_id"],
                **({"lot_id": outcome["lot_id"]} if isinstance(outcome.get("lot_id"), str) else {}),
            })
    result["artifacts"][0]["target_outcomes"] = target_outcomes
    _check_cancelled()
    validate_envelope(result)
    return result


def analyze(data: Any, *, cancel_check: Callable[[], bool] | None = None,
            coverage_authority: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
    """Analyze a bounded snapshot and cooperatively stop when requested."""
    token = _CANCEL_CHECK.set(cancel_check)
    coverage_token = _COVERAGE_AUTHORITY.set(coverage_authority)
    try:
        _check_cancelled()
        return _analyze(data)
    finally:
        _COVERAGE_AUTHORITY.reset(coverage_token)
        _CANCEL_CHECK.reset(token)
