"""Build a fixed-answer, synthetic multi-lot process-forensics exercise."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "2026-11-21T01:25:00+00:00"
END = "2026-11-21T01:35:00+00:00"
EFFECTIVE_START = "2026-11-20T00:00:00+00:00"
EFFECTIVE_END = "2026-11-30T00:00:00+00:00"
BASE = datetime(2026, 11, 21, tzinfo=timezone.utc)


def source(source_id: str, grain: str) -> dict:
    return {
        "id": source_id,
        "approved_semantic_version": "SYNTHETIC-ENGINEER-STUDY-1",
        "grain": grain,
        "source_hash": hashlib.sha256(source_id.encode()).hexdigest(),
        "permissions_ref": "SYNTHETIC-ONLY-NOT-AUTHORIZATION",
    }


def relation(relation_id: str, source_id: str, keys: list[str], grain: str,
             relationship_type: str | None = None) -> dict:
    record = {
        "id": relation_id,
        "approved": True,
        "source_ids": [source_id],
        "keys": keys,
        "cardinality": "synthetic fixture relationship; not company semantics",
        "grain": grain,
        "effective_start": EFFECTIVE_START,
        "effective_end": EFFECTIVE_END,
    }
    if relationship_type:
        record["relationship_type"] = relationship_type
    return record


def coverage_record(record_id: str, source_id: str, relation_id: str,
                    covered_wafer_ids: list[str], covered_source_ids: list[str],
                    missing_record_ids: list[str]) -> dict:
    return {
        "record_id": record_id,
        "complete": True,
        "covered_wafer_ids": covered_wafer_ids,
        "covered_lot_ids": [f"SYN-LOT-{i // 10:02d}" for i in range(100)],
        "covered_operation_ids": ["CLEAN", "ETCH", "MET", "CMP"],
        "covered_source_ids": covered_source_ids,
        "population_kind": "WAFER",
        "source_authority_claim": "SYNTHETIC_FIXTURE_ASSERTION_ONLY",
        "source_ids": [source_id],
        "relationship_id": relation_id,
        "window_start": EFFECTIVE_START,
        "window_end": EFFECTIVE_END,
        "valid_until": EFFECTIVE_END,
        "missing_record_ids": missing_record_ids,
    }


def main() -> None:
    wafer_ids = [f"SYN-EW-{i:03d}" for i in range(100)]
    process_id, outcome_id = "SYN_EW_PROCESS", "SYN_EW_OUTCOME"
    exposure_cov_id, history_cov_id = "SYN_EW_EXPOSURE_COVERAGE", "SYN_EW_HISTORY_COVERAGE"
    route_id, condition_id, material_id = "SYN_EW_ROUTE", "SYN_EW_CONDITION", "SYN_EW_MATERIAL"
    process_rel, outcome_rel = "SYN_REL_EW_PROCESS", "SYN_REL_EW_OUTCOME"
    exposure_cov_rel, history_cov_rel = "SYN_REL_EW_EXPOSURE_COVERAGE", "SYN_REL_EW_HISTORY_COVERAGE"
    route_rel, condition_rel = "SYN_REL_EW_ROUTE", "SYN_REL_EW_CONDITION"
    material_rel_ids = {
        "LOT_MEMBERSHIP": "SYN_REL_EW_LOT_MEMBERSHIP",
        "SPLIT_FROM": "SYN_REL_EW_SPLIT",
        "MERGED_FROM": "SYN_REL_EW_MERGE",
    }
    sources = [
        source(process_id, "one process step instance"),
        source(outcome_id, "one outcome per wafer"),
        source(exposure_cov_id, "one exposure observation-coverage record"),
        source(history_cov_id, "one process-history observation-coverage record"),
        source(route_id, "one expected route definition per route version"),
        source(condition_id, "one equipment condition event"),
        source(material_id, "one typed material relationship edge"),
    ]
    process_keys = [
        "wafer_id", "step_instance_id", "operation", "timestamp", "recorded_at",
        "time_uncertainty_seconds", "lot_id", "tool_id", "chamber_id", "route_id",
        "route_version", "rework_of_step_instance_id",
    ]
    coverage_keys = [
        "record_id", "complete", "covered_wafer_ids", "covered_lot_ids",
        "covered_operation_ids", "covered_source_ids", "population_kind",
        "source_authority_claim", "source_ids", "window_start", "window_end",
        "valid_until", "missing_record_ids",
    ]
    relationships = [
        relation(process_rel, process_id, process_keys, "one process step instance"),
        relation(outcome_rel, outcome_id, ["wafer_id", "lot_id", "label", "timestamp", "product_id"], "one outcome per wafer"),
        relation(exposure_cov_rel, exposure_cov_id, coverage_keys, "one scoped exposure coverage record"),
        relation(history_cov_rel, history_cov_id, coverage_keys, "one scoped history coverage record"),
        relation(route_rel, route_id, ["route_id", "route_version", "approved", "operations", "allowed_sequences"], "one route definition per version"),
        relation(condition_rel, condition_id, ["condition_event_id", "condition_type", "equipment_type", "equipment_id", "event_start", "event_end", "time_uncertainty_seconds", "recorded_at"], "one equipment condition event"),
    ]
    for relationship_type, rel_id in material_rel_ids.items():
        relationships.append(relation(rel_id, material_id,
            ["from_entity_id", "from_entity_type", "to_entity_id", "to_entity_type"],
            "one typed material relationship edge", relationship_type))

    events: list[dict] = []
    outcomes: list[dict] = []
    abnormal_ids: list[str] = []
    for index, wafer_id in enumerate(wafer_ids):
        if index in {98, 99}:
            # Outcome exists, but the process-history feed has no rows for these wafers.
            continue
        group = index % 4
        chamber = {0: "SYN-C1", 1: "SYN-C2", 2: None, 3: "SYN-C3"}[group]
        tool = "SYN-T-ETCH-X" if group in {0, 1, 2} else "SYN-T-ETCH-Y"
        version = "v2" if index % 10 >= 5 else "v1"
        base_ops = ["CLEAN", "ETCH", "MET", "CMP"]
        if version == "v2" and index % 10 == 9:
            base_ops = ["CLEAN", "ETCH", "CMP"]  # explicit permitted alternate route
        times = [BASE + timedelta(minutes=m) for m in (30, 90, 130, 170)]
        prior_etch: str | None = None
        for order, operation in enumerate(base_ops):
            if operation == "CMP" and version == "v2" and index % 10 == 9:
                order_time = BASE + timedelta(minutes=170)
            else:
                order_time = times[order]
            step_id = f"{wafer_id}-S{order:02d}"
            event = {
                "wafer_id": wafer_id,
                "step_instance_id": step_id,
                "operation": operation,
                "timestamp": order_time.isoformat(),
                # Arrival/recording order intentionally disagrees with process order.
                "recorded_at": (order_time + timedelta(days=2 + (3 - order))).isoformat(),
                "time_uncertainty_seconds": 0,
                "lot_id": f"SYN-LOT-{index // 10:02d}",
                "tool_id": tool,
                "chamber_id": chamber,
                "route_id": "SYN-ROUTE-A",
                "route_version": version,
                "rework_of_step_instance_id": None,
                "source_id": process_id,
                "relationship_id": process_rel,
                "approved_relationship": True,
            }
            if wafer_id == "SYN-EW-004" and operation == "ETCH":
                event["time_uncertainty_seconds"] = 1200
            if wafer_id == "SYN-EW-043" and operation == "MET":
                event["timestamp"] = (BASE + timedelta(minutes=155)).isoformat()
                event["time_uncertainty_seconds"] = 900
            if wafer_id == "SYN-EW-043" and operation == "CMP":
                event["timestamp"] = (BASE + timedelta(minutes=150)).isoformat()
                event["time_uncertainty_seconds"] = 900
            events.append(event)
            if operation == "ETCH":
                prior_etch = step_id
                if index % 5 == 0:
                    rework_time = order_time + timedelta(minutes=12)
                    events.append({
                        **event,
                        "step_instance_id": f"{wafer_id}-ETCH-R1",
                        "timestamp": rework_time.isoformat(),
                        "recorded_at": (rework_time + timedelta(days=3)).isoformat(),
                        "rework_of_step_instance_id": prior_etch,
                    })

        # Label pattern crosses exact C1 exposure groups and other chambers;
        # it intentionally does not encode a single explanatory cause.
        abnormal = (index * 7 + 3) % 11 < 5
        if abnormal:
            abnormal_ids.append(wafer_id)
        outcomes.append({
            "wafer_id": wafer_id,
            "lot_id": f"SYN-LOT-{index // 10:02d}",
            "label": "ABNORMAL" if abnormal else "NORMAL",
            "product_id": f"SYN-PROD-{index % 3}",
            "timestamp": (BASE + timedelta(days=4, minutes=index)).isoformat(),
            "source_id": outcome_id,
            "relationship_id": outcome_rel,
            "approved_relationship": True,
        })

    # Exact duplicate is safely coalescible; a second negative exercise below
    # inserts a contradictory duplicate ID and must be refused.
    events.append(deepcopy(next(row for row in events if row["step_instance_id"] == "SYN-EW-001-S01")))

    condition_events = [
        {
            "condition_event_id": "SYN-MAINT-C1-04",
            "condition_type": "MAINTENANCE", "equipment_type": "CHAMBER", "equipment_id": "SYN-C1",
            "event_start": "2026-11-21T01:20:00+00:00", "event_end": "2026-11-21T01:50:00+00:00",
            "time_uncertainty_seconds": 120, "recorded_at": "2026-11-22T09:00:00+00:00",
            "source_id": condition_id, "relationship_id": condition_rel,
            "approved_relationship": True,
        },
        {
            "condition_event_id": "SYN-CHANGE-T-ETCH-X-02",
            "condition_type": "CHANGE", "equipment_type": "TOOL", "equipment_id": "SYN-T-ETCH-X",
            "event_start": "2026-11-21T01:10:00+00:00", "event_end": "2026-11-21T02:00:00+00:00",
            "time_uncertainty_seconds": 0, "recorded_at": "2026-11-22T06:00:00+00:00",
            "source_id": condition_id, "relationship_id": condition_rel,
            "approved_relationship": True,
        },
    ]
    expected_routes = [
        {"route_id": "SYN-ROUTE-A", "route_version": "v1", "approved": True,
         "source_id": route_id, "relationship_id": route_rel,
         "operations": ["CLEAN", "ETCH", "MET", "CMP"], "allowed_sequences": []},
        {"route_id": "SYN-ROUTE-A", "route_version": "v2", "approved": True,
         "source_id": route_id, "relationship_id": route_rel,
         "operations": ["CLEAN", "ETCH", "MET", "CMP"],
         "allowed_sequences": [["CLEAN", "ETCH", "CMP"]]},
    ]
    covered_ids = wafer_ids
    exposure_coverage = coverage_record("SYN-EW-EXP-COV", exposure_cov_id, exposure_cov_rel,
        covered_ids, [process_id], ["GAP-ETCH-044", "GAP-ETCH-077"])
    history_coverage = coverage_record("SYN-EW-HIST-COV", history_cov_id, history_cov_rel,
        covered_ids, [process_id], ["GAP-HISTORY-098", "GAP-HISTORY-099"])
    route_coverage = coverage_record("SYN-EW-ROUTE-COV", exposure_cov_id, exposure_cov_rel,
        covered_ids, [process_id, route_id], ["GAP-ROUTE-077"])

    # One wafer changes lot after a source-declared split; a separate lot merge
    # connects the destination to a parent lot without asserting sibling wafers.
    material_edges = []
    def material_edge(record_id: str, kind: str, from_entity: dict, to_entity: dict,
                      rel_id: str, effective_start: str, effective_end: str) -> dict:
        return {
            "record_id": record_id, "relationship_type": kind, "source_id": material_id,
            "relationship_id": rel_id, "from_entity": from_entity, "to_entity": to_entity,
            "key_values": {"from_entity_id": from_entity["id"], "from_entity_type": from_entity["type"],
                           "to_entity_id": to_entity["id"], "to_entity_type": to_entity["type"]},
            "effective_start": effective_start, "effective_end": effective_end,
            "observed_at": "2026-11-22T10:00:00+00:00",
        }
    material_edges.extend([
        material_edge("SYN-MEM-010-A", "LOT_MEMBERSHIP", {"type": "lot", "id": "SYN-LOT-01"}, {"type": "wafer", "id": "SYN-EW-010"}, material_rel_ids["LOT_MEMBERSHIP"], EFFECTIVE_START, "2026-11-21T02:00:00+00:00"),
        material_edge("SYN-MEM-010-B", "LOT_MEMBERSHIP", {"type": "lot", "id": "SYN-LOT-01B"}, {"type": "wafer", "id": "SYN-EW-010"}, material_rel_ids["LOT_MEMBERSHIP"], "2026-11-21T02:00:00+00:00", EFFECTIVE_END),
        material_edge("SYN-SPLIT-01", "SPLIT_FROM", {"type": "lot", "id": "SYN-LOT-01"}, {"type": "lot", "id": "SYN-LOT-01B"}, material_rel_ids["SPLIT_FROM"], "2026-11-21T02:00:00+00:00", EFFECTIVE_END),
        material_edge("SYN-MERGE-01", "MERGED_FROM", {"type": "lot", "id": "SYN-LOT-MERGED"}, {"type": "lot", "id": "SYN-LOT-01B"}, material_rel_ids["MERGED_FROM"], "2026-11-21T02:00:00+00:00", EFFECTIVE_END),
    ])

    snapshot = {
        "wafer_id": abnormal_ids[0],
        "target_wafer_ids": [w for w in abnormal_ids if w not in {"SYN-EW-098", "SYN-EW-099"}],
        "cohort": wafer_ids,
        "events": list(reversed(events)),
        "outcomes": outcomes,
        "sources": sources,
        "relationships": relationships,
        "suspected_exposure": {"chamber_id": "SYN-C1", "start": START, "end": END, "condition_type": "MAINTENANCE"},
        "condition_events": condition_events,
        "coverage": exposure_coverage,
        "history_coverage": history_coverage,
        "expected_routes": expected_routes,
        "route_coverage": route_coverage,
        "material_relationships": material_edges,
    }
    target = ROOT / "qualification/fixtures/complex_engineer_investigation_v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"fixture": str(target.relative_to(ROOT)), "wafer_count": len(wafer_ids),
                      "outcome_count": len(outcomes), "event_rows_including_exact_duplicate": len(events),
                      "abnormal_target_count": len(snapshot["target_wafer_ids"]),
                      "source_count": len(sources), "relationship_count": len(relationships),
                      "case_is_synthetic": True}, indent=2))


if __name__ == "__main__":
    main()
