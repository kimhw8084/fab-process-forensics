"""Synthetic local MCP service for P2 transport and boundary qualification.

This is a read-only fixture with server-enforced source permissions and query
bounds. It contains no company data and is never a production endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
import uuid

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from fabintel.mcp_adapter import operation_hash


SOURCE_ID = "SYN_PROCESS"
RELATIONSHIP_ID = "SYN_REL_WAFER_STEP"
OUTCOME_SOURCE_ID = "SYN_OUTCOMES"
OUTCOME_RELATIONSHIP_ID = "SYN_REL_WAFER_OUTCOME"
COVERAGE_SOURCE_ID = "SYN_EXPOSURE_COVERAGE"
COVERAGE_RELATIONSHIP_ID = "SYN_REL_EXPOSURE_COVERAGE"
HISTORY_COVERAGE_SOURCE_ID = "SYN_HISTORY_COVERAGE"
HISTORY_COVERAGE_RELATIONSHIP_ID = "SYN_REL_HISTORY_COVERAGE"
ROUTE_SOURCE_ID = "SYN_ROUTE_DEFINITIONS"
ROUTE_RELATIONSHIP_ID = "SYN_REL_ROUTE_DEFINITION"
ROUTE_COVERAGE_SOURCE_ID = "SYN_ROUTE_COVERAGE"
ROUTE_COVERAGE_RELATIONSHIP_ID = "SYN_REL_ROUTE_COVERAGE"
MATERIAL_SOURCE_ID = "SYN_MATERIAL"
MATERIAL_RELATIONSHIP_ID = "SYN_REL_WAFER_LOT_MEMBERSHIP"
SEMANTIC_VERSION = "SYN-SEM-1"
START = "2026-11-21T00:00:00+00:00"
END = "2026-11-22T00:00:00+00:00"
READ_SCOPE = "SYNTHETIC_READ"


def _as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


class FixtureState:
    def __init__(self, delay_ms: int = 0, mutate: str | None = None, scenario: str = "legacy",
                 descriptor_topology: str = "standard"):
        self.delay_ms = max(0, min(delay_ms, 5000))
        self.mutate = mutate
        self.scenario = scenario
        self.descriptor_topology = descriptor_topology
        self.source_definitions = copy.deepcopy(SOURCE_DEFINITIONS)
        self.source_relationships = copy.deepcopy(SOURCE_RELATIONSHIPS)
        self.data_rows = copy.deepcopy(DATA_ROWS)
        self.time_start, self.time_end = START, END
        self.limits = {"max_rows": 100, "max_bytes": 32768, "max_seconds": 5}
        if scenario in {"engineer-100", "engineer-100-followup", "engineer-100-alias",
                        "engineer-100-alias-followup", "engineer-100-alt-alias",
                        "engineer-100-alt-alias-followup", "engineer-100-alt-alias-13k",
                        "engineer-100-alt-alias-13k-followup"}:
            self.data_rows = _engineer_100_data_rows()
            self.time_start, self.time_end = "2026-11-20T00:00:00+00:00", "2026-11-30T00:00:00+00:00"
            self.limits = {"max_rows": 1000, "max_bytes": 4194304, "max_seconds": 30}
            if "alias" in scenario:
                (self.source_definitions, self.source_relationships,
                 self.data_rows) = _aliased_engineer_100_sources(
                    self.source_definitions, self.source_relationships, self.data_rows,
                    schema_variant="alternate" if "alt-alias" in scenario else "fabx",
                )
            if scenario in {"engineer-100-alt-alias-13k", "engineer-100-alt-alias-13k-followup"}:
                # Large-catalog challenge: these descriptors are intentionally
                # unclassified and carry no field semantics or relationships.
                # Naming must not cause the mapper to assign them a source role.
                self.source_definitions = copy.deepcopy(self.source_definitions)
                self.data_rows = copy.deepcopy(self.data_rows)
                for index in range(13001):
                    source_id = f"OPAQUE_CATALOG_ENTRY_{index:05d}"
                    self.source_definitions[source_id] = {
                        "record_kind": "UNCLASSIFIED",
                        "source_hash": hashlib.sha256(source_id.encode()).hexdigest(),
                        "grain": "UNCLASSIFIED_ROW",
                        "column_definitions": {},
                    }
                    self.data_rows[source_id] = []
        self._apply_descriptor_topology()
        self.lock = threading.Lock()
        self.active: dict[str, tuple[threading.Event, threading.Event]] = {}
        self.audit: dict[str, dict[str, Any]] = {}
        self.semantics_requested: set[str] = set()

    def _apply_descriptor_topology(self):
        """Build fixed synthetic descriptor variants for live onboarding tests."""
        topology = self.descriptor_topology
        if topology == "standard":
            return
        event_ids = [source_id for source_id, spec in self.source_definitions.items()
                     if spec.get("record_kind") == "PROCESS_STEP_INSTANCE"]
        membership_ids = [source_id for source_id, spec in self.source_definitions.items()
                          if spec.get("record_kind") == "MATERIAL_RELATIONSHIP"]
        if len(event_ids) != 1 or len(membership_ids) != 1:
            raise ValueError("Descriptor topology requires one process source and one membership source.")
        event_id, membership_id = event_ids[0], membership_ids[0]
        event = self.source_definitions[event_id]
        event_relation_id = next(key for key, relation in self.source_relationships.items()
                                  if relation.get("source_ids") == [event_id])
        membership_relation_id = next(key for key, relation in self.source_relationships.items()
                                       if relation.get("source_ids") == [membership_id])
        event_relation = self.source_relationships[event_relation_id]

        if topology == "arrival-time-only":
            event_column = next(name for name, field in event["column_definitions"].items()
                                if field.get("meaning") == "event time")
            event["column_definitions"][event_column]["meaning"] = "record ingestion time"
        elif topology == "static-membership":
            membership = self.source_definitions[membership_id]
            columns = membership["column_definitions"]
            effective_fields = [name for name, field in columns.items()
                                if field.get("meaning") in {"effective start", "effective end"}]
            for name in effective_fields:
                columns.pop(name)
            relation = self.source_relationships[membership_relation_id]
            relation["keys"] = [key for key in relation["keys"] if key not in effective_fields]
        elif topology == "missing-event-relationship-key":
            event_key = next(name for name, field in event["column_definitions"].items()
                             if field.get("entity") == "process_step_instance"
                             and field.get("meaning") == "actual operation instance")
            event_relation["keys"] = [key for key in event_relation["keys"] if key != event_key]
        elif topology == "equipment-group-only":
            columns = event["column_definitions"]
            removed = [name for name, field in columns.items()
                       if field.get("entity") in {"tool", "chamber"}]
            for name in removed:
                columns.pop(name)
            columns["equipment_group"] = {
                "type": "identifier", "entity": "equipment_group",
                "meaning": "equipment family; not a physical chamber",
            }
            event_relation["keys"] = [key for key in event_relation["keys"] if key not in removed]
            event_relation["keys"].append("equipment_group")
        elif topology == "duplicate-event-version":
            duplicate_id = "SYN_PROCESS_OLDER_SEMANTICS"
            duplicate = copy.deepcopy(event)
            duplicate["semantic_version"] = "SYN-SEM-2025.1"
            duplicate["source_hash"] = hashlib.sha256(b"synthetic-older-event-schema").hexdigest()
            self.source_definitions[duplicate_id] = duplicate
            self.data_rows[duplicate_id] = []
            duplicate_relation = copy.deepcopy(event_relation)
            duplicate_relation["source_ids"] = [duplicate_id]
            self.source_relationships["SYN_REL_PROCESS_OLDER"] = duplicate_relation
        elif topology == "combined-untyped-process-outcome":
            # A suggestive source label cannot repair absent role semantics.
            event["record_kind"] = "PROCESS_AND_OUTCOME"
            event["source_name"] = "COMPLETE_PROCESS_AND_WAFER_OUTCOME_HISTORY"
        else:
            raise ValueError(f"Unknown synthetic descriptor topology: {topology}")

        # The advertised hash identifies the exact descriptor after each
        # deliberate schema mutation; it grants no authority or approval.
        affected = [event_id] if topology not in {"static-membership"} else [membership_id]
        if topology == "duplicate-event-version":
            affected.append("SYN_PROCESS_OLDER_SEMANTICS")
        for source_id in affected:
            body = {key: value for key, value in self.source_definitions[source_id].items()
                    if key not in {"source_hash", "semantic_version"}}
            self.source_definitions[source_id]["source_hash"] = hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

    def begin(self, operation_id: str):
        with self.lock:
            if operation_id in self.active or operation_id in self.audit:
                raise ToolError("DUPLICATE_OPERATION_ID")
            cancel_event, stopped_event = threading.Event(), threading.Event()
            self.active[operation_id] = (cancel_event, stopped_event)
            return cancel_event, stopped_event

    def finish(self, operation_id: str, audit_record: dict[str, Any] | None = None):
        with self.lock:
            pair = self.active.pop(operation_id, None)
            if pair is not None:
                pair[1].set()
            if audit_record is not None:
                self.audit[operation_id] = audit_record

    def cancel(self, operation_id: str) -> bool:
        with self.lock:
            pair = self.active.get(operation_id)
            if pair is None:
                return False
            pair[0].set()
            stopped = pair[1]
        return stopped.wait(timeout=2.0)

    def audit_for(self, operation_id: str):
        with self.lock:
            return self.audit.get(operation_id)


def _engineer_100_data_rows() -> dict[str, list[dict[str, Any]]]:
    """Load the independently fixed 100-wafer synthetic acceptance history."""
    path = Path(__file__).resolve().parent.parent / "qualification" / "fixtures" / "complex_engineer_investigation_v1.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    rows = {source_id: [] for source_id in SOURCE_DEFINITIONS}
    rows[SOURCE_ID] = copy.deepcopy(fixture["events"])
    rows[OUTCOME_SOURCE_ID] = copy.deepcopy(fixture["outcomes"])
    for index, outcome in enumerate(rows[OUTCOME_SOURCE_ID], start=1):
        outcome.setdefault("outcome_id", f"SYN-EW-OUTCOME-{index:03d}")
    for key, source_id in (("coverage", COVERAGE_SOURCE_ID),
                           ("history_coverage", HISTORY_COVERAGE_SOURCE_ID),
                           ("route_coverage", ROUTE_COVERAGE_SOURCE_ID)):
        record = copy.deepcopy(fixture[key])
        record.setdefault("timestamp", record.get("window_start", "2026-11-21T00:00:00+00:00"))
        if key == "coverage":
            record["covered_source_ids"] = [SOURCE_ID]
            record["source_ids"] = [source_id]
        elif key == "history_coverage":
            record["covered_source_ids"] = [SOURCE_ID]
            record["source_ids"] = [source_id]
        else:
            record["covered_source_ids"] = [SOURCE_ID, ROUTE_SOURCE_ID]
            record["source_ids"] = [source_id]
        rows[source_id] = [record]
    rows[ROUTE_SOURCE_ID] = copy.deepcopy(fixture["expected_routes"])
    for index, route in enumerate(rows[ROUTE_SOURCE_ID], start=1):
        route.setdefault("timestamp", f"2026-11-20T00:{index:02d}:00+00:00")
    material = []
    for edge in fixture["material_relationships"]:
        if edge.get("relationship_type") != "LOT_MEMBERSHIP":
            continue
        row = copy.deepcopy(edge)
        row.update(copy.deepcopy(edge.get("key_values", {})))
        row["timestamp"] = row.get("observed_at")
        row["key_values"].update({
            "record_id": row["record_id"], "timestamp": row["timestamp"],
        })
        material.append(row)
    rows[MATERIAL_SOURCE_ID] = material
    return rows

SOURCE_DEFINITIONS = {
    SOURCE_ID: {
        "record_kind": "PROCESS_STEP_INSTANCE",
        "source_hash": "a" * 64,
        "grain": "one process step instance",
        "column_definitions": {
            "wafer_id": {"type": "identifier", "entity": "wafer"},
            "step_instance_id": {"type": "identifier", "entity": "process_step_instance", "meaning": "actual operation instance"},
            "timestamp": {"type": "timestamp", "timezone_required": True, "meaning": "event time"},
            "recorded_at": {"type": "timestamp", "timezone_required": True, "nullable": True, "meaning": "record ingestion time; null when unavailable"},
            "time_uncertainty_seconds": {"type": "number", "nullable": True, "meaning": "event-time uncertainty in seconds; null when unavailable"},
            "lot_id": {"type": "identifier", "entity": "lot", "nullable": True},
            "operation": {"type": "string", "entity": "operation", "meaning": "source-defined process operation"},
            "tool_id": {"type": "identifier", "entity": "tool"},
            "chamber_id": {"type": "identifier", "entity": "chamber"},
            "rework_of_step_instance_id": {"type": "identifier", "entity": "process_step_instance", "meaning": "prior step instance this operation reworks", "nullable": True},
            "route_id": {"type": "identifier", "entity": "route", "nullable": True},
            "route_version": {"type": "identifier", "entity": "route_version", "nullable": True},
        },
    },
    OUTCOME_SOURCE_ID: {
        "record_kind": "WAFER_OUTCOME",
        "source_hash": "b" * 64,
        "grain": "one wafer outcome record",
        "column_definitions": {
            "wafer_id": {"type": "identifier", "entity": "wafer"},
            "outcome_id": {"type": "identifier", "entity": "outcome_record"},
            "timestamp": {"type": "timestamp", "timezone_required": True, "meaning": "outcome time observation"},
            "label": {"type": "enum", "values": ["ABNORMAL", "NORMAL"]},
            "product_id": {"type": "identifier", "entity": "product"},
        },
    },
    COVERAGE_SOURCE_ID: {
        "record_kind": "EXPOSURE_COVERAGE",
        "source_hash": "c" * 64,
        "grain": "one declared exposure observation coverage record",
        "column_definitions": {
            "record_id": {"type": "identifier", "entity": "coverage_record"},
            "timestamp": {"type": "timestamp", "timezone_required": True, "meaning": "source observation time"},
            "complete": {"type": "boolean"},
            "covered_wafer_ids": {"type": "identifier_list", "entity": "wafer"},
            "covered_lot_ids": {"type": "identifier_list", "entity": "lot"},
            "covered_operation_ids": {"type": "identifier_list", "entity": "operation"},
            "population_kind": {"type": "string", "meaning": "population identity grain"},
            "source_authority_claim": {"type": "string", "meaning": "unverified authority label asserted by fixture"},
            "covered_source_ids": {"type": "identifier_list", "entity": "source", "meaning": "sources covered by completeness scope"},
            "source_ids": {"type": "identifier_list", "entity": "source", "meaning": "coverage record source identifiers"},
            "window_start": {"type": "timestamp", "timezone_required": True, "meaning": "window start"},
            "window_end": {"type": "timestamp", "timezone_required": True, "meaning": "window end"},
            "valid_until": {"type": "timestamp", "timezone_required": True, "meaning": "valid until"},
            "missing_record_ids": {"type": "identifier_list", "entity": "record"},
        },
    },
    HISTORY_COVERAGE_SOURCE_ID: {
        "record_kind": "PROCESS_HISTORY_COVERAGE",
        "source_hash": "f" * 64,
        "grain": "one declared process-history observation coverage record",
        "column_definitions": {
            "record_id": {"type": "identifier", "entity": "coverage_record"},
            "timestamp": {"type": "timestamp", "timezone_required": True, "meaning": "source observation time"},
            "complete": {"type": "boolean"},
            "covered_wafer_ids": {"type": "identifier_list", "entity": "wafer"},
            "covered_lot_ids": {"type": "identifier_list", "entity": "lot"},
            "covered_operation_ids": {"type": "identifier_list", "entity": "operation"},
            "population_kind": {"type": "string", "meaning": "population identity grain"},
            "source_authority_claim": {"type": "string", "meaning": "unverified authority label asserted by fixture"},
            "covered_source_ids": {"type": "identifier_list", "entity": "source", "meaning": "sources covered by completeness scope"},
            "source_ids": {"type": "identifier_list", "entity": "source", "meaning": "coverage record source identifiers"},
            "window_start": {"type": "timestamp", "timezone_required": True, "meaning": "window start"},
            "window_end": {"type": "timestamp", "timezone_required": True, "meaning": "window end"},
            "valid_until": {"type": "timestamp", "timezone_required": True, "meaning": "valid until"},
            "missing_record_ids": {"type": "identifier_list", "entity": "record"},
        },
    },
    ROUTE_SOURCE_ID: {
        "record_kind": "ROUTE_DEFINITION",
        "source_hash": "d" * 64,
        "grain": "one approved route definition per route version",
        "column_definitions": {
            "timestamp": {"type": "timestamp", "timezone_required": True, "meaning": "route definition record time"},
            "route_id": {"type": "identifier", "entity": "route"},
            "route_version": {"type": "identifier", "entity": "route_version"},
            "approved": {"type": "boolean"},
            "operations": {"type": "ordered_string_list"},
            "allowed_sequences": {"type": "list_of_ordered_string_lists"},
        },
    },
    ROUTE_COVERAGE_SOURCE_ID: {
        "record_kind": "ROUTE_COVERAGE",
        "source_hash": "e" * 64,
        "grain": "one route observation coverage record per population and time window",
        "column_definitions": {
            "record_id": {"type": "identifier", "entity": "coverage_record"},
            "timestamp": {"type": "timestamp", "timezone_required": True, "meaning": "source observation time"},
            "complete": {"type": "boolean"},
            "covered_wafer_ids": {"type": "identifier_list", "entity": "wafer"},
            "covered_lot_ids": {"type": "identifier_list", "entity": "lot"},
            "covered_operation_ids": {"type": "identifier_list", "entity": "operation"},
            "population_kind": {"type": "string", "meaning": "population identity grain"},
            "source_authority_claim": {"type": "string", "meaning": "unverified authority label asserted by fixture"},
            "covered_source_ids": {"type": "identifier_list", "entity": "source", "meaning": "sources covered by completeness scope"},
            "source_ids": {"type": "identifier_list", "entity": "source", "meaning": "coverage record source identifiers"},
            "window_start": {"type": "timestamp", "timezone_required": True, "meaning": "window start"},
            "window_end": {"type": "timestamp", "timezone_required": True, "meaning": "window end"},
            "valid_until": {"type": "timestamp", "timezone_required": True, "meaning": "valid until"},
            "missing_record_ids": {"type": "identifier_list", "entity": "record"},
        },
    },
    MATERIAL_SOURCE_ID: {
        "record_kind": "MATERIAL_RELATIONSHIP",
        "source_hash": "9" * 64,
        "grain": "one typed, effective-dated wafer-to-lot relationship record",
        "column_definitions": {
            "record_id": {"type": "identifier", "entity": "relationship_record"},
            "relationship_type": {"type": "string"},
            "from_entity": {"type": "typed_entity_reference"},
            "to_entity": {"type": "typed_entity_reference"},
            "from_entity_id": {"type": "identifier", "entity": "lot"},
            "from_entity_type": {"type": "string", "meaning": "from entity type"},
            "to_entity_id": {"type": "identifier", "entity": "wafer"},
            "to_entity_type": {"type": "string", "meaning": "to entity type"},
            "timestamp": {"type": "timestamp", "timezone_required": True, "meaning": "source observation time"},
            "effective_start": {"type": "timestamp", "timezone_required": True, "meaning": "effective start"},
            "effective_end": {"type": "timestamp", "timezone_required": True, "meaning": "effective end"},
            "observed_at": {"type": "timestamp", "timezone_required": True, "meaning": "record arrival time"},
            "key_values": {"type": "object"},
        },
    },
}

SOURCE_RELATIONSHIPS = {
    RELATIONSHIP_ID: {
        "source_ids": [SOURCE_ID],
        "keys": ["wafer_id", "step_instance_id", "operation", "timestamp", "lot_id", "tool_id", "chamber_id", "rework_of_step_instance_id", "route_id", "route_version"],
        "cardinality": "one process step instance to one wafer identity",
        "grain": "one process step instance",
    },
    OUTCOME_RELATIONSHIP_ID: {
        "source_ids": [OUTCOME_SOURCE_ID],
        "keys": ["wafer_id", "outcome_id", "timestamp", "label", "product_id"],
        "cardinality": "one outcome record to one wafer identity",
        "grain": "one wafer outcome record",
    },
    COVERAGE_RELATIONSHIP_ID: {
        "source_ids": [COVERAGE_SOURCE_ID],
        "keys": ["record_id", "timestamp", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids", "population_kind", "source_authority_claim", "covered_source_ids", "source_ids", "window_start", "window_end", "valid_until", "missing_record_ids"],
        "cardinality": "one declared observation coverage record to one source observation scope",
        "grain": "one exposure observation coverage record",
    },
    HISTORY_COVERAGE_RELATIONSHIP_ID: {
        "source_ids": [HISTORY_COVERAGE_SOURCE_ID],
        "keys": ["record_id", "timestamp", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids", "population_kind", "source_authority_claim", "covered_source_ids", "source_ids", "window_start", "window_end", "valid_until", "missing_record_ids"],
        "cardinality": "one declared process-history coverage record to one source observation scope",
        "grain": "one process-history observation coverage record",
    },
    ROUTE_RELATIONSHIP_ID: {
        "source_ids": [ROUTE_SOURCE_ID],
        "keys": ["timestamp", "route_id", "route_version", "approved", "operations", "allowed_sequences"],
        "cardinality": "one approved route definition to one route version",
        "grain": "one approved route definition per route version",
    },
    ROUTE_COVERAGE_RELATIONSHIP_ID: {
        "source_ids": [ROUTE_COVERAGE_SOURCE_ID],
        "keys": ["record_id", "timestamp", "complete", "covered_wafer_ids", "covered_lot_ids", "covered_operation_ids", "population_kind", "source_authority_claim", "covered_source_ids", "source_ids", "window_start", "window_end", "valid_until", "missing_record_ids"],
        "cardinality": "one route coverage record to an explicitly listed population and time window",
        "grain": "one route observation coverage record per population and time window",
    },
    MATERIAL_RELATIONSHIP_ID: {
        "source_ids": [MATERIAL_SOURCE_ID],
        "keys": ["record_id", "from_entity_id", "from_entity_type", "to_entity_id", "to_entity_type", "timestamp"],
        "relationship_type": "LOT_MEMBERSHIP",
        "cardinality": "one effective-dated wafer membership record to one lot and one wafer",
        "grain": "one typed, effective-dated wafer-to-lot relationship record",
    },
}

DATA_ROWS = {
    SOURCE_ID: [
        {"wafer_id": "SYN-W1", "step_instance_id": "SYN-S1", "operation": "ETCH", "lot_id": "SYN-LOT-OLD", "tool_id": "SYN-T1", "chamber_id": "SYN-C1", "timestamp": "2026-11-21T03:30:00+00:00", "rework_of_step_instance_id": None, "route_id": "SYN-BASE", "route_version": "v1"},
        {"wafer_id": "SYN-W1", "step_instance_id": "SYN-S2", "operation": "CLEAN", "lot_id": "SYN-LOT-OLD", "tool_id": "SYN-T2", "chamber_id": "SYN-C3", "timestamp": "2026-11-21T06:30:00+00:00", "rework_of_step_instance_id": None, "route_id": "SYN-BASE", "route_version": "v1"},
        {"wafer_id": "SYN-W2", "step_instance_id": "SYN-S3", "operation": "ETCH", "lot_id": "SYN-LOT-2", "tool_id": "SYN-T1", "chamber_id": "SYN-C1", "timestamp": "2026-11-21T03:40:00+00:00", "rework_of_step_instance_id": None, "route_id": "SYN-REWORK", "route_version": "v2"},
        {"wafer_id": "SYN-W2", "step_instance_id": "SYN-S4", "operation": "ETCH", "lot_id": "SYN-LOT-2", "tool_id": "SYN-T1", "chamber_id": "SYN-C1", "timestamp": "2026-11-21T04:40:00+00:00", "rework_of_step_instance_id": "SYN-S3", "route_id": "SYN-REWORK", "route_version": "v2"},
        {"wafer_id": "SYN-W3", "step_instance_id": "SYN-S5", "operation": "ETCH", "lot_id": "SYN-LOT-3", "tool_id": "SYN-T1", "chamber_id": "SYN-C2", "timestamp": "2026-11-21T04:20:00+00:00", "rework_of_step_instance_id": None, "route_id": "SYN-BASE", "route_version": "v1"},
        {"wafer_id": "SYN-W3", "step_instance_id": "SYN-S6", "operation": "ETCH", "lot_id": "SYN-LOT-3", "tool_id": "SYN-T1", "chamber_id": "SYN-C2", "timestamp": "2026-11-21T05:20:00+00:00", "rework_of_step_instance_id": "SYN-S5", "route_id": "SYN-BASE", "route_version": "v1"},
        {"wafer_id": "SYN-W4", "step_instance_id": "SYN-S7", "operation": "ETCH", "lot_id": "SYN-LOT-4", "tool_id": "SYN-T2", "chamber_id": "SYN-C3", "timestamp": "2026-11-21T05:00:00+00:00", "rework_of_step_instance_id": None, "route_id": "SYN-BASE", "route_version": "v1"},
        {"wafer_id": "SYN-W4", "step_instance_id": "SYN-S8", "operation": "CMP", "lot_id": "SYN-LOT-4", "tool_id": "SYN-T2", "chamber_id": "SYN-C3", "timestamp": "2026-11-21T05:30:00+00:00", "rework_of_step_instance_id": None, "route_id": "SYN-BASE", "route_version": "v1"},
        {"wafer_id": "SYN-W4", "step_instance_id": "SYN-S9", "operation": "CLEAN", "lot_id": "SYN-LOT-4", "tool_id": "SYN-T2", "chamber_id": "SYN-C3", "timestamp": "2026-11-21T06:00:00+00:00", "rework_of_step_instance_id": None, "route_id": "SYN-BASE", "route_version": "v1"},
    ],
    OUTCOME_SOURCE_ID: [
        {"wafer_id": "SYN-W1", "outcome_id": "SYN-O1", "label": "ABNORMAL", "product_id": "SYN-P1", "timestamp": "2026-11-21T08:00:00+00:00"},
        {"wafer_id": "SYN-W2", "outcome_id": "SYN-O2", "label": "NORMAL", "product_id": "SYN-P1", "timestamp": "2026-11-21T08:00:00+00:00"},
        {"wafer_id": "SYN-W3", "outcome_id": "SYN-O3", "label": "ABNORMAL", "product_id": "SYN-P2", "timestamp": "2026-11-21T08:00:00+00:00"},
        {"wafer_id": "SYN-W4", "outcome_id": "SYN-O4", "label": "NORMAL", "product_id": "SYN-P2", "timestamp": "2026-11-21T08:00:00+00:00"},
    ],
    COVERAGE_SOURCE_ID: [{
        "record_id": "SYN-COV-1", "timestamp": "2026-11-21T06:00:00+00:00", "complete": True,
        "covered_wafer_ids": ["SYN-W1", "SYN-W2", "SYN-W3", "SYN-W4"],
        "covered_lot_ids": ["SYN-LOT-OLD", "SYN-LOT-2", "SYN-LOT-3", "SYN-LOT-4"], "covered_operation_ids": ["ETCH", "CLEAN", "CMP"],
        "population_kind": "WAFER", "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION",
        "covered_source_ids": [SOURCE_ID], "source_ids": [COVERAGE_SOURCE_ID],
        "window_start": "2026-11-21T03:00:00+00:00", "window_end": "2026-11-21T06:00:00+00:00",
        "valid_until": "2026-11-21T06:00:00+00:00",
        "missing_record_ids": [],
    }],
    HISTORY_COVERAGE_SOURCE_ID: [{
        "record_id": "SYN-HISTORY-COV-1", "timestamp": "2026-11-21T21:00:00+00:00", "complete": True,
        "covered_wafer_ids": ["SYN-W1", "SYN-W2", "SYN-W3", "SYN-W4"],
        "covered_lot_ids": ["SYN-LOT-OLD", "SYN-LOT-2", "SYN-LOT-3", "SYN-LOT-4"], "covered_operation_ids": ["ETCH", "CLEAN", "CMP"],
        "population_kind": "WAFER", "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION",
        "covered_source_ids": [SOURCE_ID], "source_ids": [HISTORY_COVERAGE_SOURCE_ID],
        "window_start": "2026-11-21T00:00:00+00:00", "window_end": "2026-11-22T00:00:00+00:00",
        "valid_until": "2026-11-22T00:00:00+00:00",
        "missing_record_ids": [],
    }],
    ROUTE_SOURCE_ID: [
        {"timestamp": "2026-11-21T00:10:00+00:00", "route_id": "SYN-BASE", "route_version": "v1", "approved": True,
         "operations": ["ETCH", "CLEAN"], "allowed_sequences": [["ETCH", "CMP", "CLEAN"]]},
        {"timestamp": "2026-11-21T00:10:00+00:00", "route_id": "SYN-REWORK", "route_version": "v2", "approved": True,
         "operations": ["ETCH"], "allowed_sequences": []},
    ],
    ROUTE_COVERAGE_SOURCE_ID: [{
        "record_id": "SYN-ROUTE-COV-1", "timestamp": "2026-11-21T00:15:00+00:00", "complete": True,
        "covered_wafer_ids": ["SYN-W1", "SYN-W2", "SYN-W3", "SYN-W4"],
        "covered_lot_ids": ["SYN-LOT-OLD", "SYN-LOT-2", "SYN-LOT-3", "SYN-LOT-4"], "covered_operation_ids": ["ETCH", "CLEAN", "CMP"],
        "population_kind": "WAFER", "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION",
        "covered_source_ids": [SOURCE_ID, ROUTE_SOURCE_ID], "source_ids": [ROUTE_COVERAGE_SOURCE_ID],
        "window_start": "2026-11-21T00:00:00+00:00", "window_end": "2026-11-22T00:00:00+00:00",
        "valid_until": "2026-11-22T00:00:00+00:00",
        "missing_record_ids": [],
    }],
    MATERIAL_SOURCE_ID: [{
        "record_id": "SYN-MEM-W1-A", "relationship_type": "LOT_MEMBERSHIP",
        "from_entity": {"id": "SYN-LOT-NEW", "type": "lot"},
        "to_entity": {"id": "SYN-W1", "type": "wafer"},
        "from_entity_id": "SYN-LOT-NEW", "from_entity_type": "lot",
        "to_entity_id": "SYN-W1", "to_entity_type": "wafer",
        "timestamp": "2026-11-21T04:00:00+00:00",
        "effective_start": "2026-11-21T03:00:00+00:00", "effective_end": "2026-11-21T07:00:00+00:00",
        "observed_at": "2026-11-21T04:00:00+00:00",
        "key_values": {"record_id": "SYN-MEM-W1-A", "from_entity_id": "SYN-LOT-NEW", "from_entity_type": "lot", "to_entity_id": "SYN-W1", "to_entity_type": "wafer", "timestamp": "2026-11-21T04:00:00+00:00"},
    }],
}


def _aliased_engineer_100_sources(source_definitions, source_relationships, data_rows,
                                  *, schema_variant="fabx"):
    """Return a second physical schema over the same fixed-answer 100-wafer data."""
    source_aliases = {
        SOURCE_ID: "FABX_PROCESS_LEDGER_V7",
        OUTCOME_SOURCE_ID: "FABX_WAFER_RESULTS_V2",
        COVERAGE_SOURCE_ID: "FABX_EXPOSURE_COVERAGE_V1",
        HISTORY_COVERAGE_SOURCE_ID: "FABX_HISTORY_COVERAGE_V3",
        ROUTE_SOURCE_ID: "FABX_ROUTE_CATALOG_V5",
        ROUTE_COVERAGE_SOURCE_ID: "FABX_ROUTE_COVERAGE_V2",
        MATERIAL_SOURCE_ID: "FABX_MATERIAL_EDGES_V4",
    }
    relation_aliases = {
        RELATIONSHIP_ID: "FABX_REL_PROCESS_STEP",
        OUTCOME_RELATIONSHIP_ID: "FABX_REL_WAFER_RESULT",
        COVERAGE_RELATIONSHIP_ID: "FABX_REL_EXPOSURE_SCOPE",
        HISTORY_COVERAGE_RELATIONSHIP_ID: "FABX_REL_HISTORY_SCOPE",
        ROUTE_RELATIONSHIP_ID: "FABX_REL_ROUTE_VERSION",
        ROUTE_COVERAGE_RELATIONSHIP_ID: "FABX_REL_ROUTE_SCOPE",
        MATERIAL_RELATIONSHIP_ID: "FABX_REL_TIME_SCOPED_MEMBERSHIP",
    }
    fields_by_source = {
        SOURCE_ID: {
            "wafer_id": "wafer_identifier", "step_instance_id": "step_occurrence_id",
            "operation": "operation_performed", "timestamp": "processed_timestamp",
            "recorded_at": "received_timestamp", "time_uncertainty_seconds": "clock_error_seconds",
            "lot_id": "lot_identifier", "tool_id": "equipment_identifier",
            "chamber_id": "chamber_asset", "rework_of_step_instance_id": "rework_parent_step",
            "route_id": "route_identifier", "route_version": "route_version_identifier",
        },
        OUTCOME_SOURCE_ID: {
            "wafer_id": "wafer_identifier", "outcome_id": "result_record_id",
            "timestamp": "result_timestamp", "label": "result_state", "product_id": "product_identifier",
        },
        COVERAGE_SOURCE_ID: {
            "record_id": "coverage_record_id", "timestamp": "captured_timestamp",
            "complete": "is_complete", "covered_wafer_ids": "wafer_scope_ids",
            "covered_lot_ids": "lot_scope_ids", "covered_operation_ids": "operation_scope_ids",
            "population_kind": "population_grain", "source_authority_claim": "authority_claim",
            "covered_source_ids": "covered_sources", "source_ids": "descriptor_sources",
            "window_start": "scope_start", "window_end": "scope_end",
            "valid_until": "scope_expiry", "missing_record_ids": "missing_record_refs",
        },
        HISTORY_COVERAGE_SOURCE_ID: {
            "record_id": "history_coverage_record_id", "timestamp": "observed_timestamp",
            "complete": "is_complete", "covered_wafer_ids": "wafer_scope_ids",
            "covered_lot_ids": "lot_scope_ids", "covered_operation_ids": "operation_scope_ids",
            "population_kind": "population_grain", "source_authority_claim": "authority_claim",
            "covered_source_ids": "covered_sources", "source_ids": "descriptor_sources",
            "window_start": "scope_start", "window_end": "scope_end",
            "valid_until": "scope_expiry", "missing_record_ids": "missing_record_refs",
        },
        ROUTE_SOURCE_ID: {
            "timestamp": "definition_recorded_at", "route_id": "route_identifier",
            "route_version": "version_identifier", "approved": "is_approved",
            "operations": "ordered_operation_codes", "allowed_sequences": "valid_alternatives",
        },
        ROUTE_COVERAGE_SOURCE_ID: {
            "record_id": "route_coverage_record_id", "timestamp": "observed_timestamp",
            "complete": "is_complete", "covered_wafer_ids": "wafer_scope_ids",
            "covered_lot_ids": "lot_scope_ids", "covered_operation_ids": "operation_scope_ids",
            "population_kind": "population_grain", "source_authority_claim": "authority_claim",
            "covered_source_ids": "covered_sources", "source_ids": "descriptor_sources",
            "window_start": "scope_start", "window_end": "scope_end",
            "valid_until": "scope_expiry", "missing_record_ids": "missing_record_refs",
        },
        MATERIAL_SOURCE_ID: {
            "record_id": "membership_record_id", "relationship_type": "edge_kind",
            "from_entity_id": "parent_lot_identifier", "from_entity_type": "parent_entity_kind",
            "to_entity_id": "member_wafer_identifier", "to_entity_type": "member_entity_kind",
            "timestamp": "source_observed_at", "effective_start": "valid_from",
            "effective_end": "valid_to", "observed_at": "record_arrived_at",
            "key_values": "source_key_values",
        },
    }
    if schema_variant == "alternate":
        source_aliases = {
            SOURCE_ID: "PLANT7_ACTUAL_RUNS",
            OUTCOME_SOURCE_ID: "QDATA_WAFER_RESULTS",
            COVERAGE_SOURCE_ID: "TRACE_EXPOSURE_COVERAGE",
            HISTORY_COVERAGE_SOURCE_ID: "TRACE_HISTORY_COVERAGE",
            ROUTE_SOURCE_ID: "ROUTE_BOOK_V6",
            ROUTE_COVERAGE_SOURCE_ID: "TRACE_ROUTE_COVERAGE",
            MATERIAL_SOURCE_ID: "LOT_WAFER_LINEAGE",
        }
        relation_aliases = {
            RELATIONSHIP_ID: "PLANT7_REL_ACTUAL_RUN",
            OUTCOME_RELATIONSHIP_ID: "QDATA_REL_WAFER_RESULT",
            COVERAGE_RELATIONSHIP_ID: "TRACE_REL_EXPOSURE_SCOPE",
            HISTORY_COVERAGE_RELATIONSHIP_ID: "TRACE_REL_HISTORY_SCOPE",
            ROUTE_RELATIONSHIP_ID: "ROUTE_REL_VERSIONED_DEFINITION",
            ROUTE_COVERAGE_RELATIONSHIP_ID: "TRACE_REL_ROUTE_SCOPE",
            MATERIAL_RELATIONSHIP_ID: "LINEAGE_REL_EFFECTIVE_MEMBERSHIP",
        }
        fields_by_source = {
            SOURCE_ID: {
                "wafer_id": "substrate_tag", "step_instance_id": "run_occurrence",
                "operation": "actual_operation_code", "timestamp": "run_completed_utc",
                "recorded_at": "record_received_utc", "time_uncertainty_seconds": "clock_uncertainty_s",
                "lot_id": "batch_identifier", "tool_id": "equipment_asset_ref",
                "chamber_id": "module_identifier", "rework_of_step_instance_id": "rework_predecessor",
                "route_id": "route_code", "route_version": "route_revision",
            },
            OUTCOME_SOURCE_ID: {
                "wafer_id": "substrate_tag", "outcome_id": "inspection_record",
                "timestamp": "measured_at_utc", "label": "result_class", "product_id": "product_family",
            },
            COVERAGE_SOURCE_ID: {
                "record_id": "scope_record", "timestamp": "reviewed_at_utc",
                "complete": "all_rows_present", "covered_wafer_ids": "wafer_scope",
                "covered_lot_ids": "lot_scope", "covered_operation_ids": "process_scope",
                "population_kind": "scope_grain", "source_authority_claim": "authority_source",
                "covered_source_ids": "covered_source_ids", "source_ids": "source_refs",
                "window_start": "valid_from_utc", "window_end": "valid_to_utc",
                "valid_until": "valid_until_utc", "missing_record_ids": "known_gaps",
            },
            HISTORY_COVERAGE_SOURCE_ID: {
                "record_id": "history_scope_record", "timestamp": "observed_at_utc",
                "complete": "all_rows_present", "covered_wafer_ids": "wafer_scope",
                "covered_lot_ids": "lot_scope", "covered_operation_ids": "process_scope",
                "population_kind": "scope_grain", "source_authority_claim": "authority_source",
                "covered_source_ids": "covered_source_ids", "source_ids": "source_refs",
                "window_start": "valid_from_utc", "window_end": "valid_to_utc",
                "valid_until": "valid_until_utc", "missing_record_ids": "known_gaps",
            },
            ROUTE_SOURCE_ID: {
                "timestamp": "route_recorded_at", "route_id": "flow_code",
                "route_version": "flow_revision", "approved": "approved_by_source",
                "operations": "operation_sequence", "allowed_sequences": "alternate_sequences",
            },
            ROUTE_COVERAGE_SOURCE_ID: {
                "record_id": "route_scope_record", "timestamp": "observed_at_utc",
                "complete": "all_rows_present", "covered_wafer_ids": "wafer_scope",
                "covered_lot_ids": "lot_scope", "covered_operation_ids": "process_scope",
                "population_kind": "scope_grain", "source_authority_claim": "authority_source",
                "covered_source_ids": "covered_source_ids", "source_ids": "source_refs",
                "window_start": "valid_from_utc", "window_end": "valid_to_utc",
                "valid_until": "valid_until_utc", "missing_record_ids": "known_gaps",
            },
            MATERIAL_SOURCE_ID: {
                "record_id": "membership_record", "relationship_type": "edge_type",
                "from_entity_id": "parent_id", "from_entity_type": "parent_type",
                "to_entity_id": "member_id", "to_entity_type": "member_type",
                "timestamp": "source_seen_utc", "effective_start": "membership_effective_from",
                "effective_end": "membership_effective_to", "observed_at": "arrival_time",
                "key_values": "source_key_values",
            },
        }
    elif schema_variant != "fabx":
        raise ValueError("Unknown synthetic alias schema variant.")
    definitions = copy.deepcopy(source_definitions)
    relationships = copy.deepcopy(source_relationships)
    rows_by_source = copy.deepcopy(data_rows)
    source_hashes = {}
    aliased_definitions = {}
    aliased_relationships = {}
    aliased_rows = {}

    for source_id, original in definitions.items():
        physical_id = source_aliases[source_id]
        spec = copy.deepcopy(original)
        spec["column_definitions"] = {
            fields_by_source[source_id].get(name, name): definition
            for name, definition in spec["column_definitions"].items()
        }
        hash_input = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
        source_hash = hashlib.sha256(hash_input).hexdigest()
        spec["source_hash"] = source_hash
        source_hashes[physical_id] = source_hash
        aliased_definitions[physical_id] = spec

        aliased_rows[physical_id] = []
        for original_row in rows_by_source[source_id]:
            row = {
                fields_by_source[source_id].get(name, name): value
                for name, value in original_row.items()
            }
            for logical_key in ("covered_source_ids", "source_ids"):
                key = fields_by_source[source_id].get(logical_key, logical_key)
                values = row.get(key)
                if isinstance(values, list):
                    row[key] = [source_aliases.get(value, value) for value in values]
            if "source_key_values" in row and isinstance(row["source_key_values"], dict):
                row["source_key_values"] = {
                    fields_by_source[source_id].get(name, name): value
                    for name, value in row["source_key_values"].items()
                }
            aliased_rows[physical_id].append(row)

    for relation_id, original in relationships.items():
        relation = copy.deepcopy(original)
        source_id = original["source_ids"][0]
        physical_source = source_aliases[source_id]
        relation["source_ids"] = [physical_source]
        relation["keys"] = [fields_by_source[source_id].get(key, key) for key in relation["keys"]]
        aliased_relationships[relation_aliases[relation_id]] = relation

    return aliased_definitions, aliased_relationships, aliased_rows

FOLLOWUP_MATERIAL_ROW = {
    "record_id": "SYN-MEM-W1-B", "relationship_type": "LOT_MEMBERSHIP",
    "from_entity": {"id": "SYN-LOT-ALTERNATE", "type": "lot"},
    "to_entity": {"id": "SYN-W1", "type": "wafer"},
    "from_entity_id": "SYN-LOT-ALTERNATE", "from_entity_type": "lot",
    "to_entity_id": "SYN-W1", "to_entity_type": "wafer",
    "timestamp": "2026-11-21T04:30:00+00:00",
    "effective_start": "2026-11-21T03:00:00+00:00", "effective_end": "2026-11-21T07:00:00+00:00",
    "observed_at": "2026-11-21T04:30:00+00:00",
    "key_values": {"record_id": "SYN-MEM-W1-B", "from_entity_id": "SYN-LOT-ALTERNATE", "from_entity_type": "lot", "to_entity_id": "SYN-W1", "to_entity_type": "wafer", "timestamp": "2026-11-21T04:30:00+00:00"},
}

LEGACY_PROCESS_ROWS = [
    {"wafer_id": "SYN-W1", "step_instance_id": "SYN-S1", "operation": "ETCH", "lot_id": "SYN-LOT-1", "tool_id": "SYN-T1", "chamber_id": "SYN-C1", "timestamp": "2026-11-21T03:00:00+00:00", "rework_of_step_instance_id": None, "route_id": None, "route_version": None},
    {"wafer_id": "SYN-W2", "step_instance_id": "SYN-S2", "operation": "ETCH", "lot_id": "SYN-LOT-2", "tool_id": "SYN-T1", "chamber_id": "SYN-C2", "timestamp": "2026-11-21T04:00:00+00:00", "rework_of_step_instance_id": None, "route_id": None, "route_version": None},
    {"wafer_id": "SYN-W3", "step_instance_id": "SYN-S3", "operation": "CMP", "lot_id": "SYN-LOT-3", "tool_id": None, "chamber_id": None, "timestamp": "2026-11-21T05:00:00+00:00", "rework_of_step_instance_id": None, "route_id": None, "route_version": None},
]


def build_server(state: FixtureState, tool_prefix: str = "") -> MCPServer:
    server = MCPServer(
        name="p2-synthetic-readonly-mock",
        version="1.0.0",
        description="Synthetic P2 compatibility fixture. Read only; no company endpoints or data.",
    )
    readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(name=f"{tool_prefix}discover", description="Discover synthetic read-only logical capabilities and bounds.", annotations=readonly, structured_output=True)
    def discover() -> dict[str, Any]:
        return {
            "capabilities": ["discover", "semantics", "relationships", "read_bounded", "cancel", "audit"],
            "tool_versions": {f"{tool_prefix}{name}": "1.0.0" for name in ("discover", "semantics", "relationships", "read_bounded", "cancel", "audit")},
            "semantic_versions": [SEMANTIC_VERSION],
            "source_catalog": [{"source_id": source_id,
                                "semantic_version": state.source_definitions[source_id].get("semantic_version", SEMANTIC_VERSION)}
                               for source_id in sorted(state.source_definitions)],
            "limits": dict(state.limits),
            "auth_scopes": [READ_SCOPE],
            "audit_support": True,
            "mode": "SYNTHETIC_DEMO",
        }

    @server.tool(name=f"{tool_prefix}semantics", description="Read synthetic source semantics.", annotations=readonly, structured_output=True)
    def semantics(source_ids: list[str], semantic_version: str | None = None) -> dict[str, Any]:
        if not source_ids or any(source_id not in state.source_definitions for source_id in source_ids):
            raise ToolError("PERMISSION_DENIED")
        if semantic_version not in (None, SEMANTIC_VERSION):
            raise ToolError("SEMANTIC_VERSION_UNAVAILABLE")
        # Metadata inspection is allowed to batch large catalogs. Accumulate
        # IDs across this session so the subsequent relationship request can
        # refer to the complete discovered set without weakening unknown-ID
        # denial (each ID still must exist in the catalog above).
        state.semantics_requested.update(source_ids)
        sources = [{
            "source_id": source_id,
            **({"source_name": spec["source_name"]} if isinstance(spec.get("source_name"), str) else {}),
            "record_kind": spec["record_kind"],
            "approved": True,
            "semantic_version": spec.get("semantic_version", SEMANTIC_VERSION),
            "source_hash": spec["source_hash"],
            "grain": spec["grain"],
            "column_definitions": spec["column_definitions"],
            "units": {},
            "effectivity": {"start": state.time_start, "end": state.time_end},
            "approval": "SYNTHETIC_ONLY",
        } for source_id, spec in state.source_definitions.items() if source_id in source_ids]
        if state.mutate == "duplicate_semantics_source":
            source = next(item for item in sources if item["source_id"] == SOURCE_ID)
            return {"sources": [source, {**source, "source_hash": "d" * 64}]}
        return {"sources": sources}

    @server.tool(name=f"{tool_prefix}relationships", description="Read explicitly declared synthetic relationships.", annotations=readonly, structured_output=True)
    def relationships(entity_refs: list[dict[str, Any]], time_window: dict[str, str]) -> dict[str, Any]:
        start, end = _as_utc(time_window.get("start", "")), _as_utc(time_window.get("end", ""))
        if end <= start:
            raise ToolError("INVALID_TIME_WINDOW")
        if any(ref.get("source_id") not in (None, *state.semantics_requested) for ref in entity_refs):
            raise ToolError("PERMISSION_DENIED")
        requested_sources = {ref.get("source_id") for ref in entity_refs if ref.get("source_id")}
        if not requested_sources:
            requested_sources = set(state.semantics_requested)
        relations = []
        for relation_id, spec in state.source_relationships.items():
            source_id = spec["source_ids"][0]
            if source_id not in state.semantics_requested or source_id not in requested_sources:
                continue
            relation = {
                "id": relation_id,
                "approved": True,
                "source_ids": list(spec["source_ids"]),
                "keys": list(spec["keys"]),
                "cardinality": spec["cardinality"],
                "grain": spec["grain"],
                **({"relationship_type": spec["relationship_type"]} if "relationship_type" in spec else {}),
                "effective_start": state.time_start,
                "effective_end": state.time_end,
                "source_reference": {
                    "source_ids": [source_id],
                    "source_hash": state.source_definitions[source_id]["source_hash"],
                    "semantic_version": state.source_definitions[source_id].get("semantic_version", SEMANTIC_VERSION),
                },
            }
            if relation_id == RELATIONSHIP_ID and state.mutate == "relationship_time_key":
                relation["keys"].remove("timestamp")
            if relation_id == RELATIONSHIP_ID and state.mutate == "undeclared_relation_key":
                relation["keys"].append("unmodeled_join_field")
            if relation_id == RELATIONSHIP_ID and state.mutate == "relationship_hash":
                relation["source_reference"]["source_hash"] = "d" * 64
            relations.append(relation)
            if relation_id == RELATIONSHIP_ID and state.mutate == "duplicate_relationship_id":
                return {"relationships": [relation, {**relation, "keys": ["timestamp"]}]}
        if any(ref.get("relationship_id") == "SYN_UNAPPROVED" for ref in entity_refs):
            return {"relationships": [*relations, {**relations[0], "id": "SYN_UNAPPROVED", "approved": False}]}
        return {"relationships": relations}

    @server.tool(name=f"{tool_prefix}read_bounded", description="Read synthetic process rows under server-enforced scope and limits.", annotations=readonly, structured_output=True)
    async def read_bounded(approved_plan: dict[str, Any], permission_context: str, limits: dict[str, Any], operation_id: str) -> dict[str, Any]:
        if permission_context != READ_SCOPE:
            raise ToolError("PERMISSION_DENIED")
        sources = approved_plan.get("source_ids")
        relation_ids = approved_plan.get("relationship_ids")
        window = approved_plan.get("time_window", {})
        time_field = approved_plan.get("time_field")
        if (not isinstance(sources, list) or len(sources) != 1
                or sources[0] not in state.source_definitions
                or not isinstance(relation_ids, list) or len(relation_ids) != 1
                or not isinstance(time_field, str) or not time_field):
            raise ToolError("PERMISSION_DENIED")
        source_id = sources[0]
        relation_id = relation_ids[0]
        if (relation_id not in state.source_relationships
                or state.source_relationships[relation_id]["source_ids"] != [source_id]
                or source_id not in state.semantics_requested):
            raise ToolError("PERMISSION_DENIED")
        source_spec = state.source_definitions[source_id]
        time_column = source_spec["column_definitions"].get(time_field)
        expected_time_meaning = {
            "PROCESS_STEP_INSTANCE": "event time",
            "WAFER_OUTCOME": "outcome time",
            "EXPOSURE_COVERAGE": "source observation time",
            "PROCESS_HISTORY_COVERAGE": "source observation time",
            "ROUTE_DEFINITION": "route definition record time",
            "ROUTE_COVERAGE": "source observation time",
            "MATERIAL_RELATIONSHIP": "source observation time",
        }.get(source_spec.get("record_kind"))
        if (not isinstance(time_column, dict) or time_column.get("type") != "timestamp"
                or time_column.get("timezone_required") is not True
                or not expected_time_meaning
                or expected_time_meaning not in str(time_column.get("meaning", "")).casefold()
                or time_field not in state.source_relationships[relation_id]["keys"]):
            raise ToolError("PERMISSION_DENIED")
        filters = approved_plan.get("filters", {})
        allowed_filter_keys = set(state.source_relationships[relation_id]["keys"])
        if not isinstance(filters, dict) or not set(filters).issubset(allowed_filter_keys):
            raise ToolError("FILTER_NOT_APPROVED_BY_RELATIONSHIP")
        normalized_filters = {}
        for field, raw_value in filters.items():
            values = [raw_value] if isinstance(raw_value, str) else raw_value
            if (not isinstance(values, list) or not values
                    or any(not isinstance(value, str) or not value for value in values)
                    or len(values) != len(set(values))):
                raise ToolError("INVALID_FILTER")
            normalized_filters[field] = values
        try:
            start, end = _as_utc(window.get("start", "")), _as_utc(window.get("end", ""))
        except (ValueError, AttributeError) as exc:
            raise ToolError("INVALID_TIME_WINDOW") from exc
        if end <= start or start < _as_utc(state.time_start) or end > _as_utc(state.time_end):
            raise ToolError("INVALID_TIME_WINDOW")
        max_rows = limits.get("max_rows")
        max_bytes = limits.get("max_bytes")
        max_seconds = limits.get("max_seconds")
        if not isinstance(max_rows, int) or not 1 <= max_rows <= state.limits["max_rows"]:
            raise ToolError("QUERY_LIMIT_EXCEEDED")
        if not isinstance(max_bytes, int) or not 1024 <= max_bytes <= state.limits["max_bytes"]:
            raise ToolError("QUERY_LIMIT_EXCEEDED")
        if not isinstance(max_seconds, (int, float)) or not 0 < max_seconds <= state.limits["max_seconds"]:
            raise ToolError("QUERY_LIMIT_EXCEEDED")
        try:
            operation_id = str(uuid.UUID(operation_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ToolError("INVALID_OPERATION_ID") from exc
        cancel_event, _stopped_event = state.begin(operation_id)
        started = time.monotonic()
        try:
            deadline = started + min(float(max_seconds), float(state.limits["max_seconds"]))
            read_delay_ms = state.delay_ms
            if state.scenario == "engineer-followup" and not normalized_filters:
                read_delay_ms = 0
            while read_delay_ms and time.monotonic() < started + read_delay_ms / 1000:
                if cancel_event.is_set():
                    return {"cancelled": True}
                if time.monotonic() >= deadline:
                    raise ToolError("QUERY_TIMEOUT")
                await asyncio.sleep(0.01)
            selected = []
            source_rows = state.data_rows[source_id]
            if source_id == SOURCE_ID and state.scenario == "legacy":
                source_rows = LEGACY_PROCESS_ROWS
            if (source_id == MATERIAL_SOURCE_ID and state.scenario == "engineer-followup"
                    and normalized_filters.get("to_entity_id") == ["SYN-W1"]):
                source_rows = [*source_rows, FOLLOWUP_MATERIAL_ROW]
            if (source_id == MATERIAL_SOURCE_ID and state.scenario == "engineer-100-followup"
                    and normalized_filters.get("to_entity_id") == ["SYN-EW-010"]):
                extra_membership = {
                    "record_id": "SYN-MEM-010-C", "relationship_type": "LOT_MEMBERSHIP",
                    "from_entity": {"id": "SYN-LOT-01C", "type": "lot"},
                    "to_entity": {"id": "SYN-EW-010", "type": "wafer"},
                    "from_entity_id": "SYN-LOT-01C", "from_entity_type": "lot",
                    "to_entity_id": "SYN-EW-010", "to_entity_type": "wafer",
                    "timestamp": "2026-11-21T02:20:00+00:00",
                    "effective_start": "2026-11-21T02:00:00+00:00",
                    "effective_end": "2026-11-21T03:00:00+00:00",
                    "observed_at": "2026-11-22T11:00:00+00:00",
                    "key_values": {"record_id": "SYN-MEM-010-C", "from_entity_id": "SYN-LOT-01C",
                                   "from_entity_type": "lot", "to_entity_id": "SYN-EW-010",
                                   "to_entity_type": "wafer", "timestamp": "2026-11-21T02:20:00+00:00"},
                }
                source_rows = [*source_rows, extra_membership]
            if (source_id == "FABX_MATERIAL_EDGES_V4"
                    and state.scenario == "engineer-100-alias-followup"
                    and normalized_filters.get("member_wafer_identifier") == ["SYN-EW-010"]):
                extra_alias_membership = {
                    "membership_record_id": "SYN-MEM-010-C",
                    "edge_kind": "LOT_MEMBERSHIP",
                    "parent_lot_identifier": "SYN-LOT-01C",
                    "parent_entity_kind": "lot",
                    "member_wafer_identifier": "SYN-EW-010",
                    "member_entity_kind": "wafer",
                    "source_observed_at": "2026-11-21T02:20:00+00:00",
                    "valid_from": "2026-11-21T02:00:00+00:00",
                    "valid_to": "2026-11-21T03:00:00+00:00",
                    "record_arrived_at": "2026-11-22T11:00:00+00:00",
                    "source_key_values": {
                        "membership_record_id": "SYN-MEM-010-C",
                        "parent_lot_identifier": "SYN-LOT-01C", "parent_entity_kind": "lot",
                        "member_wafer_identifier": "SYN-EW-010", "member_entity_kind": "wafer",
                        "source_observed_at": "2026-11-21T02:20:00+00:00",
                        "valid_from": "2026-11-21T02:00:00+00:00",
                        "valid_to": "2026-11-21T03:00:00+00:00",
                        "record_arrived_at": "2026-11-22T11:00:00+00:00",
                    },
                }
                source_rows = [*source_rows, extra_alias_membership]
            if (source_id == "LOT_WAFER_LINEAGE"
                    and state.scenario in {"engineer-100-alt-alias-followup",
                                           "engineer-100-alt-alias-13k-followup"}
                    and normalized_filters.get("member_id") == ["SYN-EW-010"]):
                source_rows = [*source_rows, {
                    "membership_record": "SYN-MEM-010-C",
                    "edge_type": "LOT_MEMBERSHIP",
                    "parent_id": "SYN-LOT-01C", "parent_type": "lot",
                    "member_id": "SYN-EW-010", "member_type": "wafer",
                    "source_seen_utc": "2026-11-21T02:20:00+00:00",
                    "membership_effective_from": "2026-11-21T02:00:00+00:00",
                    "membership_effective_to": "2026-11-21T03:00:00+00:00",
                    "arrival_time": "2026-11-22T11:00:00+00:00",
                    "source_key_values": {
                        "membership_record": "SYN-MEM-010-C", "parent_id": "SYN-LOT-01C",
                        "parent_type": "lot", "member_id": "SYN-EW-010", "member_type": "wafer",
                        "source_seen_utc": "2026-11-21T02:20:00+00:00",
                        "membership_effective_from": "2026-11-21T02:00:00+00:00",
                        "membership_effective_to": "2026-11-21T03:00:00+00:00",
                        "arrival_time": "2026-11-22T11:00:00+00:00",
                    },
                }]
            if any(not isinstance(row.get(time_field), str) for row in source_rows):
                raise ToolError("MISSING_APPROVED_TIME_FIELD")
            matches = [row for row in source_rows if start <= _as_utc(row[time_field]) < end]
            for field, accepted_values in normalized_filters.items():
                matches = [row for row in matches if row.get(field) in accepted_values]
            truncated = False
            for row in matches:
                if cancel_event.is_set():
                    return {"cancelled": True}
                typed = {**row, "source_id": source_id, "relationship_id": relation_id,
                         "grain": source_spec["grain"], "source_version": SEMANTIC_VERSION}
                candidate = [*selected, typed]
                preview = {"typed_rows": candidate}
                size = len(json.dumps(preview, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                if len(candidate) > max_rows or size > max_bytes:
                    truncated = True
                    break
                selected.append(typed)
            query = {"approved_plan": approved_plan, "permission_context": permission_context, "limits": limits}
            query_hash = operation_hash(query)
            out = {
                "operation_id": operation_id,
                "audit_id": "SYN-AUDIT-" + operation_id,
                "query_hash": query_hash,
                "typed_rows": selected,
                "row_grain": source_spec["grain"],
                "source_ids": [source_id] if selected else [],
                "relationship_ids": [relation_id] if selected else [],
                "source_versions": {source_id: SEMANTIC_VERSION} if selected else {},
                "truncated": truncated,
                "query_window": {"start": window["start"], "end": window["end"]},
                "permission_scope": permission_context,
            }
            if state.mutate == "grain":
                out["typed_rows"][0]["grain"] = "one wafer"
            elif state.mutate == "time":
                out["typed_rows"][0]["timestamp"] = "2026-11-21T03:00:00"
            elif state.mutate == "provenance":
                out["typed_rows"][0]["relationship_id"] = "SYN_UNAPPROVED"
            elif state.mutate == "source_version":
                out["typed_rows"][0]["source_version"] = "SYN-OLD"
            elif state.mutate == "source_ids":
                out["source_ids"] = ["SYN_OTHER"]
            elif state.mutate == "omit_source_references":
                out["source_ids"] = []
                out["source_versions"] = {}
            elif state.mutate == "omit_relationship_references":
                out["relationship_ids"] = []
            elif state.mutate == "audit_hash":
                out["query_hash"] = "f" * 64
            elif state.mutate == "oversize":
                out["oversized_note"] = "x" * (max_bytes + 10)
            if state.mutate != "oversize":
                while len(json.dumps(out, sort_keys=True, separators=(",", ":")).encode("utf-8")) > max_bytes and out["typed_rows"]:
                    out["typed_rows"].pop()
                    out["truncated"] = True
                    if out["typed_rows"]:
                        out["source_ids"] = [source_id]
                        out["relationship_ids"] = [relation_id]
                        out["source_versions"] = {source_id: SEMANTIC_VERSION}
                    else:
                        out["source_ids"] = []
                        out["relationship_ids"] = []
                        out["source_versions"] = {}
                if len(json.dumps(out, sort_keys=True, separators=(",", ":")).encode("utf-8")) > max_bytes:
                    raise ToolError("QUERY_LIMIT_EXCEEDED")
            selected = out["typed_rows"]
            audit_sources = [{"source_id": source_id, "semantic_version": SEMANTIC_VERSION,
                              "source_hash": source_spec["source_hash"]}] if selected else []
            state.finish(operation_id, {
                "permission_scope": permission_context, "sources": audit_sources,
                "timestamps": {"start": window["start"], "end": window["end"]},
                "query_hash": query_hash,
            })
            if time.monotonic() > deadline:
                raise ToolError("QUERY_TIMEOUT")
            return out
        finally:
            state.finish(operation_id)

    @server.tool(name=f"{tool_prefix}cancel", description="Cancel a currently active synthetic bounded read.", annotations=readonly, structured_output=True)
    async def cancel(operation_id: str) -> dict[str, Any]:
        try:
            operation_id = str(uuid.UUID(operation_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ToolError("INVALID_OPERATION_ID") from exc
        return {"confirmed_stopped": await asyncio.to_thread(state.cancel, operation_id)}

    @server.tool(name=f"{tool_prefix}audit", description="Read the synthetic audit record for a completed operation.", annotations=readonly, structured_output=True)
    def audit(operation_id: str) -> dict[str, Any]:
        record = state.audit_for(operation_id)
        if record is None:
            raise ToolError("AUDIT_NOT_FOUND")
        if state.mutate == "audit_scope":
            record = {**record, "permission_scope": "SYNTHETIC_ADMIN"}
        if state.mutate == "audit_time":
            record = {**record, "timestamps": {"start": "2026-11-21T00:00:00+00:00", "end": "2026-11-23T00:00:00+00:00"}}
        return record

    return server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay-ms", type=int, default=int(os.environ.get("P2_FIXTURE_READ_DELAY_MS", "0")))
    parser.add_argument("--mutate", choices=("grain", "time", "provenance", "source_version", "source_ids", "omit_source_references", "omit_relationship_references", "relationship_time_key", "undeclared_relation_key", "duplicate_relationship_id", "duplicate_semantics_source", "audit_hash", "oversize", "audit_scope", "audit_time", "relationship_hash"))
    parser.add_argument("--scenario", choices=("legacy", "engineer-complete", "engineer-followup", "engineer-100", "engineer-100-followup", "engineer-100-alias", "engineer-100-alias-followup", "engineer-100-alt-alias", "engineer-100-alt-alias-followup", "engineer-100-alt-alias-13k", "engineer-100-alt-alias-13k-followup"), default="legacy")
    parser.add_argument("--descriptor-topology", choices=("standard", "arrival-time-only",
                        "static-membership", "missing-event-relationship-key",
                        "equipment-group-only", "duplicate-event-version",
                        "combined-untyped-process-outcome"), default="standard")
    parser.add_argument("--tool-prefix", default="")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    fixture_state = FixtureState(args.delay_ms, args.mutate, args.scenario, args.descriptor_topology)
    server = build_server(fixture_state, args.tool_prefix)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=args.host, port=args.port, streamable_http_path="/mcp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
