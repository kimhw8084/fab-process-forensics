"""Compare time-scoped material-edge lookup with an independent scan oracle."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from products.p2.engine import (  # noqa: E402
    _build_material_edge_interval_indexes,
    _material_edges_intersecting_time,
)

WAFERS = 1_000
EDGES_PER_WAFER = 100
EVENTS_PER_WAFER = 100
TRIALS = 3
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
UNCERTAINTY = timedelta(seconds=60)


def build_fixture():
    edges = []
    edge_times = {}
    by_entity = defaultdict(list)
    queries = []
    for wafer_index in range(WAFERS):
        wafer_id = f"W-{wafer_index:04d}"
        for day_index in range(EDGES_PER_WAFER):
            edge_id = f"M-{wafer_index:04d}-{day_index:03d}"
            edge = {
                "record_id": edge_id,
                "from_entity": {"type": "lot", "id": f"L-{wafer_index:04d}-{day_index:03d}"},
                "to_entity": {"type": "wafer", "id": wafer_id},
            }
            start = BASE + day_index * DAY
            end = start + DAY
            edges.append(edge)
            edge_times[edge_id] = (start, end)
            by_entity[("wafer", wafer_id)].append(edge)

        for query_index in range(EVENTS_PER_WAFER):
            boundary = query_index % 10 == 0
            center = BASE + query_index * DAY + (timedelta(0) if boundary else timedelta(hours=12))
            uncertainty = UNCERTAINTY if boundary else timedelta(0)
            queries.append({
                "wafer_id": wafer_id,
                "day_index": query_index,
                "boundary": boundary,
                "low": center - uncertainty,
                "high": center + uncertainty,
            })
    return edges, edge_times, by_entity, queries


def status(edge, low, high, edge_times):
    start, end = edge_times[edge["record_id"]]
    return (
        edge["record_id"],
        "EFFECTIVE_ACROSS_EVENT_TIME_UNCERTAINTY"
        if start <= low and high < end
        else "POSSIBLY_EFFECTIVE_DUE_TO_CLOCK_UNCERTAINTY",
    )


def scan_query(query, by_entity, edge_times):
    rows = by_entity[("wafer", query["wafer_id"])]
    return sorted(
        (status(edge, query["low"], query["high"], edge_times)
         for edge in rows
         if query["low"] < edge_times[edge["record_id"]][1]
         and query["high"] >= edge_times[edge["record_id"]][0]),
    )


def index_query(query, indexes, edge_times):
    index = indexes[("wafer", query["wafer_id"])]
    return sorted(
        status(edge, query["low"], query["high"], edge_times)
        for edge in _material_edges_intersecting_time(index, query["low"], query["high"], edge_times)
    )


def independent_expected(query):
    day_index = query["day_index"]
    prefix = query["wafer_id"].replace("W-", "M-")
    if query["boundary"]:
        days = [day_index - 1, day_index] if day_index else [0]
        return sorted(
            (f"{prefix}-{index:03d}", "POSSIBLY_EFFECTIVE_DUE_TO_CLOCK_UNCERTAINTY")
            for index in days
        )
    return [(f"{prefix}-{day_index:03d}", "EFFECTIVE_ACROSS_EVENT_TIME_UNCERTAINTY")]


def measure(method, edges, edge_times, by_entity, queries):
    build_ms = []
    query_ms = []
    peak_bytes = 0
    result_count = ambiguous_count = 0
    for _ in range(TRIALS):
        start = time.perf_counter_ns()
        indexes = None
        # Grouping is shared setup required by both approaches.
        grouped = defaultdict(list)
        for edge in edges:
            grouped[(edge["from_entity"]["type"], edge["from_entity"]["id"])].append(edge)
            grouped[(edge["to_entity"]["type"], edge["to_entity"]["id"])].append(edge)
        if method == "interval_index":
            indexes = _build_material_edge_interval_indexes(grouped, edge_times)
        build_ms.append((time.perf_counter_ns() - start) / 1_000_000)

        started = time.perf_counter_ns()
        for query in queries:
            result = (index_query(query, indexes, edge_times) if method == "interval_index"
                      else scan_query(query, grouped, edge_times))
            result_count += len(result)
            ambiguous_count += sum(
                item[1] == "POSSIBLY_EFFECTIVE_DUE_TO_CLOCK_UNCERTAINTY" for item in result
            )
        query_ms.append((time.perf_counter_ns() - started) / 1_000_000)
    # Trace a separate allocation run so instrumentation cannot distort timing.
    tracemalloc.start()
    grouped = defaultdict(list)
    for edge in edges:
        grouped[(edge["from_entity"]["type"], edge["from_entity"]["id"])].append(edge)
        grouped[(edge["to_entity"]["type"], edge["to_entity"]["id"])].append(edge)
    if method == "interval_index":
        _build_material_edge_interval_indexes(grouped, edge_times)
    _current, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "trials": TRIALS,
        "build_median_ms": statistics.median(build_ms),
        "query_median_ms": statistics.median(query_ms),
        "end_to_end_median_ms": statistics.median([a + b for a, b in zip(build_ms, query_ms)]),
        "end_to_end_samples_ms": [round(a + b, 3) for a, b in zip(build_ms, query_ms)],
        "peak_traced_setup_bytes": peak_bytes,
        "result_count_across_trials": result_count,
        "possible_edge_count_across_trials": ambiguous_count,
    }


def main():
    edges, edge_times, by_entity, queries = build_fixture()
    expected_total = 0
    for query in queries:
        expected = independent_expected(query)
        scanned = scan_query(query, by_entity, edge_times)
        if scanned != expected:
            raise SystemExit(f"Scan/oracle mismatch: {query!r}: {scanned!r} != {expected!r}")
        expected_total += len(expected)

    indexes = _build_material_edge_interval_indexes(by_entity, edge_times)
    for query in queries:
        indexed = index_query(query, indexes, edge_times)
        expected = independent_expected(query)
        if indexed != expected:
            raise SystemExit(f"Index/oracle mismatch: {query!r}: {indexed!r} != {expected!r}")

    scan = measure("scan", edges, edge_times, by_entity, queries)
    indexed = measure("interval_index", edges, edge_times, by_entity, queries)
    ratio = scan["end_to_end_median_ms"] / indexed["end_to_end_median_ms"]
    report = {
        "status": "PASS_SYNTHETIC_MATERIAL_EDGE_INDEX" if ratio >= 1.25 else "NO_ADOPTION_ADVANTAGE",
        "protocol": "docs/MATERIAL_EDGE_INDEX_BENCHMARK_PROTOCOL.md",
        "synthetic_only": True,
        "network_used": False,
        "dependencies": "Python standard library and the local P2 engine only.",
        "host": {
            "os": platform.system(), "release": platform.release(),
            "architecture": platform.machine(), "python": sys.version,
        },
        "workload": {
            "wafer_count": WAFERS,
            "membership_edge_count": len(edges),
            "event_time_queries": len(queries),
            "boundary_uncertainty_queries": sum(query["boundary"] for query in queries),
            "oracle_result_count_per_trial": expected_total,
        },
        "correctness": "PASS: exhaustive scan and interval index match the fixture-derived oracle for every query.",
        "exhaustive_scan": scan,
        "interval_index": indexed,
        "end_to_end_speedup": ratio,
        "additional_traced_index_setup_bytes": (
            indexed["peak_traced_setup_bytes"] - scan["peak_traced_setup_bytes"]
        ),
        "decision_rule": "Retain only with exact oracle agreement and at least 1.25x median end-to-end speedup.",
        "limitations": [
            "Regular synthetic membership intervals do not represent fab data or split/merge frequency.",
            "This measures material-edge lookup only, not full analysis, source discovery, or engineer task time.",
            "No fab-scale or target-host performance claim is made.",
        ],
    }
    target = ROOT / "qualification" / "evidence" / "benchmark-material-edge-index.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS_SYNTHETIC_MATERIAL_EDGE_INDEX":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
