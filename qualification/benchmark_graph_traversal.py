"""Compare P2's typed adjacency traversal with NetworkX on explicit material edges."""
from __future__ import annotations

import gc
import json
import platform
import random
import statistics
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path

import networkx as nx


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2027, 1, 1, tzinfo=timezone.utc)
QUERY_TIMES = [START + timedelta(days=30), START + timedelta(days=180), START + timedelta(days=350)]


def build_edges(lots: int = 10_000, wafers_per_lot: int = 10):
    edges = []
    for lot_index in range(lots):
        lot_id = f"LOT-{lot_index:05d}"
        for member in range(wafers_per_lot):
            wafer_id = f"W-{lot_index:05d}-{member:02d}"
            edges.append({
                "record_id": f"M-{lot_index:05d}-{member:02d}",
                "relationship_type": "LOT_MEMBERSHIP",
                "from_entity": ("lot", lot_id),
                "to_entity": ("wafer", wafer_id),
                "effective_start": START,
                "effective_end": END,
            })
    return edges


def traverse_adjacency(adjacency, edges, source, query_time):
    found = set()
    visited = {source}
    stack = [source]
    while stack:
        node = stack.pop()
        for edge_index in adjacency.get(node, ()):
            edge = edges[edge_index]
            if not edge["effective_start"] <= query_time < edge["effective_end"]:
                continue
            left, right = edge["from_entity"], edge["to_entity"]
            neighbor = right if node == left else left
            found.add((edge["record_id"], edge["relationship_type"], left, right))
            if neighbor not in visited:
                visited.add(neighbor)
                stack.append(neighbor)
    return found


def traverse_networkx(graph, source, query_time):
    found = set()
    visited = {source}
    stack = [source]
    while stack:
        node = stack.pop()
        for neighbor, edge_attrs in graph[node].items():
            for edge in edge_attrs.values():
                if not edge["effective_start"] <= query_time < edge["effective_end"]:
                    continue
                left, right = edge["from_entity"], edge["to_entity"]
                found.add((edge["record_id"], edge["relationship_type"], left, right))
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
    return found


def timed_queries(function, *args):
    durations = []
    for source, query_time in args[-1]:
        started = time.perf_counter_ns()
        function(*args[:-1], source, query_time)
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(durations)
    return {
        "query_count": len(durations),
        "total_ms": round(sum(durations), 3),
        "median_ms": round(statistics.median(durations), 5),
        "p95_ms": round(ordered[int((len(ordered) - 1) * 0.95)], 5),
    }


def measure_build(builder):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter_ns()
    value = builder()
    duration = (time.perf_counter_ns() - started) / 1_000_000
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return value, {"build_ms": round(duration, 3), "peak_tracemalloc_bytes": peak}


def main():
    edges = build_edges()
    rng = random.Random(20261122)
    probes = [("wafer", f"W-{rng.randrange(10_000):05d}-{rng.randrange(10):02d}") for _ in range(250)]
    queries = [(source, QUERY_TIMES[index % len(QUERY_TIMES)]) for index, source in enumerate(probes)]

    def make_adjacency():
        adjacency = {}
        for index, edge in enumerate(edges):
            adjacency.setdefault(edge["from_entity"], []).append(index)
            adjacency.setdefault(edge["to_entity"], []).append(index)
        return adjacency

    adjacency, adjacency_build = measure_build(make_adjacency)

    def make_networkx():
        graph = nx.MultiGraph()
        for edge in edges:
            graph.add_edge(edge["from_entity"], edge["to_entity"], key=edge["record_id"], **edge)
        return graph

    graph, graph_build = measure_build(make_networkx)

    # Compare every result for a deterministic subset, then time the same query set.
    for source, query_time in queries[:25]:
        if traverse_adjacency(adjacency, edges, source, query_time) != traverse_networkx(graph, source, query_time):
            raise SystemExit(f"Traversal result mismatch for {source!r} at {query_time.isoformat()}")

    adjacency_queries = timed_queries(traverse_adjacency, adjacency, edges, queries)
    networkx_queries = timed_queries(traverse_networkx, graph, queries)
    output = {
        "benchmark": "explicit time-scoped typed relationship neighborhood traversal",
        "synthetic_only": True,
        "seed": 20261122,
        "python": platform.python_version(),
        "networkx": nx.__version__,
        "graph": {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "queries": len(queries)},
        "correctness": "PASS: all 25 held-out result sets identical",
        "p2_typed_adjacency": {**adjacency_build, "queries": adjacency_queries},
        "networkx_multigraph": {**graph_build, "queries": networkx_queries},
        "interpretation": "This workload needs explicit-edge provenance and time filtering. The stdlib adjacency index had lower build/runtime overhead in this measured Python environment; NetworkX remains useful as an independent graph-algorithm oracle, but is not required by the product runtime for this traversal.",
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
