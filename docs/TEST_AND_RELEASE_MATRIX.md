# Release-blocking scientific and implementation qualification — FAB Process Forensics

## Critical independently checked case catalog
The following describe expected behaviors **to be implemented and actually executed by Codex**. The bootstrap supplies only a tiny fixed subset, intentionally insufficient for a product-ready claim. Expand to at least the full catalog with richer parameter sweeps, property/metamorphic tests and correctly sequestered holdouts.

| ID | Input challenge | Required behavior | Independent expected-answer source |
|---|---|---|---|
| P2-01 | W1 repeated ETCH step instances | **preserve two distinct ETCH occurrences** | frozen step-instance sequence |
| P2-02 | C1 event and C2 processing same hour | **exclude C2 from exact C1 exposed** | fixed chamber/window oracle |
| P2-03 | event without approved relationship | **REFUSED; never render as factual path** | approval flag oracle |
| P2-04 | wafer with missing chamber but known tool | **unknown chamber exposure, not definitely exposed** | type semantics oracle |
| P2-05 | event timestamp without timezone | **REFUSED/inconclusive time order** | clock ambiguity fixture |
| P2-06 | multiple source wafer aliases collision | **no unapproved ID merge** | namespaced identity fixture |
| P2-07 | maintenance between two chamber jobs | **classify before/after exposure separately** | time window oracle |
| P2-08 | wafer rework loop vs missing event gap | **do not infer route violation from gap** | coverage fixture |
| P2-09 | lot split and merge at dated events | **track membership at each step** | time-effective membership oracle |
| P2-10 | normal wafers share suspected exposure | **contradiction clearly represented** | counterevidence oracle |
| P2-11 | abnormal wafer has no alleged exposure | **alternative needed; no definitive root-cause claim** | negative exposure oracle |
| P2-12 | 13k ambiguous source catalog | **no invalid join accepted; compare baselines** | catalog and approval oracle |
| P2-13 | exact tool scope with a missing event tool assignment | **matching tool exact; missing tool unknown; chamber is not inferred** | fixed and 100-case seeded exact-tool oracles |
| P2-14 | operator labels a suspected maintenance/change interval | **keep label unverified; do not present it as source evidence** | context validation and output-status oracle |
| P2-15 | nonmatching wafer with incomplete source-linked query coverage | **retain unknown exposure; exclude it as a comparator** | fixed coverage source/relationship oracle |
| P2-16 | history coverage omits one of multiple observed event sources | **mark journeys incomplete; do not claim complete process history** | independent fixed-answer multi-source coverage case |
| P2-17 | known tool observation has no chamber move record | **possible chamber exposure; no exact or not-observed classification** | independent fixed-answer missing-move case |
| P2-18 | repeated exact chamber processing within the query window | **retain both instance-level evidence rows for the exposed wafer** | independent fixed-answer repeated-processing case |
| P2-19 | maintenance records bracket the suspected window | **report before/after temporal context only; no causal conclusion** | independent fixed-answer temporal-boundary case |
| P2-20 | event history changes route version and matches a declared alternative | **retain route-version segments; accept only the explicit alternative** | independent fixed-answer route-version case |
| P2-21 | a repeated process instance has a verified rework predecessor | **retain both instances and provenance; exclude rework from base route count** | independent fixed-answer rework case |
| P2-22 | normal wafer shares exposure while abnormal wafer lacks an observed match | **show both counterexamples; no unsupported support, statistic, or cause** | independent fixed-answer hypothesis case |
| P2-23 | lot membership changes over time with a typed split edge | **preserve event-time membership and split provenance; refuse conflicting join keys** | independent fixed-answer material-graph case |
| P2-24 | descendant lot has a two-hop split/merge chain, an expired edge, and a sibling-wafer path | **show only source-declared, time-relevant lot-to-lot paths; preserve direction; exclude expired edges and sibling traversal** | independent fixed-answer multi-hop lineage case |
| P2-25 | event row contains a lot ID absent from its approved relationship keys | **do not use that field to attach unrelated material edges; expose the missing key and keep lineage unknown** | independent fixed-answer undeclared-lot-field case |
| P2-26 | event uncertainty interval crosses the source relationship's effective start while the nominal timestamp is within it | **retain only a possible lineage seed, flag membership ambiguity, and identify the missing full-interval validity evidence** | independent fixed-answer effectivity-boundary case |
| P2-27 | exact exposure event's clock interval crosses the approved source relationship effective start | **classify the population member as unknown, not exposed or an observed-unexposed comparator** | independent fixed-answer exposure effectivity case |
| P2-28 | route coverage declares a population member with no event rows and another member has overlapping event-time intervals | **report declared and observed denominators separately, isolate chronology-uncertain histories, and never invent a route for a no-row member** | independent fixed-answer route denominator case |
| P2-29 | a process row carries chamber context but its source relationship declares only tool identity | **exclude the chamber from hypothesis equipment strata and disclose the unverified field and relationship** | independent fixed-answer counterevidence-context case |
| P2-30 | identical duplicate step-instance copies are followed by a conflicting same-grain chamber record | **collapse exact copies with an explicit count; refuse the conflicting instance and emit no investigation artifact** | independent fixed-answer duplicate/conflict case |
| P2-31 | a verified event lot has no split/merge rows in the submitted material snapshot | **report no connected path observed and keep material-edge completeness NOT_ESTABLISHED** | independent fixed-answer incomplete-material-snapshot case |
| P2-32 | a material completeness record omits an entity, edge type/source, missing record, or full time bound | **accept only a source-linked declared scope covering the lot seed, required relationship types/sources, and full event-time uncertainty; mark it unauthenticated** | independent fixed-answer material-coverage contract case |
| P2-33 | actual processing interval uncertainty crosses the event relationship effective boundary while event timestamp is still inside | **classify the crossing member UNKNOWN and preserve exact classification only for the interval fully inside effectivity** | independent fixed-answer processing-interval effectivity case |
| P2-34 | exposure and route coverage says complete while listing a missing process row, or omits its missing-record declaration | **keep nonmatches UNKNOWN, exclude them as comparators, and prevent route conformance; require the missing-record field in the approved coverage relationship** | independent fixed-answer missing-coverage-record case |
| P2-35 | caller marks an expected route approved but supplies no source-authorized route-definition relationship | **refuse route conformance until the relationship authorizes approval, route identity/version and sequence fields** | independent fixed-answer unlinked-route-definition case |
| P2-36 | expected-route relationship effectivity begins inside an event's clock-uncertainty interval | **report route-definition effectivity as uncertain, preserve source/relationship provenance, and assert neither match nor mismatch** | independent fixed-answer route-effectivity case |
| P2-37 | outcome timestamp appears in a row but is absent from the approved relationship's declared keys | **refuse to use that timestamp for time-stratified hypothesis review** | independent fixed-answer outcome-time provenance case |
| P2-38 | outcomes span product/time strata and an event-bearing cohort member has no outcome | **show only source-authorized strata, preserve covered/observed denominators and missing outcomes, and leave association/cause unestablished** | independent fixed-answer product/time/selection counterexample |
| P2-39 | process-event timestamp is present but absent from the approved wafer-step relationship keys | **refuse chronology and event-time claims that use the undeclared timestamp** | independent fixed-answer process-time provenance case |
| P2-40 | MCP typed rows omit their source/relationship envelope references or the approved relationship omits the plan time key | **reject before analysis unless every returned row is declared by the response and each relationship authorizes the timezone-aware time field** | synthetic-peer protocol compatibility case |
| P2-41 | delayed/out-of-order records have arrival times that reverse event chronology and exposure | **use authorized event time for order and exposure, display arrival time separately, and classify only the covered nonmatch as not observed exposed** | independent fixed-answer event-time-versus-recording-time case |
| P2-42 | two exact equipment patterns have the same outcome/exposure cross-tab and complete coverage | **retain both alternatives without ranking either; association and cause remain unestablished** | independent fixed-answer equal-support equipment-hypothesis case |
| P2-43 | complete route histories include a verified mismatch, a valid allowed alternative, and mixed outcomes | **show route/outcome/exposure groups with exact process and route-definition references; do not rank route causes or infer association or causality** | independent fixed-answer route-pattern counterevidence case |

## MCP protocol adversarial cases

| ID | Input challenge | Required behavior | Independent check |
|---|---|---|---|
| MCP-01 | relationship response repeats an ID with a conflicting join-key definition | **reject the response; do not overwrite one relation with another under the same ID** | `test_relationship_ids_and_join_keys_are_unambiguous_and_source_declared` |
| MCP-02 | approved relationship declares a key absent from all its verified source semantics | **reject the join definition before bounded retrieval** | `test_relationship_ids_and_join_keys_are_unambiguous_and_source_declared` |
| MCP-03 | typed response rows omit their source/relationship envelope reference or plan time key authorization | **reject before analysis** | P2-40 synthetic-peer mutation loop |
| MCP-04 | Streamable HTTP peer denies scope, receives an over-limit request, cancels an active read, then serves a retry | **preserve denial and limit errors, return no partial cancellation result, and verify recovered audit hash** | `test_streamable_http_denial_bounds_cancellation_and_recovery` |
| MCP-05 | semantics response repeats a source ID with conflicting source hashes | **reject duplicate source definitions before relationship validation** | `test_duplicate_source_semantics_records_are_rejected` |

| LOT-START | abnormal lot with normal and abnormal wafer outcome rows | **derive only rows with an approved declared lot_id + wafer_id relationship; preserve normal members; refuse missing membership keys** | caller-supplied outcome rows and exact declared relationship key set |

## Cross-product external release gates
| ID | Check | Evidence required |
|---|---|---|
| E01 | Full integrated scientific workflow, all features | Functional E2E cases, no placeholder critical paths |
| E02 | Independent positive and numeric oracle | Independent fixed expected outputs + held-out cases |
| E03 | Adversarial false claim / refusal | All critical negative examples blocked |
| E04 | Frozen schema, APIs and compatibility | Schema validation + contract fingerprints |
| E05 | Actual read-only authorization + provenance | Denial tests, audit + source lineage |
| E06 | LLM optional + prompt injection boundary | Mock invalid model output, deterministic fallback |
| E07 | Engineer UX and accessibility | Keyboard file selection, errors, chart/table alternatives, recovery; named table captions and scoped headers; concise status announcements; target screen-reader and engineer review |
| E08 | No-network platform install/runtime | Fresh matched OS/arch install with network isolation |
| E09 | Supply-chain/license/security scan | SBOM, license approvals, time-stamped CVE DB |
| E10 | Archive reproducibility, rollback, stop | Hashes, rerun unpack tests, kill switch |
| E11 | Performance, resource and user work | Pre-set baseline comparisons, p95 and user effort |
| E12 | Minimal authorized internal adaptation | Qualify-internal real MCP checklist + guided first result |

## Precommit benchmark method
- Record target OS/architecture CPU/memory, Python/JS/runtime versions, analysis task sizes, expected task mix, correctness oracle, baseline method and threshold BEFORE final holdout scoring.
- Benchmark representative small/medium/13,000-schema source discovery and dense golden event/measurement cases; do not allocate 13,000 fully populated relational tables unless benchmark calls for it.
- Measure source-selection recall and false joins, scientific validity, false positives/abstentions, p50/p95 latency, peak memory, model calls/tokens, full user-review duration and dependency/install cost.
- Noncompensatory safety/false-causal/false-join cases require zero escape in defined critical suite. No percentile score compensates for an invented manufacturing fact.
- A baseline may legitimately outperform a sophisticated model; remove components without justified incremental gain.
- Record failures and retry evidence. A unit test that merely asserts an output exists is not an independent scientific oracle.

## Evidence policy
Every external gate must map to actual test command and artifact path. The supplied `bootstrap_check.py` validates only starter file integrity and a few sanity tests. `EXTERNAL_TRANSFER_READY` is forbidden until code, offline target installation, security/license review, full user path and complete independent science tests exist. Internal readiness is separate and can never be certified using synthetic cases.
