---
name: p2-manufacturing-forensics
description: Reconstruct and review verified wafer journeys, tool exposure, route variants, and counterevidence for FAB Process Forensics P2.
---

# P2 manufacturing evidence workflow

Use this skill for changes to B01 wafer journeys, B02 exposure analysis, B03 routes and rework, or B05 hypothesis and counterevidence output.

1. Read `GOAL.md`, `docs/PRODUCT_SPEC.md`, `docs/SCIENCE_AND_METHODS.md`, `contracts/SHARED_ARCHITECTURE.md`, `docs/INPUT_SNAPSHOT_CONTRACT.md`, and `requirements/AUTHORITY_AND_GAPS.md` before changing evidence semantics. Keep the v1 shared contract frozen unless a versioned RFC is authorized.
2. Treat wafer IDs, lot membership, operation definitions, process step instances, routes, tools, and chambers as distinct typed records. Repeated processing uses distinct step instance IDs. Preserve source IDs, relationship IDs, declared keys, grain, source version, effective time, and content hashes.
3. Order only timezone-aware event times. Preserve record time separately. Represent clock error as intervals; ties or overlapping intervals remain unordered. Duplicate records require an explicit duplicate policy and provenance; missing events produce an incomplete/ambiguous history state.
4. Traverse only source-approved, effective-dated relationships. Every material edge and derived chronological adjacency must carry its input record IDs, relationship approval references, and derivation method. Do not merge aliases, split/merge objects, or infer paths from labels or matching IDs.
5. Keep process operations separate from actual process-step instances. Route conformance requires the verified route definition/version and complete event coverage; permitted exceptions and rework must be explicit. Incomplete history is not a route violation.
6. Classify exposure only from an observed processing instance on the exact selected chamber or exact equipment ID and time interval. A tool group, nearby event, overlapping interval, or caller-entered condition label alone is not exposure. Keep verified maintenance/change events as separate context evidence. Missing assignments or clock ambiguity remain potentially exposed/unknown.
7. Compare exposed, not-observed-exposed, potentially exposed, and unknown populations only under stated coverage. Show normal wafers sharing the suspected exposure, abnormal wafers lacking it, missing outcomes, coverage gaps, product-mix/time/equipment confounders, and non-discriminating observations.
8. Separate verified observations, statistical association, proposed explanation, and causal conclusion. The P2 deterministic engine may make descriptive comparisons; it must not assert a root cause. A next verification step must name only a frozen logical read operation and the evidence gap it addresses; it cannot invent a company endpoint or source mapping.
9. Before closing a change, add independent expected-answer cases, adversarial false-relationship and uncertainty cases, and a reproducible engineer workflow. Preserve synthetic labels and do not present synthetic results as company evidence.

Relevant source adaptation: `research/golden-agentic-engineering/opencode-skills/golden-manufacturing-data.SKILL.md` and `workflows/task-routing.json` from the pinned Golden reference. Golden's status and nonqualification limits are recorded in `research/golden-agentic-engineering/REFERENCE.md`.
