"""Measure deterministic P2 analysis scaling on a precommitted local fixture."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fabintel.project import analyze

WAFER_COUNT = 100
EVENT_SIZES = (100, 1_000, 10_000, 50_000, 100_000)
RUNS = 7
MAX_PAYLOAD_BYTES = 25 * 1024 * 1024
BASE_TIME = datetime(2026, 11, 21, tzinfo=timezone.utc)
WINDOW_START = "2026-11-21T00:00:00+00:00"
WINDOW_END = "2026-11-21T03:00:00+00:00"
LOT_ID = "LOT-SCALE"
PROCESS_SOURCE = "SYN_SCALE_PROCESS"
OUTCOME_SOURCE = "SYN_SCALE_OUTCOME"
COVERAGE_SOURCE = "SYN_SCALE_COVERAGE"
EVENT_RELATION = "SYN_SCALE_WAFER_STEP"
OUTCOME_RELATION = "SYN_SCALE_OUTCOME_LOT_WAFER"
COVERAGE_RELATION = "SYN_SCALE_COVERAGE_RECORD"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999)))
    return ordered[index]


def build_snapshot(event_count: int) -> dict:
    if event_count % WAFER_COUNT:
        raise ValueError("Each benchmark workload must divide evenly across 100 wafers.")
    steps_per_wafer = event_count // WAFER_COUNT
    wafer_ids = [f"SCALE-W{i:03d}" for i in range(WAFER_COUNT)]
    event_source = {
        "id": PROCESS_SOURCE,
        "approved_semantic_version": "SYNTHETIC-SCALE-1",
        "grain": "one process step instance",
        "source_hash": hashlib.sha256(b"synthetic scale process source").hexdigest(),
    }
    outcome_source = {
        "id": OUTCOME_SOURCE,
        "approved_semantic_version": "SYNTHETIC-SCALE-1",
        "grain": "one outcome per wafer",
        "source_hash": hashlib.sha256(b"synthetic scale outcome source").hexdigest(),
    }
    coverage_source = {
        "id": COVERAGE_SOURCE,
        "approved_semantic_version": "SYNTHETIC-SCALE-1",
        "grain": "one exposure coverage record per population and time window",
        "source_hash": hashlib.sha256(b"synthetic scale coverage source").hexdigest(),
    }
    event_relation = {
        "id": EVENT_RELATION,
        "approved": True,
        "source_ids": [PROCESS_SOURCE],
        "keys": ["wafer_id", "step_instance_id", "timestamp", "chamber_id"],
        "cardinality": "one process step instance to one wafer identity",
        "grain": "one process step instance",
        "effective_start": "2026-11-20T00:00:00+00:00",
        "effective_end": "2026-11-23T00:00:00+00:00",
    }
    outcome_relation = {
        "id": OUTCOME_RELATION,
        "approved": True,
        "source_ids": [OUTCOME_SOURCE],
        "keys": ["wafer_id", "timestamp", "lot_id"],
        "cardinality": "one outcome per wafer and lot membership",
        "grain": "one outcome per wafer",
        "effective_start": "2026-11-20T00:00:00+00:00",
        "effective_end": "2026-11-23T00:00:00+00:00",
    }
    coverage_relation = {
        "id": COVERAGE_RELATION,
        "approved": True,
        "source_ids": [COVERAGE_SOURCE],
        "keys": ["record_id", "complete", "covered_wafer_ids", "covered_source_ids", "window_start", "window_end", "missing_record_ids"],
        "cardinality": "one coverage record to an explicitly listed wafer population and time window",
        "grain": "one exposure coverage record per population and time window",
        "effective_start": "2026-11-20T00:00:00+00:00",
        "effective_end": "2026-11-23T00:00:00+00:00",
    }
    events = []
    for wafer_index, wafer_id in enumerate(wafer_ids):
        chamber_id = "C1" if wafer_index % 2 == 0 else "C2"
        for step_index in range(steps_per_wafer):
            events.append({
                "wafer_id": wafer_id,
                "step_instance_id": f"{wafer_id}-S{step_index:04d}",
                "operation": ("ETCH" if step_index % 3 == 0 else "MET"),
                "timestamp": (BASE_TIME + timedelta(seconds=step_index)).isoformat(),
                "chamber_id": chamber_id,
                "source_id": PROCESS_SOURCE,
                "relationship_id": EVENT_RELATION,
                "approved_relationship": True,
            })
    outcomes = [{
        "wafer_id": wafer_id,
        "lot_id": LOT_ID,
        "label": "NORMAL" if index % 2 == 0 else "ABNORMAL",
        "timestamp": "2026-11-21T04:00:00+00:00",
        "source_id": OUTCOME_SOURCE,
        "relationship_id": OUTCOME_RELATION,
        "approved_relationship": True,
    } for index, wafer_id in enumerate(wafer_ids)]
    return {
        "events": events,
        "outcomes": outcomes,
        "cohort": wafer_ids,
        "target_lot_id": LOT_ID,
        "sources": [event_source, outcome_source, coverage_source],
        "relationships": [event_relation, outcome_relation, coverage_relation],
        "suspected_exposure": {
            "chamber_id": "C1", "start": WINDOW_START, "end": WINDOW_END,
        },
        "coverage": {
            "complete": True,
            "covered_wafer_ids": wafer_ids,
            "missing_record_ids": [],
            "source_ids": [COVERAGE_SOURCE],
            "covered_source_ids": [PROCESS_SOURCE],
            "relationship_id": COVERAGE_RELATION,
            "record_id": "SYN_SCALE_COVERAGE_ROW",
            "window_start": WINDOW_START,
            "window_end": WINDOW_END,
        },
    }


def verify_independent_oracle(data: dict, result: dict, event_count: int) -> None:
    wafer_ids = data["cohort"]
    steps_per_wafer = event_count // WAFER_COUNT
    expected_operations = ["ETCH" if step % 3 == 0 else "MET" for step in range(steps_per_wafer)]
    expected_exposed = [wafer for i, wafer in enumerate(wafer_ids) if i % 2 == 0]
    expected_unexposed = [wafer for i, wafer in enumerate(wafer_ids) if i % 2 == 1]
    if result.get("status") != "VALID":
        raise AssertionError(f"{event_count} events returned {result.get('status')} instead of VALID.")
    journeys = next(item["journeys"] for item in result["transformations"]
                    if item.get("id") == "p2-journey-and-route-variants-v1")
    if [item["wafer_id"] for item in journeys] != wafer_ids:
        raise AssertionError("Journey wafer set/order differs from independent cohort expectation.")
    for journey in journeys:
        expected_step_ids = [f"{journey['wafer_id']}-S{step:04d}" for step in range(steps_per_wafer)]
        actual_steps = journey["steps"]
        if [step["step_instance_id"] for step in actual_steps] != expected_step_ids:
            raise AssertionError(f"Step-instance chronology differs for {journey['wafer_id']}.")
        if [step["operation"] for step in actual_steps] != expected_operations:
            raise AssertionError(f"Route operation sequence differs for {journey['wafer_id']}.")
        if journey["route_conformance"] != "NO_APPROVED_EXPECTED_ROUTE":
            raise AssertionError("Benchmark without an expected route must not claim route conformance.")
    variants = next(item["route_variants"] for item in result["transformations"]
                    if item.get("id") == "p2-journey-and-route-variants-v1")
    if len(variants) != 1 or variants[0]["wafer_ids"] != wafer_ids or variants[0]["count"] != WAFER_COUNT:
        raise AssertionError("Route-variant grouping differs from independent expectation.")
    if result["artifacts"][0]["scope"].get("target_lot_id") != LOT_ID:
        raise AssertionError("Target-lot scope was not retained in the evidence envelope.")
    if result["artifacts"][0]["scope"].get("target_wafer_ids") != wafer_ids:
        raise AssertionError("Outcome-linked target-lot membership differs from the expected wafer set.")
    populations = {item["classification"]: item["wafer_ids"] for item in result["populations"]}
    if populations.get("EXPOSED") != expected_exposed:
        raise AssertionError("Exact-chamber exposure set differs from independent expectation.")
    if populations.get("POTENTIALLY_EXPOSED") != []:
        raise AssertionError("Complete, exact synthetic coverage should not leave possible exposure.")
    if populations.get("NOT_OBSERVED_EXPOSED") != expected_unexposed:
        raise AssertionError("Not-observed-exposed set differs from independent expectation.")
    counter = result["counterevidence"][0]
    expected_cross_tab = {
        "normal_wafers_with_exact_exposure": expected_exposed,
        "abnormal_wafers_not_observed_exposed": expected_unexposed,
        "abnormal_wafers_with_exact_exposure": [],
        "normal_wafers_not_observed_exposed": [],
        "outcomes_with_unknown_exposure": [],
        "population_wafers_missing_outcome": [],
    }
    if any(counter.get(key) != value for key, value in expected_cross_tab.items()):
        raise AssertionError("Outcome/exposure cross-tab differs from independent expectation.")


def main() -> None:
    measurements = []
    for event_count in EVENT_SIZES:
        data = build_snapshot(event_count)
        input_bytes = len(json.dumps(data, separators=(",", ":")).encode("utf8"))
        warmup = analyze(data)
        verify_independent_oracle(data, warmup, event_count)
        latencies = []
        for _ in range(RUNS):
            start = time.perf_counter()
            result = analyze(data)
            latencies.append((time.perf_counter() - start) * 1000)
            if result.get("status") != "VALID":
                raise AssertionError(f"{event_count} events failed during timed analysis.")
        tracemalloc.start()
        measured = analyze(data)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        verify_independent_oracle(data, measured, event_count)
        measurements.append({
            "event_count": event_count,
            "wafer_count": WAFER_COUNT,
            "steps_per_wafer": event_count // WAFER_COUNT,
            "outcome_count": len(data["outcomes"]),
            "compact_json_bytes": input_bytes,
            "compact_json_within_25_mib_limit": input_bytes <= MAX_PAYLOAD_BYTES,
            "runs": RUNS,
            "analysis_p50_ms": statistics.median(latencies),
            "analysis_p95_ms": percentile(latencies, .95),
            "analysis_peak_traced_bytes_one_run": peak_bytes,
            "oracle_status": "PASS",
        })
        del warmup, measured, data, result

    baseline_p50 = measurements[0]["analysis_p50_ms"]
    baseline_p95 = measurements[0]["analysis_p95_ms"]
    for item in measurements:
        item["p50_ratio_vs_100_events"] = item["analysis_p50_ms"] / baseline_p50
        item["p95_ratio_vs_100_events"] = item["analysis_p95_ms"] / baseline_p95
    report = {
        "status": "PASS_SYNTHETIC_ANALYSIS_SCALING",
        "protocol": "docs/ANALYSIS_SCALING_BENCHMARK_PROTOCOL.md",
        "network_used": False,
        "dependencies": "Python standard library and the local P2 engine only; no package installed or fetched.",
        "host": {
            "os": platform.system(), "release": platform.release(),
            "architecture": platform.machine(), "python": sys.version,
        },
        "measurement": {
            "timed_operation": "Complete products.p2.engine.analyze() call after one untimed warm-up.",
            "runs_per_workload": RUNS,
            "percentile_method": "Nearest rank; p95 of seven measurements is the maximum observed sample.",
            "payload_limit_bytes": MAX_PAYLOAD_BYTES,
            "expected_oracle": "100 ordered journeys, one route variant, exact C1 exposure for 50 normal wafers, not-observed-exposed for 50 abnormal wafers under caller-declared source-linked coverage, zero unknown/missing outcomes.",
        },
        "workloads": measurements,
        "limitations": [
            "Synthetic rows do not establish fab-scale or metrology-volume performance.",
            "The workload uses one process source and one outcome source; it does not measure live catalog discovery or source selection quality.",
            "No engineer time study, target-host threshold, or external OSS graph/process-mining comparison was performed.",
            "The 100,000-event point measures the local engine's declared row ceiling; compact JSON size is reported separately against the 25 MiB request limit.",
        ],
    }
    target = ROOT / "qualification" / "evidence" / "benchmark-analysis-scaling.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
