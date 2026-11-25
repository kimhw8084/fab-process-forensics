# Local OSS catalog foundation screen

Date precommitted: 2026-11-22

## Question

For exact source/relationship catalog lookups at the launchkit's synthetic 13,000-record scale, does SQLite offer a measurable advantage over the existing deterministic in-memory dictionary approach?

## Methods

- Use only the launchkit's deterministic synthetic catalog generator and Python's already-available standard-library `sqlite3` binding to the installed SQLite runtime. Do not install, download, or bundle any dependency.
- Add a fixed one-to-one caller-declared relationship per synthetic source, with approved and refused cases, then run a seeded batch of 1,000 exact and negative lookups.
- Apply the same predicate to both methods: exact source IDs, both source approval flags, declared key on both sources and the relationship, nonempty cardinality, and effective interval covering a timezone-aware UTC window.
- Compute an independent expected Boolean for each query by scanning the original catalog rows. Require identical results for every lookup before comparing speed.
- Measure index construction, per-lookup p50/p95, total 1,000-lookup batch time after index construction, and SQLite page bytes. Run each measurement 15 times on the current host.

## Precommitted adoption screen

Consider a SQLite lookup foundation only if it matches the independent oracle for every query, lowers lookup p95 by at least 25%, and does not increase the combined index-build plus 1,000-lookup median time. This is an exploratory screening rule for the synthetic workload, not a fab-scale release threshold. If it fails, retain the simpler dictionary baseline and do not add SQLite as a product dependency.

## Limits

This screen measures catalog lookup only. It does not evaluate graph traversal, object-centric mining, source discovery quality, actual Fab Insight mappings, fab-scale data, memory parity between Python and SQLite's native allocator, licensing of a bundled runtime, or engineer task time. The Python standard-library binding is not an added product dependency.
