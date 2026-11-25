# P2 analysis scaling benchmark protocol

Date precommitted: 2026-11-22

## Question

Measure the current deterministic engine's end-to-end `analyze()` cost as a bounded synthetic process snapshot grows to the declared 100,000-event ceiling. This complements the separate catalog lookup screen; it does not establish fab-scale performance.

## Fixed workload

- Workload sizes: 100, 1,000, 10,000, 50,000, and 100,000 event rows.
- Each size contains the same 100 wafer identities, with an equal number of ordered step instances per wafer; route operations follow a fixed repeating ETCH/MET/MET pattern.
- Even-indexed wafers have exact C1 events and NORMAL outcomes. Odd-indexed wafers have C2 events and ABNORMAL outcomes. Every wafer has exactly one outcome row and declared lot membership through a relationship keyed by `wafer_id` and `lot_id`.
- The complete exposure coverage record spans C1 and a timezone-aware three-hour half-open window. The independent expected result is 50 normal exposed wafers, 50 abnormal `NOT_OBSERVED_EXPOSED` wafers under a caller-declared source-linked coverage record, zero unknown exposure, one route variant, 100 journeys, and the exact ordered step-instance sequence for every wafer.
- Use the already-installed Python standard library only. No package installation, file download, network access, model call, or fab data.

## Measurement and acceptance

- Prebuild each snapshot before timing. Run one untimed warm-up and then seven measurements per workload. Time the complete `analyze()` call; do not include snapshot generation or JSON byte counting.
- Record nearest-rank p50/p95 latency, input JSON bytes, event/wafer/outcome counts, and peak traced allocations during one analysis call. Record the host/runtime and scaling ratios relative to 100 events.
- Before timing each size, compare the full result against the independent expected-answer function in the benchmark script. Any mismatch or non-VALID result fails that size; performance numbers cannot compensate.
- The 100,000-row case also records whether its compact JSON representation fits the product's 25 MiB request limit. No absolute fab seconds-saved or latency threshold is asserted without a representative company workload.

## Limits

This is a synthetic event-scaling measurement, not an authorized data benchmark, engineer time study, metrology-volume benchmark, multi-source catalog discovery test, or proof of site capacity. The separate source catalog screen covers 13,000 synthetic sources. E11 remains partial until representative fab workloads, an engineer task study, and external target thresholds exist.
