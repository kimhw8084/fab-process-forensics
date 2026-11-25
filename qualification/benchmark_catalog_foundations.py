"""Compare in-memory dictionaries with the installed stdlib SQLite binding."""
from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fabintel.catalog import synthetic_catalog

TABLE_COUNT = 13_000
QUERY_COUNT = 1_000
RUNS = 15
SEED = 20261122
WINDOW_START = "2026-11-21T00:00:00+00:00"
WINDOW_END = "2026-11-21T01:00:00+00:00"
EFFECTIVE_START = "2026-11-20T00:00:00+00:00"
EFFECTIVE_END = "2026-11-22T00:00:00+00:00"
KEY = "step_instance_id"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999)))]


def build_catalog() -> list[dict]:
    catalog = synthetic_catalog(TABLE_COUNT, seed=SEED)
    for index, source in enumerate(catalog):
        target = catalog[(index + 1) % len(catalog)]
        source["relationships"] = [{
            "target_id": target["id"],
            "approved": index % 5 != 0,
            "keys": [KEY],
            "cardinality": "one declared source row to one target source row",
            "effective_start": EFFECTIVE_START,
            "effective_end": EFFECTIVE_END,
        }]
    return catalog


def build_queries(catalog: list[dict]) -> list[tuple[str, str, str, str, str]]:
    queries = []
    for query_index in range(QUERY_COUNT):
        source_index = (query_index * 37) % len(catalog)
        target_index = (source_index + (1 if query_index % 5 else 2)) % len(catalog)
        key = KEY if query_index % 11 else "not_declared_key"
        start, end = WINDOW_START, WINDOW_END
        if query_index % 13 == 0:
            start, end = "2026-11-23T00:00:00+00:00", "2026-11-23T01:00:00+00:00"
        queries.append((catalog[source_index]["id"], catalog[target_index]["id"], key, start, end))
    return queries


def oracle_lookup(query: tuple[str, str, str, str, str], catalog: list[dict]) -> bool:
    source_id, target_id, key, start, end = query
    sources = {row["id"]: row for row in catalog}
    source = sources.get(source_id)
    target = sources.get(target_id)
    if not (source and target and source.get("approved") is True and target.get("approved") is True):
        return False
    if key not in source.get("columns", []) or key not in target.get("columns", []):
        return False
    for relationship in source.get("relationships", []):
        if not isinstance(relationship, dict) or relationship.get("target_id") != target_id:
            continue
        if relationship.get("approved") is not True or key not in relationship.get("keys", []):
            continue
        if not relationship.get("cardinality"):
            continue
        if relationship.get("effective_start", "") <= start and end <= relationship.get("effective_end", ""):
            return True
    return False


def build_dictionary_index(catalog: list[dict]):
    sources = {row["id"]: row for row in catalog}
    relationships = {}
    for source in catalog:
        for relationship in source["relationships"]:
            relationships[(source["id"], relationship["target_id"])] = relationship
    return sources, relationships


def dictionary_lookup(index, query: tuple[str, str, str, str, str]) -> bool:
    source_id, target_id, key, start, end = query
    sources, relationships = index
    source, target = sources.get(source_id), sources.get(target_id)
    relationship = relationships.get((source_id, target_id))
    return bool(
        source and target and relationship
        and source.get("approved") is True and target.get("approved") is True
        and key in source.get("columns", []) and key in target.get("columns", [])
        and relationship.get("approved") is True and key in relationship.get("keys", [])
        and relationship.get("cardinality")
        and relationship.get("effective_start", "") <= start
        and end <= relationship.get("effective_end", "")
    )


def build_sqlite_index(catalog: list[dict]) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE source(id TEXT PRIMARY KEY, approved INTEGER NOT NULL);
        CREATE TABLE source_column(source_id TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY(source_id, name));
        CREATE TABLE relationship(
            source_id TEXT NOT NULL, target_id TEXT NOT NULL, approved INTEGER NOT NULL,
            cardinality TEXT NOT NULL, effective_start TEXT NOT NULL, effective_end TEXT NOT NULL,
            PRIMARY KEY(source_id, target_id)
        );
        CREATE TABLE relationship_key(
            source_id TEXT NOT NULL, target_id TEXT NOT NULL, name TEXT NOT NULL,
            PRIMARY KEY(source_id, target_id, name)
        );
    """)
    connection.executemany("INSERT INTO source VALUES (?, ?)", (
        (row["id"], int(row["approved"] is True)) for row in catalog
    ))
    connection.executemany("INSERT INTO source_column VALUES (?, ?)", (
        (row["id"], column) for row in catalog for column in row["columns"]
    ))
    connection.executemany("INSERT INTO relationship VALUES (?, ?, ?, ?, ?, ?)", (
        (row["id"], relation["target_id"], int(relation["approved"] is True),
         relation["cardinality"], relation["effective_start"], relation["effective_end"])
        for row in catalog for relation in row["relationships"]
    ))
    connection.executemany("INSERT INTO relationship_key VALUES (?, ?, ?)", (
        (row["id"], relation["target_id"], key)
        for row in catalog for relation in row["relationships"] for key in relation["keys"]
    ))
    return connection


SQL_LOOKUP = """
    SELECT 1
    FROM source AS source_a
    JOIN source AS source_b ON source_b.id = ?
    JOIN relationship AS relation ON relation.source_id = source_a.id AND relation.target_id = source_b.id
    JOIN source_column AS column_a ON column_a.source_id = source_a.id AND column_a.name = ?
    JOIN source_column AS column_b ON column_b.source_id = source_b.id AND column_b.name = ?
    JOIN relationship_key AS relation_key ON relation_key.source_id = relation.source_id
        AND relation_key.target_id = relation.target_id AND relation_key.name = ?
    WHERE source_a.id = ? AND source_a.approved = 1 AND source_b.approved = 1
        AND relation.approved = 1 AND relation.cardinality <> ''
        AND relation.effective_start <= ? AND ? <= relation.effective_end
    LIMIT 1
"""


def sqlite_lookup(connection: sqlite3.Connection, query: tuple[str, str, str, str, str]) -> bool:
    source_id, target_id, key, start, end = query
    return connection.execute(SQL_LOOKUP, (target_id, key, key, key, source_id, start, end)).fetchone() is not None


def timed_build(fn, catalog):
    start = time.perf_counter()
    value = fn(catalog)
    return value, (time.perf_counter() - start) * 1000


def timed_batch(fn, queries):
    latencies = []
    start_batch = time.perf_counter()
    for query in queries:
        start = time.perf_counter()
        fn(query)
        latencies.append((time.perf_counter() - start) * 1000)
    batch_ms = (time.perf_counter() - start_batch) * 1000
    return latencies, batch_ms


def main() -> None:
    catalog = build_catalog()
    queries = build_queries(catalog)
    expected = [oracle_lookup(query, catalog) for query in queries]
    dictionary_index = build_dictionary_index(catalog)
    sqlite_index = build_sqlite_index(catalog)
    dictionary_actual = [dictionary_lookup(dictionary_index, query) for query in queries]
    sqlite_actual = [sqlite_lookup(sqlite_index, query) for query in queries]
    if dictionary_actual != expected or sqlite_actual != expected:
        raise SystemExit("Foundation comparison failed the independent lookup oracle.")

    for _ in range(100):
        dictionary_lookup(dictionary_index, queries[_])
        sqlite_lookup(sqlite_index, queries[_])
    sqlite_index.close()
    dictionary_latencies, dictionary_batches = [], []
    sqlite_latencies, sqlite_batches = [], []
    dictionary_builds, sqlite_builds = [], []
    for _ in range(RUNS):
        dictionary_index, build_ms = timed_build(build_dictionary_index, catalog)
        dictionary_builds.append(build_ms)
        batch, total = timed_batch(lambda q: dictionary_lookup(dictionary_index, q), queries)
        dictionary_latencies.extend(batch)
        dictionary_batches.append(total)

        sqlite_index, build_ms = timed_build(build_sqlite_index, catalog)
        sqlite_builds.append(build_ms)
        batch, total = timed_batch(lambda q: sqlite_lookup(sqlite_index, q), queries)
        sqlite_latencies.extend(batch)
        sqlite_batches.append(total)
        sqlite_index.close()

    # Keep one connection only long enough to report its in-memory page size.
    page_connection = build_sqlite_index(catalog)
    sqlite_bytes = page_connection.execute("PRAGMA page_count").fetchone()[0] * page_connection.execute("PRAGMA page_size").fetchone()[0]
    page_connection.close()
    exact = dictionary_actual == sqlite_actual == expected
    dict_p95 = percentile(dictionary_latencies, .95)
    sqlite_p95 = percentile(sqlite_latencies, .95)
    dict_total = statistics.median(dictionary_builds) + statistics.median(dictionary_batches)
    sqlite_total = statistics.median(sqlite_builds) + statistics.median(sqlite_batches)
    threshold_pass = exact and sqlite_p95 <= dict_p95 * .75 and sqlite_total <= dict_total
    report = {
        "status": "PASS_COMPARISON" if exact else "FAIL_ORACLE",
        "adoption_screen": "PASS" if threshold_pass else "FAIL_KEEP_DICTIONARY_BASELINE",
        "foundation": "SQLite via the already-installed Python standard-library sqlite3 binding; no package was installed or bundled.",
        "network_used": False,
        "protocol": "docs/OSS_CATALOG_BENCHMARK_PROTOCOL.md",
        "host": {"os": platform.system(), "release": platform.release(), "architecture": platform.machine(), "python": sys.version,
                 "sqlite_runtime": sqlite3.sqlite_version},
        "catalog_table_count": len(catalog),
        "relationship_count": sum(len(row["relationships"]) for row in catalog),
        "query_count_per_run": len(queries),
        "runs_per_measurement": RUNS,
        "oracle": {"query_results_identical": exact, "queries_true": sum(expected), "queries_false": len(expected) - sum(expected),
                   "misses_or_false_joins": 0 if exact else None},
        "dictionary": {"build_p50_ms": statistics.median(dictionary_builds), "build_p95_ms": percentile(dictionary_builds, .95),
                       "lookup_p50_ms": statistics.median(dictionary_latencies), "lookup_p95_ms": dict_p95,
                       "batch_p50_ms": statistics.median(dictionary_batches),
                       "build_plus_batch_p50_ms": dict_total},
        "sqlite": {"build_p50_ms": statistics.median(sqlite_builds), "build_p95_ms": percentile(sqlite_builds, .95),
                   "lookup_p50_ms": statistics.median(sqlite_latencies), "lookup_p95_ms": sqlite_p95,
                   "batch_p50_ms": statistics.median(sqlite_batches), "build_plus_batch_p50_ms": sqlite_total,
                   "in_memory_database_bytes": sqlite_bytes},
        "decision": "SQLite is not adopted unless exact oracle equivalence holds, lookup p95 is at least 25% lower, and build plus 1,000-lookups median time is no slower. This remains a synthetic catalog-only screen.",
    }
    target = ROOT / "qualification" / "evidence" / "benchmark-foundation-comparison.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
