"""Offline, non-authorizing MCP descriptor mapping proposals for P2."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


_OPERATION_REQUIRED = {
    "discover": set(),
    "semantics": {"source_ids"},
    "relationships": {"entity_refs", "time_window"},
    "read_bounded": {"approved_plan", "permission_context", "limits", "operation_id"},
    "cancel": {"operation_id"},
    "audit": {"operation_id"},
}
_OPERATION_CUES = {
    "discover": ("discover", "capabilit"),
    "semantics": ("semantic", "source definition"),
    "relationships": ("relationship", "join"),
    "read_bounded": ("bounded", "read"),
    "cancel": ("cancel", "stop"),
    "audit": ("audit", "trace"),
}
_INPUT_TYPES = {
    "source_ids": "array", "entity_refs": "array", "time_window": "object",
    "approved_plan": "object", "permission_context": "string",
    "limits": "object", "operation_id": "string",
}
_ROLE_KIND = {
    "events": "PROCESS_STEP_INSTANCE",
    "outcomes": "WAFER_OUTCOME",
    "coverage": "EXPOSURE_COVERAGE",
    "history_coverage": "PROCESS_HISTORY_COVERAGE",
    "route_definitions": "ROUTE_DEFINITION",
    "route_coverage": "ROUTE_COVERAGE",
    "material_relationships": "MATERIAL_RELATIONSHIP",
}

# A journey can be useful when chamber or equipment observations are absent:
# B01 can still show the verified step identity and chronology while B02 must
# leave chamber exposure unknown.  The missing observation is surfaced in the
# proposal; it is never filled from a group identifier or a field name.
_REQUIRED_FIELDS = {
    "events": {"wafer_id", "step_instance_id", "event_time", "operation"},
    "outcomes": {"wafer_id", "outcome_label", "outcome_time"},
    "material_relationships": {
        "record_id", "from_entity_id", "from_entity_type", "to_entity_id",
        "to_entity_type", "effective_start", "effective_end", "observed_at",
    },
    "coverage": {"record_id", "complete", "covered_wafer_ids", "covered_lot_ids",
                  "covered_operation_ids", "covered_source_ids", "source_ids", "population_kind",
                  "source_authority_claim", "window_start", "window_end", "valid_until",
                  "record_time", "missing_record_ids"},
    "history_coverage": {"record_id", "complete", "covered_wafer_ids", "covered_lot_ids",
                         "covered_operation_ids", "covered_source_ids", "source_ids", "population_kind",
                         "source_authority_claim", "window_start", "window_end", "valid_until",
                         "record_time", "missing_record_ids"},
    "route_coverage": {"record_id", "complete", "covered_wafer_ids", "covered_lot_ids",
                       "covered_operation_ids", "covered_source_ids", "source_ids", "population_kind",
                       "source_authority_claim", "window_start", "window_end", "valid_until",
                       "record_time", "missing_record_ids"},
    "route_definitions": {"route_id", "route_version", "approved", "operations",
                          "record_time"},
}


def _aware_interval(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _tool_matches(tool: dict[str, Any], operation: str) -> bool:
    if not isinstance(tool.get("name"), str) or not isinstance(tool.get("description"), str):
        return False
    schema = tool.get("inputSchema", tool.get("input_schema"))
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return False
    required = schema.get("required", [])
    if (not isinstance(required, list) or any(not isinstance(item, str) for item in required)
            or set(required) != _OPERATION_REQUIRED[operation]):
        return False
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or any(
        not isinstance(properties.get(name), dict)
        or properties[name].get("type") != _INPUT_TYPES[name]
        for name in _OPERATION_REQUIRED[operation]
    ):
        return False
    annotations = tool.get("annotations")
    if not isinstance(annotations, dict):
        return False
    if annotations.get("readOnlyHint") is not True or annotations.get("destructiveHint") is not False:
        return False
    description = " ".join((tool.get("name", ""), tool.get("description", ""))).casefold()
    return all(cue in description for cue in _OPERATION_CUES[operation]) if operation == "read_bounded" else any(
        cue in description for cue in _OPERATION_CUES[operation]
    )


def _field_matches(definition: Any, *, entity: str | None = None, kind: str | None = None,
                   meaning: str | None = None, values: set[str] | None = None) -> bool:
    if not isinstance(definition, dict):
        return False
    if entity and definition.get("entity") != entity:
        return False
    if kind and definition.get("type") != kind:
        return False
    if kind == "timestamp" and definition.get("timezone_required") is not True:
        return False
    if meaning:
        declared = str(definition.get("meaning", "")).casefold()
        if meaning not in declared:
            return False
    if values:
        declared_values = definition.get("values")
        if (not isinstance(declared_values, list)
                or any(not isinstance(value, str) for value in declared_values)
                or not values.issubset(set(declared_values))):
            return False
    return True


def _valid_relationships(source: dict[str, Any], relationships: list[dict[str, Any]],
                         required_keys: set[str], relationship_type: str | None = None) -> list[dict[str, Any]]:
    result = []
    source_id = source.get("source_id")
    for relation in relationships:
        source_ids = relation.get("source_ids") if isinstance(relation, dict) else None
        keys = relation.get("keys") if isinstance(relation, dict) else None
        if (not isinstance(relation, dict) or relation.get("approved") is not True
                or not isinstance(source_ids, list) or any(not isinstance(item, str) for item in source_ids)
                or source_id not in source_ids or not isinstance(keys, list)
                or any(not isinstance(key, str) for key in keys)
                or not required_keys.issubset(set(keys))):
            continue
        if relationship_type and relation.get("relationship_type") != relationship_type:
            continue
        if not isinstance(relation.get("id"), str) or not relation["id"]:
            continue
        if (not isinstance(relation.get("cardinality"), str) or not relation["cardinality"]
                or not isinstance(relation.get("grain"), str) or not relation["grain"]):
            continue
        if not (_aware_interval(relation.get("effective_start"))
                and _aware_interval(relation.get("effective_end"))):
            continue
        start = datetime.fromisoformat(relation["effective_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(relation["effective_end"].replace("Z", "+00:00"))
        if end <= start:
            continue
        source_effectivity = source.get("effectivity", {})
        if (_aware_interval(source_effectivity.get("start"))
                and _aware_interval(source_effectivity.get("end"))):
            source_start = datetime.fromisoformat(source_effectivity["start"].replace("Z", "+00:00"))
            source_end = datetime.fromisoformat(source_effectivity["end"].replace("Z", "+00:00"))
            if end <= source_start or start >= source_end:
                continue
        reference = relation.get("source_reference")
        if (not isinstance(reference, dict)
                or reference.get("source_ids") != relation.get("source_ids")
                or reference.get("source_hash") != source.get("source_hash")
                or reference.get("semantic_version") != source.get("semantic_version")):
            continue
        result.append(relation)
    return result


def _role_candidate(role: str, source: dict[str, Any], relationships: list[dict[str, Any]]) -> dict[str, Any] | None:
    if source.get("record_kind") != _ROLE_KIND[role]:
        return None
    if source.get("approved") is not True:
        return {"role": role, "source_id": source.get("source_id"),
                "candidate_state": "SOURCE_NOT_MARKED_APPROVED",
                "requires_authorized_review": True}
    columns = source.get("column_definitions")
    source_effectivity = source.get("effectivity")
    if (not isinstance(columns, dict) or not isinstance(source.get("source_id"), str)
            or not isinstance(source.get("semantic_version"), str) or not source["semantic_version"]
            or not isinstance(source.get("grain"), str) or not source["grain"]
            or not isinstance(source.get("source_hash"), str)
            or len(source["source_hash"]) != 64
            or any(char not in "0123456789abcdef" for char in source["source_hash"].lower())
            or not isinstance(source_effectivity, dict)
            or not _aware_interval(source_effectivity.get("start"))
            or not _aware_interval(source_effectivity.get("end"))):
        return {"role": role, "source_id": source.get("source_id"),
                "candidate_state": "INVALID_SOURCE_DESCRIPTOR",
                "requires_authorized_review": True}
    source_start = datetime.fromisoformat(source_effectivity["start"].replace("Z", "+00:00"))
    source_end = datetime.fromisoformat(source_effectivity["end"].replace("Z", "+00:00"))
    if source_end <= source_start:
        return {"role": role, "source_id": source.get("source_id"),
                "candidate_state": "INVALID_SOURCE_EFFECTIVITY",
                "requires_authorized_review": True}

    def select(entity=None, kind=None, meaning=None, values=None):
        found = [name for name, definition in columns.items()
                 if isinstance(name, str) and _field_matches(
                     definition, entity=entity, kind=kind, meaning=meaning, values=values,
                 )]
        return found[0] if len(found) == 1 else None

    def select_meaning_cues(kind, cues):
        found = [name for name, definition in columns.items()
                 if isinstance(name, str) and isinstance(definition, dict)
                 and definition.get("type") == kind
                 and any(cue in str(definition.get("meaning", "")).casefold() for cue in cues)]
        return found[0] if len(found) == 1 else None

    def select_instance():
        found = [name for name, definition in columns.items()
                 if isinstance(name, str) and _field_matches(
                     definition, entity="process_step_instance", kind="identifier",
                 )]
        actual = [name for name in found
                  if any(cue in str(columns[name].get("meaning", "")).casefold()
                         for cue in ("actual operation instance", "actual step instance"))]
        if len(actual) == 1:
            return actual[0]
        return found[0] if len(found) == 1 else None

    fields: dict[str, str | None] = {}
    required: set[str] = set()
    required_relationship_keys: set[str] = set()
    relation_type = None
    time_field = None
    if role == "events":
        fields = {
            "wafer_id": select(entity="wafer", kind="identifier"),
            "step_instance_id": select_instance(),
            "event_time": select(kind="timestamp", meaning="event time"),
            "operation": select(entity="operation"),
            "tool_id": select(entity="tool", kind="identifier"),
            "chamber_id": select(entity="chamber", kind="identifier"),
            "lot_id": select(entity="lot", kind="identifier"),
            "recorded_at": select_meaning_cues(
                "timestamp", ("ingestion time", "record arrival time", "record time"),
            ),
            "time_uncertainty_seconds": select_meaning_cues(
                "number", ("event-time uncertainty", "clock error"),
            ),
            "rework_of_step_instance_id": select(entity="process_step_instance", kind="identifier",
                                                  meaning="prior step instance"),
            "route_id": select(entity="route", kind="identifier"),
            "route_version": select(entity="route_version", kind="identifier"),
        }
        required = {fields[name] for name in ("wafer_id", "step_instance_id", "event_time") if fields[name]}
        required_relationship_keys = set(required)
        time_field = fields["event_time"]
    elif role == "outcomes":
        fields = {
            "wafer_id": select(entity="wafer", kind="identifier"),
            "outcome_label": select(kind="enum", values={"ABNORMAL", "NORMAL"}),
            "outcome_time": select(kind="timestamp", meaning="outcome time"),
        }
        required = {value for value in fields.values() if value}
        required_relationship_keys = set(required)
        time_field = fields["outcome_time"]
    elif role == "material_relationships":
        relation_type = "LOT_MEMBERSHIP"
        fields = {
            "record_id": select(entity="relationship_record", kind="identifier"),
            "from_entity_id": select(entity="lot", kind="identifier"),
            "from_entity_type": select(kind="string", meaning="from entity type"),
            "to_entity_id": select(entity="wafer", kind="identifier"),
            "to_entity_type": select(kind="string", meaning="to entity type"),
            "effective_start": select(kind="timestamp", meaning="effective start"),
            "effective_end": select(kind="timestamp", meaning="effective end"),
            "observed_at": select(kind="timestamp", meaning="source observation time"),
        }
        required = {value for value in fields.values() if value}
        time_field = fields["observed_at"]
        required_relationship_keys = {
            fields[name] for name in ("from_entity_id", "from_entity_type", "to_entity_id", "to_entity_type", "observed_at")
            if fields[name]
        }
    elif role in {"coverage", "history_coverage", "route_coverage"}:
        fields = {
            "record_id": select(entity="coverage_record", kind="identifier"),
            "complete": select(kind="boolean"),
            "covered_wafer_ids": select(entity="wafer", kind="identifier_list"),
            "covered_lot_ids": select(entity="lot", kind="identifier_list"),
            "covered_operation_ids": select(entity="operation", kind="identifier_list"),
            "covered_source_ids": select(entity="source", kind="identifier_list", meaning="sources covered"),
            "source_ids": select(entity="source", kind="identifier_list", meaning="coverage record source"),
            "population_kind": select(kind="string", meaning="population identity grain"),
            "source_authority_claim": select(kind="string", meaning="authority label"),
            "window_start": select(kind="timestamp", meaning="window start"),
            "window_end": select(kind="timestamp", meaning="window end"),
            "valid_until": select(kind="timestamp", meaning="valid until"),
            "record_time": select(kind="timestamp", meaning="source observation time"),
            "missing_record_ids": select(entity="record", kind="identifier_list"),
        }
        required = {value for value in fields.values() if value}
        time_field = fields["record_time"]
        required_relationship_keys = set(required)
    else:  # route definitions
        fields = {
            "route_id": select(entity="route", kind="identifier"),
            "route_version": select(entity="route_version", kind="identifier"),
            "approved": select(kind="boolean"),
            "operations": select(kind="ordered_string_list"),
            "allowed_sequences": select(kind="list_of_ordered_string_lists"),
            "record_time": select(kind="timestamp", meaning="route definition record time"),
        }
        required = {value for value in fields.values() if value}
        time_field = fields["record_time"]
        required_relationship_keys = set(required)

    missing_required = sorted(name for name in _REQUIRED_FIELDS[role] if fields.get(name) is None)
    complete_fields = not missing_required
    relations = _valid_relationships(source, relationships, required_relationship_keys, relation_type) if complete_fields else []
    lineage_diagnostics = []
    if role == "material_relationships":
        source_relations = [item for item in relationships
                            if isinstance(item, dict) and source.get("source_id") in item.get("source_ids", [])]
        unsupported = sorted({item.get("relationship_type") for item in source_relations
                              if item.get("relationship_type") not in (None, "LOT_MEMBERSHIP")})
        if unsupported:
            lineage_diagnostics.append({
                "code": "MATERIAL_LINEAGE_RELATIONSHIP_UNMAPPED",
                "relationship_types": unsupported,
                "question": "Confirm source-declared split/merge endpoint types, time scope, and join keys before using these lineage edges.",
            })
    if len(relations) != 1:
        diagnostics = list(lineage_diagnostics)
        if role == "events" and fields.get("event_time") is None:
            event_times = [name for name, definition in columns.items()
                           if isinstance(definition, dict) and definition.get("type") == "timestamp"
                           and "event time" in str(definition.get("meaning", "")).casefold()]
            non_event_times = [name for name, definition in columns.items()
                               if isinstance(definition, dict) and definition.get("type") == "timestamp"
                               and any(word in str(definition.get("meaning", "")).casefold()
                                       for word in ("ingestion", "record time", "arrival time"))]
            if len(event_times) > 1:
                diagnostics.append({
                    "code": "AMBIGUOUS_PROCESS_EVENT_TIME",
                    "fields": sorted(event_times),
                    "question": "Which source field is the authorized process event timestamp for this step instance? Keep the other timestamp as separate timing context.",
                })
            elif non_event_times:
                diagnostics.append({
                    "code": "EVENT_TIME_NOT_ESTABLISHED",
                    "fields": sorted(non_event_times),
                    "question": "Which source field records actual process event time? Ingestion/record time cannot order manufacturing steps.",
                })
        if role == "events" and fields.get("step_instance_id") is None:
            instance_fields = [name for name, definition in columns.items()
                               if isinstance(definition, dict) and definition.get("entity") == "process_step_instance"]
            if len(instance_fields) > 1:
                diagnostics.append({
                    "code": "AMBIGUOUS_PROCESS_INSTANCE_IDENTIFIER",
                    "fields": sorted(instance_fields),
                    "question": "Which field uniquely identifies the actual executed step instance, separate from its rework-parent reference?",
                })
        if role == "events" and fields.get("chamber_id") is None:
            groups = [name for name, definition in columns.items()
                      if isinstance(definition, dict) and definition.get("entity") in {"tool_group", "equipment_group"}]
            if groups:
                diagnostics.append({
                    "code": "EXACT_CHAMBER_NOT_ESTABLISHED",
                    "fields": sorted(groups),
                    "question": "Is there an authorized source relationship from this equipment group to a physical chamber and actual step instance?",
                })
        if role in {"coverage", "history_coverage", "route_coverage"} and (
                fields.get("covered_source_ids") is None or fields.get("source_ids") is None):
            source_list_fields = sorted(
                name for name, definition in columns.items()
                if isinstance(definition, dict) and definition.get("type") == "identifier_list"
                and definition.get("entity") == "source"
            )
            diagnostics.append({
                "code": "COVERAGE_SOURCE_FIELDS_UNRESOLVED",
                "fields": source_list_fields,
                "question": "Which field lists the sources whose observations are covered, and which field identifies the source records that assert this coverage? P2 will not combine or guess these roles.",
            })
        if role == "material_relationships" and not any(
            name in columns for name in ("effective_start", "effective_end", "valid_from", "valid_to")
        ):
            diagnostics.append({
                "code": "TIME_SCOPED_MEMBERSHIP_NOT_ESTABLISHED",
                "fields": [],
                "question": "Which authorized source records wafer membership over the investigated event-time window?",
            })
        return {
            "role": role, "source_id": source.get("source_id"),
            "candidate_state": "AMBIGUOUS_RELATIONSHIP" if relations else "MISSING_REQUIRED_SEMANTICS_OR_RELATIONSHIP",
            "field_mapping": fields, "candidate_relationship_ids": sorted(item.get("id", "") for item in relations),
            "missing_fields": sorted(name for name, value in fields.items() if value is None),
            "missing_required_fields": missing_required,
            "diagnostics": diagnostics,
            "requires_authorized_review": True,
        }
    relation_keys = set(relations[0].get("keys", []))
    source_start = datetime.fromisoformat(source_effectivity["start"].replace("Z", "+00:00"))
    source_end = datetime.fromisoformat(source_effectivity["end"].replace("Z", "+00:00"))
    relation_start = datetime.fromisoformat(relations[0]["effective_start"].replace("Z", "+00:00"))
    relation_end = datetime.fromisoformat(relations[0]["effective_end"].replace("Z", "+00:00"))
    relationship_field_gaps = sorted(
        field for field in fields.values() if field is not None and field not in relation_keys
    )
    missing_optional = sorted(name for name, value in fields.items()
                              if value is None and name not in _REQUIRED_FIELDS[role])
    ranking_factors = {
        "required_semantics_present": len(_REQUIRED_FIELDS[role]),
        "optional_semantics_present": len(fields) - len(_REQUIRED_FIELDS[role]) - len(missing_optional),
        "required_relationship_keys_present": len(required_relationship_keys & relation_keys),
        "optional_relationship_keys_present": len(
            (set(value for name, value in fields.items() if name not in _REQUIRED_FIELDS[role] and value)
             & relation_keys)
        ),
        "score_is_only_a_review_order": True,
    }
    candidate_state = ("STRUCTURALLY_PARTIAL_REVIEW_REQUIRED" if missing_optional
                       else "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED")
    return {
        "role": role, "source_id": source["source_id"],
        "semantic_version": source["semantic_version"], "source_hash": source.get("source_hash"),
        "record_kind": source["record_kind"], "grain": source.get("grain"),
        "relationship_id": relations[0]["id"], "field_mapping": fields,
        "nullable_fields": sorted(
            logical for logical, physical in fields.items()
            if physical is not None and columns[physical].get("nullable") is True
        ),
        "relationship_type": relations[0].get("relationship_type"),
        "descriptor_effectivity_intersection": {
            "start": max(source_start, relation_start).isoformat(),
            "end": min(source_end, relation_end).isoformat(),
        },
        "relationship_authorized_fields": sorted(set(fields.values()) & relation_keys),
        "fields_missing_from_relationship": relationship_field_gaps,
        "relationship_key_note": "These fields are source attributes; only the source-declared relationship keys authorize joins and filters.",
        "time_field": time_field,
        "candidate_state": candidate_state,
        "missing_optional_fields": missing_optional,
        "ranking_factors": ranking_factors,
        "review_warning": (
            "Missing optional source observations remain unknown; they must not be inferred."
            if missing_optional else "Structural fit is not source approval or authorization."
        ),
        "diagnostics": [*lineage_diagnostics, *([{
            "code": "EXACT_CHAMBER_NOT_ESTABLISHED",
            "fields": missing_optional,
            "question": "Can an authorized physical-chamber observation be mapped? Until then, chamber exposure remains unknown.",
        }] if role == "events" and "chamber_id" in missing_optional else [])],
        "requires_authorized_review": True,
    }


def _contains_source_rows(value: Any) -> bool:
    if isinstance(value, dict):
        if any(key in value for key in ("rows", "events", "outcomes", "measurements", "typed_rows")):
            return True
        return any(_contains_source_rows(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_source_rows(item) for item in value)
    return False


def propose_mappings(capture: Any) -> dict[str, Any]:
    """Inspect a local MCP descriptor capture; never execute, authorize, or join data."""
    if not isinstance(capture, dict):
        raise ValueError("descriptor capture must be an object")
    tools = capture.get("tools", [])
    sources = capture.get("sources", [])
    relationships = capture.get("relationships", [])
    if (not isinstance(tools, list) or not isinstance(sources, list)
            or not isinstance(relationships, list)):
        raise ValueError("tools, sources, and relationships must be lists")
    if _contains_source_rows(capture):
        raise ValueError("Onboarding accepts descriptors only; remove source data rows from the capture.")
    malformed_counts = {
        "tools": sum(not isinstance(item, dict) for item in tools),
        "sources": sum(not isinstance(item, dict) for item in sources),
        "relationships": sum(not isinstance(item, dict) for item in relationships),
    }
    tools = [item for item in tools if isinstance(item, dict)]
    sources = [item for item in sources if isinstance(item, dict)]
    relationships = [item for item in relationships if isinstance(item, dict)]
    invalid_sections = []
    tool_versions = capture.get("tool_versions", {})
    if not isinstance(tool_versions, dict):
        invalid_sections.append("tool_versions")
        tool_versions = {}
    limits = capture.get("limits", {})
    if not isinstance(limits, dict):
        invalid_sections.append("limits")
        limits = {}
    source_id_counts = Counter(item.get("source_id") for item in sources
                               if isinstance(item.get("source_id"), str))
    relationship_id_counts = Counter(item.get("id") for item in relationships
                                     if isinstance(item.get("id"), str))
    duplicate_source_ids = sorted(name for name, count in source_id_counts.items() if count > 1)
    duplicate_relationship_ids = sorted(name for name, count in relationship_id_counts.items() if count > 1)
    sources = [item for item in sources if item.get("source_id") not in set(duplicate_source_ids)]
    relationships = [item for item in relationships if item.get("id") not in set(duplicate_relationship_ids)]

    operation_proposals = {}
    for operation in _OPERATION_REQUIRED:
        candidates = sorted(
            item.get("name", "") for item in tools
            if isinstance(item.get("name"), str) and _tool_matches(item, operation)
        )
        operation_proposals[operation] = {
            "candidate_tool_names": candidates,
            "tool_version_by_name": {
                name: tool_versions.get(name)
                for name in candidates
            },
            "candidate_state": "UNIQUE_REVIEW_REQUIRED" if len(candidates) == 1
            else "AMBIGUOUS" if candidates else "NO_COMPATIBLE_TOOL",
        }
    proposed_names = [value["candidate_tool_names"][0]
                      for value in operation_proposals.values()
                      if len(value["candidate_tool_names"]) == 1]
    if len(proposed_names) != len(set(proposed_names)):
        for value in operation_proposals.values():
            if len(value["candidate_tool_names"]) == 1 and proposed_names.count(value["candidate_tool_names"][0]) > 1:
                value["candidate_state"] = "AMBIGUOUS_TOOL_REUSE"

    role_candidates = {}
    for role, record_kind in _ROLE_KIND.items():
        candidates = [candidate for source in sources
                      if source.get("record_kind") == record_kind
                      if (candidate := _role_candidate(role, source, relationships)) is not None]
        compatible = [item for item in candidates
                      if item["candidate_state"] in {
                          "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED",
                          "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED",
                      }]
        compatible.sort(key=lambda item: (
            -item["ranking_factors"]["required_relationship_keys_present"],
            -item["ranking_factors"]["optional_semantics_present"], item["source_id"],
        ))
        score = lambda item: (
            item["ranking_factors"]["required_relationship_keys_present"],
            item["ranking_factors"]["optional_semantics_present"],
        )
        top_score = score(compatible[0]) if compatible else None
        top_ties = [item for item in compatible if score(item) == top_score] if compatible else []
        preferred = compatible[0]["source_id"] if len(top_ties) == 1 else None
        role_candidates[role] = {
            "candidates": candidates,
            "ranked_candidate_source_ids": [item["source_id"] for item in compatible],
            "preferred_candidate_source_id": preferred,
            "top_rank_tie_source_ids": [item["source_id"] for item in top_ties] if len(top_ties) > 1 else [],
            "ranking_policy": "Declared relationship-key coverage and optional semantic completeness. Stable ID sorts tied candidates for display only; ties have no preferred candidate. Names do not contribute.",
            "candidate_state": "UNIQUE_REVIEW_REQUIRED" if len(compatible) == 1
            else "AMBIGUOUS" if len(compatible) > 1 else "NO_STRUCTURALLY_COMPATIBLE_SOURCE",
        }

    query_plans = []
    for role, proposal in role_candidates.items():
        compatible = [item for item in proposal["candidates"]
                      if item.get("candidate_state") in {
                          "STRUCTURALLY_COMPATIBLE_REVIEW_REQUIRED",
                          "STRUCTURALLY_PARTIAL_REVIEW_REQUIRED",
                      }]
        for candidate in compatible:
            query_plans.append({
                "dataset_role": role, "source_ids": [candidate["source_id"]],
                "relationship_ids": [candidate["relationship_id"]],
                "time_field": candidate["time_field"],
                "time_window": "REQUIRED_ENGINEER_SELECTED_TIMEZONE_AWARE_BOUNDS",
                "descriptor_effectivity_intersection": candidate["descriptor_effectivity_intersection"],
                "max_rows": limits.get("max_rows"), "max_bytes": limits.get("max_bytes"),
                "max_seconds": limits.get("max_seconds"),
                "filters": "REQUIRED_SOURCE_OBSERVED_ENTITY_IDS",
                "field_mapping": candidate["field_mapping"],
                "missing_optional_fields": candidate.get("missing_optional_fields", []),
                "authorization_state": "REVIEW_REQUIRED_NOT_EXECUTED",
            })
    unresolved = []
    unresolved.extend(f"review or resolve MCP tool mapping: {name}"
                      for name, item in operation_proposals.items()
                      if item["candidate_state"] != "UNIQUE_REVIEW_REQUIRED")
    unresolved.extend(f"review or resolve source role: {name}"
                      for name, item in role_candidates.items()
                      if item["candidate_state"] != "UNIQUE_REVIEW_REQUIRED")
    for role, proposal in role_candidates.items():
        for candidate in proposal["candidates"]:
            if candidate.get("missing_optional_fields"):
                unresolved.append(
                    f"decide whether missing optional {role} observations are acceptable: "
                    f"{', '.join(candidate['missing_optional_fields'])} (remain unknown)"
                )
    if not isinstance(limits, dict) or any(
        not isinstance(limits.get(name), int) or isinstance(limits.get(name), bool) or limits[name] < 1
        for name in ("max_rows", "max_bytes", "max_seconds")
    ):
        unresolved.append("capture exact server-enforced bounded-read limits")
    exact_version_missing = any(
        not isinstance(value, str) or not value.strip()
        or value.strip().casefold() in {"latest", "unknown", "n/a", "template"}
        for proposal in operation_proposals.values()
        for value in proposal["tool_version_by_name"].values()
    )
    if exact_version_missing:
        unresolved.append("capture exact discovered MCP tool versions")
    unresolved.extend([
        "confirm the authorized server, source permissions, and exact semantic versions",
        "review source and relationship candidates; structural compatibility is not source approval",
        "select a bounded time window and limits within server-enforced permissions",
        "run approved preflight, then explicitly authorize each read-only investigation",
    ])
    descriptor_diagnostics = {
        "malformed_descriptor_counts": malformed_counts,
        "duplicate_source_ids_rejected": duplicate_source_ids,
        "duplicate_relationship_ids_rejected": duplicate_relationship_ids,
        "invalid_capture_sections": invalid_sections,
    }
    if any(malformed_counts.values()):
        unresolved.append("repair malformed MCP descriptor entries before review")
    if duplicate_source_ids or duplicate_relationship_ids:
        unresolved.append("resolve duplicate source or relationship descriptor identities")
    if invalid_sections:
        unresolved.append("repair malformed tool-version or bounded-limit capture sections")
    mapping_diagnostics = (
        any(item["candidate_state"] != "UNIQUE_REVIEW_REQUIRED" for item in operation_proposals.values())
        or any(item["candidate_state"] != "UNIQUE_REVIEW_REQUIRED" for item in role_candidates.values())
        or any(malformed_counts.values()) or duplicate_source_ids or duplicate_relationship_ids
        or invalid_sections
    )
    return {
        "schema_version": "p2-onboarding-proposal/v1",
        "state": "DIAGNOSTIC_DECISIONS_REQUIRED" if mapping_diagnostics else "REVIEW_REQUIRED",
        "capture_label": "UNVERIFIED_DESCRIPTOR_CAPTURE",
        "capture_origin_verification": "NOT_ESTABLISHED",
        "company_qualified": False, "server_authorization_established": False,
        "reads_executed": False, "relationships_joined": False,
        "operation_proposals": operation_proposals,
        "source_role_proposals": role_candidates,
        "bounded_query_plan_proposals": query_plans,
        "required_manual_decisions": unresolved,
        "descriptor_diagnostics": descriptor_diagnostics,
        "catalog_descriptors_examined": len(sources),
    }
