# P2 implementation decisions

Date: 2026-11-22  
Shared contract: v1.0.0 (unchanged)

## Deterministic baseline and dependencies

Keep event validation, UTC normalization, stable sorting, route comparison, typed adjacency traversal, and exposure classification in the deterministic standard-library engine. Benchmarking found no reason to add a graph runtime dependency. The optional official MCP Python SDK 2.3.0 is vendored only for configurable read-only protocol integration; the core product remains standard-library-only. Its macOS arm64 CPython 3.11 wheelhouse is hash-pinned and offline-install tested.

A precommitted local screen compared the dictionary catalog index with Python's stdlib SQLite binding on 13,000 synthetic sources and 1,000 exact/negative lookups. Both matched the independent answers; SQLite missed the precommitted adoption threshold, so the dictionary baseline remains. This synthetic catalog is not a proxy for Fab Insight semantics or fab-scale performance.

`qualification/benchmark_graph_traversal.py` compared 250 seeded time-scoped relationship neighborhood queries on 100,000 synthetic lot/wafer edges with NetworkX 3.1. The 25 held-out result sets were identical. In the recorded Python 3.11.7 run, typed adjacency built in 85.437 ms with 18,675,972 peak traced bytes and 1.301 ms total query time; NetworkX MultiGraph built in 519.096 ms with 89,047,336 peak traced bytes and 4.040 ms query time. P2 keeps NetworkX as an independent algorithm oracle, not a runtime dependency. This fixture measures relationship traversal, not fab-scale history reconstruction or engineer time.

Object-centric mining screening: the current data contract is a provenance-bearing event/relationship snapshot, not a verified OCEL 2 log. Converting without source semantics could alter event/object identity, time uncertainty, or edge provenance. OCPA is GPL-3.0 and was excluded from the permissive candidate set. `ocel-mine` declares MIT but has no measured advantage for the current conformance task; no dependency was installed or vendored. P2 retains deterministic route-variant/conformance logic and will consider object-centric tooling only after a faithful, held-out fixture demonstrates a correctness or analyst-time gain. DuckDB did not have a bounded analytical workload large enough to justify its runtime; Cytoscape.js remains a P1 shared-shell visualization choice.

The catalog join helper now accepts a join only when a specific approved relationship, key, cardinality, and effective interval are supplied. Table similarity, shared tags, or matching column names never qualify a join.

B01 history completeness now requires a source-linked coverage record that names the process sources it covers, has an effective relationship declaring its coverage fields, and contains each covered event's clock-uncertainty interval. Each named process source also needs an effective relationship for wafer, step-instance, and event-time fields spanning the coverage window. If a covered wafer has an observed event source omitted from that declaration, its history remains `INCOMPLETE`. This is a local caller-declared boundary; it cannot authenticate live source completeness or separately supplied material-edge coverage.

Material-edge membership now compares the full process-event uncertainty interval with edge effectivity. A transfer boundary inside that interval yields `TEMPORALLY_AMBIGUOUS_MEMBERSHIP` and candidate lots; cross-source wafer identity mappings that fail to cover the full interval refuse the merge. Per-entity interval indexes replace repeated full scans for each step. On the precommitted 100,000-edge / 100,000-query synthetic fixture, the interval index matched the independent schedule oracle on all queries and reduced median group/build plus query time from 577 ms to 346 ms (1.67x), with 30.7 MB additional traced setup allocation. This is a microbenchmark, not target or fab performance evidence; see `docs/MATERIAL_EDGE_INDEX_BENCHMARK_PROTOCOL.md` and `qualification/evidence/benchmark-material-edge-index-run.log`.

B01 now follows multiple connected, effective-dated `SPLIT_FROM`/`MERGED_FROM` lot edges from a verified event-lot or time-scoped membership seed. Each edge keeps direction and relationship provenance; possible edge timing or ambiguous membership keeps the complete path possible. `LOT_MEMBERSHIP` edges are not used as lineage traversal hops, so other wafers in the lot do not create inferred paths. A fixed-answer case exercises a two-hop chain, an expired edge, a clock-uncertain split, an unsupported relationship type, and a sibling-wafer trap.

Lineage output now distinguishes an observed lack of a connected split/merge path from proof that no such relationship exists. The generic input contract accepts a caller-declared material coverage record only when its approved source relationship covers the typed entity population, split/merge (and membership where needed) relationship types, material source IDs, missing-record list, and full event-time interval. Otherwise coverage remains `NOT_ESTABLISHED` or `INCOMPLETE_OR_UNKNOWN`. Even accepted local coverage remains unauthenticated against a live source; company-specific completeness semantics remain internal.

## Full-engine scaling

A separate precommitted synthetic screen measured the complete `analyze()` call at 100, 1,000, 10,000, 50,000, and 100,000 process events over 100 wafers, with outcome-linked lot membership and an independently checked exposure/counterevidence cross-tab. All five workload sizes matched the direct reference oracle after source-linked coverage enforcement. In the latest run, the 100,000-event point measured p95 2,380.8 ms, peak traced analysis allocations 427,930,494 bytes, and compact input JSON 24,259,581 bytes, within the local 25 MiB request limit. These host measurements are synthetic and no fab latency or memory threshold is inferred. See `docs/ANALYSIS_SCALING_BENCHMARK_PROTOCOL.md` and `qualification/evidence/benchmark-analysis-scaling.json`.

Exposure can be scoped to one exact chamber or exact tool ID over a timezone-aware window. A supplied chamber selects chamber mode even when a tool ID is also present as context. Tool-only mode matches the event's exact `tool_id`; missing tool assignment remains unknown and does not infer chamber membership.

The start control also accepts a caller label for `PROCESS`, `MAINTENANCE`, or `CHANGE` interval context. This is not condition evidence: the analysis envelope explicitly marks the label `CALLER_SUPPLIED_UNVERIFIED`, and exact exposure remains determined only by source-linked process events, equipment scope, time bounds, and source-linked coverage records. Those records remain caller-declared until authenticated by a live authorized source.

All process events and outcome rows must reference declared source and relationship records. The `approved_relationship` Boolean alone is insufficient and produces a refusal. The UI's local preflight checks relationship references, effective times, event/outcome row usage, scope, coverage, and request limits before analysis; it does not authenticate those declarations or query a source.

## Local analysis cancellation

The local UI can now cancel a running deterministic analysis or request cancellation when the input changes. Each analysis carries a UUID over the authenticated loopback API. The per-server registry limits active analysis to one, limits pending cancellation IDs to 32 with a 60-second expiry, retains only 128 completed IDs for replay refusal, and caps concurrent non-cancellation API requests at two. The engine checks cancellation during event, relationship, exposure, route, outcome, and evidence construction loops; cancellation returns a control response without a partial evidence envelope. Server shutdown signals active requests and waits for their request threads. Tests exercise mid-engine cancellation, active API cancellation, cancellation arriving before analysis registration, and client stale-result handling. This only governs the synthetic local engine; a future MCP adapter needs its own verified bounded-query cancellation and audit semantics.

## Model use

No LLM is included. User scope is structured JSON; the deterministic engine owns event ordering, route comparisons, exposure populations, and counterevidence. This avoids a model path that cannot add verified facts or authorization in this local-only build.

Local lot starts derive their wafer set only from caller-supplied outcome rows whose declared effective-dated relationship includes both `lot_id` and `wafer_id` keys. At least one row must be `ABNORMAL`; normal rows stay in the selected cohort. The engine records those rows and the selected lot ID, while explicitly stating that a local snapshot may omit lot members. No lot discovery or membership inference from process-event histories is performed.

## Scope and unresolved dependencies

The adapter is externally exercised against synthetic stdio and Streamable HTTP MCP servers. There are no actual company tool names, source definitions, permission scopes, target deployment configuration, or approved model endpoint details; none are guessed. Literal R01–R53 text remains unavailable. The Golden reference is staged at the user-pinned commit and its applicable instructions were adapted as Codex skills, but it is not company-qualified. `INTERNAL_AUTHORIZED` mode remains unavailable; local snapshots are labeled `SYNTHETIC_DEMO`.

## Scientific boundaries

- Same-chamber event time in a half-open query window is a descriptive processing match, not a causal exposure effect.
- Missing chamber or incomplete query coverage cannot produce a verified non-exposed population.
- Route mismatch is reported only against an approved expected route with complete route coverage; it is an observed difference for engineering review, not a declared process violation.
- Cross-source wafer tokens require an explicit approved identity relationship. Aliases are retained separately.
- Time ties are detected within the same wafer only; ties between different wafers do not obscure either wafer's route order.

## Verification

Independent oracle cases are maintained in `tests/test_p2_challenges.py`; seeded chamber/tool and counterevidence sweeps use direct set/cross-tab oracles. `tests/test_heldout_adversarial.py` adds separate fixed-answer public-contract cases without sharing those test helpers; it is not a blinded holdout. Local HTTP checks cover the loopback UI/API and synthetic MCP transport. The current pip-audit scan found no known vulnerabilities in the pinned MCP dependency closure. External target-OS, site network-isolation, source-owner/license-transfer, blinded engineer review, and corporate authorization evidence remains pending.

## Local accessibility follow-up

A browser replay showed that the clipped file input could receive keyboard focus without a visible focus indicator. Replace that focus path with a visible **Open JSON file** button that activates the native file input. Add captions, `thead`/`tbody`, and `scope="col"` to dynamic tables; separate the short polite preflight announcement from the full provenance region; and name the findings region used for post-analysis focus. The actual local browser exercised the keyboard-activated file chooser, preflight, analysis, and downloaded export. The fixture is synthetic; native OS dialog operation, screen-reader review, and target-host acceptance are not claimed.
