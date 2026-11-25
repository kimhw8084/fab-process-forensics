"""Reproducible synthetic scale benchmark for the P2 history engine.

Each replica has distinct wafer/lot/step IDs, while source contracts and exact
equipment definitions remain fixed. This measures local deterministic analysis
only; it is not a production-capacity qualification.
"""
from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "qualification/fixtures/complex_engineer_investigation_v1.json"
sys.path.insert(0, str(ROOT))

from fabintel.project import analyze


def scaled_snapshot(replicas: int) -> dict:
    if replicas < 1:
        raise ValueError("replicas must be at least one")
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if replicas == 1:
        return base

    base_wafers = sorted(set(base.get("cohort", [])))
    base_lots = sorted({
        row["lot_id"] for key in ("events", "outcomes")
        for row in base.get(key, []) if isinstance(row.get("lot_id"), str)
    } | {
        endpoint["id"]
        for edge in base.get("material_edges", [])
        for endpoint in (edge.get("from_entity", {}), edge.get("to_entity", {}))
        if endpoint.get("type") == "lot" and isinstance(endpoint.get("id"), str)
    })
    all_wafers = list(base_wafers)
    all_lots = set(base_lots)
    all_replica_wafers = []
    all_replica_lots = []
    events = list(base["events"])
    outcomes = list(base["outcomes"])
    material_edges = list(base.get("material_edges", []))
    targets = list(base.get("target_wafer_ids", []))

    for replica in range(1, replicas):
        prefix = f"SYN-PERF-{replica:04d}"
        wafer_map = {wafer: f"{prefix}-{wafer}" for wafer in base_wafers}
        lot_map = {lot: f"{prefix}-{lot}" for lot in base_lots}
        all_replica_wafers.extend(wafer_map.values())
        all_replica_lots.extend(lot_map.values())
        all_wafers.extend(wafer_map.values())
        all_lots.update(lot_map.values())

        for source_event in base["events"]:
            event = deepcopy(source_event)
            event["wafer_id"] = wafer_map[event["wafer_id"]]
            event["step_instance_id"] = f"{prefix}-{event['step_instance_id']}"
            if event.get("rework_of_step_instance_id"):
                event["rework_of_step_instance_id"] = f"{prefix}-{event['rework_of_step_instance_id']}"
            if event.get("lot_id") in lot_map:
                event["lot_id"] = lot_map[event["lot_id"]]
            events.append(event)

        for source_outcome in base["outcomes"]:
            outcome = deepcopy(source_outcome)
            outcome["wafer_id"] = wafer_map[outcome["wafer_id"]]
            if outcome.get("lot_id") in lot_map:
                outcome["lot_id"] = lot_map[outcome["lot_id"]]
            outcomes.append(outcome)

        for source_edge in base.get("material_edges", []):
            edge = deepcopy(source_edge)
            edge["record_id"] = f"{prefix}-{edge['record_id']}"
            for key in ("from_entity", "to_entity"):
                endpoint = edge.get(key, {})
                if endpoint.get("type") == "wafer" and endpoint.get("id") in wafer_map:
                    endpoint["id"] = wafer_map[endpoint["id"]]
                elif endpoint.get("type") == "lot" and endpoint.get("id") in lot_map:
                    endpoint["id"] = lot_map[endpoint["id"]]
            edge["key_values"] = {
                "from_entity_id": edge["from_entity"]["id"],
                "from_entity_type": edge["from_entity"]["type"],
                "to_entity_id": edge["to_entity"]["id"],
                "to_entity_type": edge["to_entity"]["type"],
            }
            material_edges.append(edge)
        targets.extend(wafer_map[wafer] for wafer in base.get("target_wafer_ids", []))

    base["events"] = list(reversed(events))
    base["outcomes"] = outcomes
    base["cohort"] = sorted(set(all_wafers))
    base["target_wafer_ids"] = sorted(set(targets))
    base["wafer_id"] = base["target_wafer_ids"][0]
    base["material_edges"] = material_edges
    # Apply every generated identity in one traversal. Rewalking the growing
    # event snapshot once per replica made benchmark setup quadratic and hid
    # the engine timing the benchmark is intended to measure.
    for value in base.values():
        _append_replica_coverage(value, all_replica_wafers, all_replica_lots)
    return base


def _append_replica_coverage(value, replica_wafer_ids, replica_lot_ids):
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "covered_wafer_ids" and isinstance(item, list):
                item.extend(replica_wafer_ids)
                value[key] = sorted(set(item))
            elif key == "covered_lot_ids" and isinstance(item, list):
                item.extend(replica_lot_ids)
                value[key] = sorted(set(item))
            else:
                _append_replica_coverage(item, replica_wafer_ids, replica_lot_ids)
    elif isinstance(value, list):
        for item in value:
            _append_replica_coverage(item, replica_wafer_ids, replica_lot_ids)


def max_rss_bytes() -> int:
    measured = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(measured if platform.system() == "Darwin" else measured * 1024)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicas", type=int, default=1, help="Number of 100-wafer fixture copies.")
    args = parser.parse_args()
    snapshot = scaled_snapshot(args.replicas)
    payload_bytes = len(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode())
    before_rss = max_rss_bytes()
    started = time.perf_counter()
    result = analyze(snapshot)
    elapsed = time.perf_counter() - started
    after_rss = max_rss_bytes()
    journey = next(item for item in result["transformations"] if item.get("id") == "p2-journey-and-route-variants-v1")
    exposure = result["artifacts"][0]["exposure_analysis"]
    fixed_answer = {
        "journeys": 98 * args.replicas,
        "retained_step_instances": 403 * args.replicas,
        "collapsed_duplicate_copies": args.replicas,
        "exact_exposure_count": 24 * args.replicas,
        "potential_exposure_count": 25 * args.replicas,
        "unknown_exposure_count": 51 * args.replicas,
        "verified_unexposed_count": 0,
        "coverage_evidence_level": "CONTRADICTORY",
        "status": "PARTIAL",
    }
    observed = {
        "journeys": len(journey["journeys"]),
        "retained_step_instances": sum(len(item["steps"]) for item in journey["journeys"]),
        "collapsed_duplicate_copies": result["uncertainty"].get("collapsed_duplicate_source_records", 0),
        "exact_exposure_count": len(exposure["definitely_exposed"]),
        "potential_exposure_count": len(exposure["potentially_exposed"]),
        "unknown_exposure_count": len(exposure["unknown"]),
        "verified_unexposed_count": len(exposure["verified_unexposed"]),
        "coverage_evidence_level": exposure["coverage_evidence_level"],
        "status": result["status"],
    }
    if observed != fixed_answer:
        raise RuntimeError(f"Scaled fixed-answer oracle mismatch: {observed!r} != {fixed_answer!r}")
    print(json.dumps({
        "fixture": FIXTURE.relative_to(ROOT).as_posix(),
        "replicas": args.replicas,
        "payload_bytes": payload_bytes,
        "event_rows_including_duplicate_copies": len(snapshot["events"]),
        "outcome_rows": len(snapshot["outcomes"]),
        "journeys": len(journey["journeys"]),
        "retained_step_instances": sum(len(item["steps"]) for item in journey["journeys"]),
        "collapsed_duplicate_copies": result["uncertainty"].get("collapsed_duplicate_source_records", 0),
        "status": result["status"],
        "coverage_evidence_level": exposure["coverage_evidence_level"],
        "exact_exposure_count": len(exposure["definitely_exposed"]),
        "potential_exposure_count": len(exposure["potentially_exposed"]),
        "unknown_exposure_count": len(exposure["unknown"]),
        "verified_unexposed_count": len(exposure["verified_unexposed"]),
        "scaled_fixed_answer_oracle": "PASS",
        "analysis_seconds": round(elapsed, 3),
        "process_max_rss_bytes": after_rss,
        "process_rss_increase_from_pre_analysis_bytes": max(0, after_rss - before_rss),
        "host_platform": platform.platform(),
        "qualification_scope": "Synthetic local engine timing only; not browser, MCP, concurrency, deployment, or production-scale qualification.",
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
