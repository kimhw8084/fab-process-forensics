# Time scoped material edge index benchmark

Date precommitted: 2026-11-22

## Question

Does a standard-library interval index reduce the end-to-end cost of locating time-relevant lot-membership edges across a bounded 100,000-event snapshot, compared with scanning every edge attached to each wafer?

## Fixed workload

- Generate 1,000 synthetic wafer identities, each with 100 contiguous one-day lot-membership intervals: 100,000 typed edges.
- Generate 100 events per wafer: 100,000 point or uncertainty-interval queries.
- Every tenth query is placed exactly at a lot-transfer boundary with a ±60-second clock interval. Other queries occur at midday inside one interval.
- Use UTC datetimes, half-open edge effectivity, and the product's rule that an edge is definite only when the complete event-time uncertainty interval is contained by its effectivity interval.
- Compare the time-index lookup with a simple exhaustive scan over the same wafer edges. An independent fixture-derived oracle specifies the expected edge IDs and definite/possible status for every query.
- Run three measured batches per method. Include grouping/index build and all 100,000 lookups in the end-to-end measurement. Record setup and query time separately, host/runtime, result counts, and peak traced allocation for both baseline grouping and indexed setup from separate un-timed builds so allocation tracing cannot distort the timing comparison.

## Decision rule

Retain the interval index only if the indexed and exhaustive results match the independent oracle for every query and its median end-to-end time is at least 25% lower than the scan baseline. Any correctness mismatch rejects the change regardless of speed. Report this as a synthetic local algorithm screen, not fab-scale or engineer-time evidence.

## Limits

This benchmark uses a regular synthetic schedule and tests only time-scoped edge lookup. It does not measure source discovery, route reconstruction, actual lot splitting/merging frequencies, fab data volume, target-host performance, or user task time. The index adds standard-library data structures but no runtime package dependency.
