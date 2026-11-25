"""Reproducible local-scale benchmark; it does not use fab data or network."""
import hashlib
import json
import os
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fabintel.catalog import approved_join, synthetic_catalog
from fabintel.project import analyze
RUNS = 15


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999)))]


def timed_ms(fn):
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000


def snapshot():
    source_id = "SYN_BENCH_PROCESS"
    source = {
        "id": source_id, "approved_semantic_version": "SYNTHETIC-BENCH-1",
        "grain": "one process step instance", "source_hash": hashlib.sha256(b"synthetic bench").hexdigest(),
    }
    relationship = {
        "id": "SYN_BENCH_REL", "approved": True, "source_ids": [source_id],
        "keys": ["wafer_id", "step_instance_id", "timestamp", "chamber_id"], "cardinality": "one event to one wafer",
        "grain": "one process step instance", "effective_start": "2026-11-20T00:00:00+00:00",
        "effective_end": "2026-11-22T00:00:00+00:00",
    }
    coverage_source = {
        "id": "SYN_BENCH_COVERAGE", "approved_semantic_version": "SYNTHETIC-BENCH-1",
        "grain": "one exposure coverage record per population and time window",
        "source_hash": hashlib.sha256(b"synthetic bench coverage").hexdigest(),
    }
    coverage_relationship = {
        "id": "SYN_BENCH_COVERAGE_REL", "approved": True,
        "source_ids": [coverage_source["id"]],
        "keys": ["record_id", "complete", "covered_wafer_ids", "covered_source_ids", "window_start", "window_end", "missing_record_ids"],
        "cardinality": "one coverage record to an explicitly listed wafer population and time window",
        "grain": "one exposure coverage record per population and time window",
        "effective_start": "2026-11-20T00:00:00+00:00",
        "effective_end": "2026-11-22T00:00:00+00:00",
    }
    wafers = [f"SYN-W{i:04d}" for i in range(100)]
    rows = []
    for wafer_no, wafer_id in enumerate(wafers):
        for step_no in range(10):
            hour = step_no // 4
            minute = step_no * 5
            rows.append({
                "wafer_id": wafer_id, "step_instance_id": f"{wafer_id}-S{step_no:02d}",
                "operation": ("ETCH" if step_no % 3 == 0 else "MET"),
                "timestamp": f"2026-11-21T{hour:02d}:{minute:02d}:00+00:00",
                "chamber_id": "C1" if (wafer_no + step_no) % 3 == 0 else "C2",
                "source_id": source_id, "relationship_id": relationship["id"],
                "approved_relationship": True,
            })
    return {
        "events": rows, "cohort": wafers, "sources": [source, coverage_source],
        "relationships": [relationship, coverage_relationship],
        "suspected_exposure": {"chamber_id": "C1", "start": "2026-11-21T00:00:00+00:00", "end": "2026-11-21T03:00:00+00:00"},
        "coverage": {"complete": True, "covered_wafer_ids": wafers, "source_ids": [coverage_source["id"]], "missing_record_ids": [],
                     "covered_source_ids": [source_id], "relationship_id": coverage_relationship["id"],
                     "record_id": "SYN_BENCH_COVERAGE_RECORD",
                     "window_start": "2026-11-21T00:00:00+00:00", "window_end": "2026-11-21T03:00:00+00:00"},
    }


def main():
    generation = [timed_ms(lambda: synthetic_catalog(13000, seed=20261122)) for _ in range(RUNS)]
    catalog = synthetic_catalog(13000, seed=20261122)
    lookup = [timed_ms(lambda: approved_join(catalog[0]["id"], catalog[31]["id"], "step_instance_id", catalog,
                                             time_window=("2026-11-21T00:00:00+00:00", "2026-11-21T01:00:00+00:00"))) for _ in range(RUNS)]
    data = snapshot()
    analysis = [timed_ms(lambda: analyze(data)) for _ in range(RUNS)]
    tracemalloc.start()
    analyze(data)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {
        "benchmark_kind": "local synthetic baseline; exploratory, not a release threshold",
        "created_on": "2026-11-22",
        "system": platform.system(), "release": platform.release(), "architecture": platform.machine(),
        "processor": platform.processor() or "not reported", "cpu_count": os.cpu_count(),
        "python": sys.version,
        "runs_per_measurement": RUNS,
        "synthetic_catalog": {"table_count": len(catalog), "generator_p50_ms": statistics.median(generation),
                              "generator_p95_ms": percentile(generation, .95),
                              "unapproved_join_lookup_p50_ms": statistics.median(lookup),
                              "unapproved_join_lookup_p95_ms": percentile(lookup, .95)},
        "event_analysis": {"event_count": len(data["events"]), "wafer_count": len(data["cohort"]),
                           "p50_ms": statistics.median(analysis), "p95_ms": percentile(analysis, .95),
                           "peak_traced_bytes_one_run": peak},
        "decision": "No advanced graph/mining dependency selected; this synthetic run does not prove fab-scale performance or engineering ROI.",
    }
    target = ROOT / "qualification" / "evidence" / "benchmark-local.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
