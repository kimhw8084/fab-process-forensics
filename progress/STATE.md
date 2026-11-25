# Persistent Codex work ledger — P2

State: `CANDIDATE`; external transfer and internal qualification are not claimed. Internal-only dependencies are `PENDING_INTERNAL`, not blockers to unrelated external engineering.

## Completed external work

- Implemented deterministic B01 wafer histories, B02 exact chamber/tool exposure, B03 route/rework variants and conformance, and B05 support/counterevidence with explicit uncertainty and causal limits.
- Preserved operation definitions versus actual step instances, repeated processing, effective-dated relationships, rework, route-version changes, split/merge membership, duplicate handling, clock uncertainty, and provenance on material links.
- Hardened B01 journey-coverage claims: coverage now declares the sources it covers, its relationship must authorize coverage fields, and every covered process source must have the required observation fields and effectivity over the coverage window. Missing source coverage leaves journeys `INCOMPLETE`; it does not upgrade the caller's assertion into live authorization.
- Hardened B01 time-scoped lot membership: an event's complete clock-uncertainty interval is compared with each material edge's half-open effectivity. A transfer boundary inside the interval remains `TEMPORALLY_AMBIGUOUS_MEMBERSHIP`, lists candidate lots, and reports possible versus definite edge timing with source provenance. Added a fixed-answer held-out case for uncertain and certain events around the same transfer.
- Hardened B01 cross-source wafer identity: an approved identity mapping must cover each event's full clock-uncertainty interval. If the interval crosses the mapping's effectivity boundary, the engine refuses the merge and emits no factual claims.
- Indexed per-entity material edges by effective time. On a synthetic 100,000-edge/100,000-query fixture, the index matched a separate schedule oracle exactly and reduced median grouping/build plus lookup time from 577 ms to 346 ms (1.67x); additional traced setup allocation was 30.7 MB. This is a bounded host benchmark, not fab performance.
- Completed the B01 multi-hop gap found in the overnight audit: from verified event-lot or material-membership seeds, trace typed source-declared `SPLIT_FROM`/`MERGED_FROM` lot edges under each event's full time interval. Direction, edge provenance, possible timing, and missing seeds are visible; sibling traversal through `LOT_MEMBERSHIP` is excluded. An undeclared event `lot_id` is now labeled unverified and cannot attach unrelated material edges. Added two fixed-answer cases and extended the headless journey panel with a lineage path table.
- Follow-on B01 hardening now limits absent-edge statements to the submitted graph: output labels a missing connection as `NO_CONNECTED_SPLIT_MERGE_EDGE_OBSERVED`. A generic `material_relationship_coverage` input can qualify a caller-declared complete snapshot only when the effective relation covers typed entities, edge types, sources, missing-record list and full event uncertainty. It remains unauthenticated; invalid omissions stay unknown. Exact duplicate source instances collapse with an explicit count; conflicting same-grain records refuse without an evidence artifact.
- B02 effectivity-boundary uncertainty leaves exact exposure and nonmatch classification `UNKNOWN`; B03 route population output separates caller-declared, event-bearing, ordered, uncertain, no-row and out-of-coverage denominators. B05 alternative equipment patterns use only source-declared fields effective over full time uncertainty and remain descriptive, not causal.
- Added a direct synthetic browser observation record at `qualification/evidence/browser-process-forensics-current.json`: three W1 step instances, two route variants, explicit denominators, exact chamber populations, counterevidence and a source-linked alternate equipment pattern are displayed in the local investigation flow. No company endpoint was contacted.
- Added a real SDK mock-to-engine workflow that records discovery, semantics, relationship retrieval, bounded read, deterministic analysis and audit provenance in one synthetic evidence envelope.
- Added the versioned headless React P2 contribution with five engineer panels, accessible chronological fallback, typed evidence/source models, host lifecycle adapters, and shared contribution metadata. P1 remains owner of the canonical suite shell.
- Implemented a configurable read-only MCP client on the official Python SDK 2.3.0 for the six frozen logical operations. Synthetic mock tests exercise stdio and Streamable HTTP, denied permissions, response limits, time/grain/provenance, cancellation, audit, and recovery.
- Staged the Golden Agentic Engineering source at `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` and adapted relevant practices into four valid Codex skills. Golden is not Samsung-qualified and is not a substitute for literal R01–R53.
- Historical full suite after P2-33: 131 tests passed with zero skips using the pinned MCP SDK 2.3.0; the base Python environment also passed all 131 tests with 12 optional-SDK skips. All synthetic; not blinded or company-qualified.
- The separate adversarial module uses its own fixed fixtures and expected answers, but is not blinded; the science gate remains partial pending independent reviewer and manufacturing-data qualification.
- Compared typed time-aware adjacency with NetworkX 3.1 on 100,000 synthetic typed edges and 250 queries. The 25 held-out result sets matched; the P2 traversal used less build time, traced memory, and query time in this workload. NetworkX is not a runtime dependency.
- Revalidated the local UI state smoke, including complete JSON envelope serialization, deterministic filename, visible download-start status, and deferred blob cleanup.
- Fixed two local accessibility gaps: the file input now has a visible keyboard-operable button, and provenance tables have captions with scoped column headers; the large review table no longer doubles as a verbose live region. A fresh browser flow exercised keyboard chooser activation, snapshot review, analysis, and JSON download; evidence is synthetic and does not include manual screen-reader acceptance.
- The local UI state smoke now checks file-control activation and concise review announcements; source-contract checks preserve the named region and table semantics.
- Current local browser replay now verifies caller-declared source-linked coverage, exact-chamber classification, route and counterevidence panels, and a captured exported JSON envelope at `qualification/evidence/browser-workflow-current.json` and `qualification/evidence/browser-current-export.json`. The prior browser workflow remains historical.
- Latest 100-to-100,000-event analysis scaling run passes its direct oracle at all five sizes; at 100,000 events p95 is 2,380.8 ms, peak traced allocations 427,930,494 bytes, and compact JSON is 24,259,581 bytes. This is synthetic host evidence, not a fab performance claim.
- Release artifacts include the pinned offline MCP wheelhouse, SPDX inventory, CycloneDX dependency report, source manifest, deterministic ZIP builder, checksum sidecar, offline verifier, and receipt generator. Regenerate and reverify these artifacts after source changes; do not infer readiness from prior archive evidence.
- Refreshed the current candidate after B01 material coverage and P2-32: two builds matched the checksum in `release/BUNDLE_SHA256SUMS.txt`. Fresh archive extraction, source integrity (205 files), hash-checked offline MCP installation, 130-test suite, demo and rollback passed on macOS arm64 CPython 3.11.7. This is current-host reproducibility only; E08/E09 remain partial.
- P2-33 fixed source relationship effectivity for actual processing time uncertainty; the prior archive is stale and needs a refreshed current-host qualification before transfer.
- P2-34: declared missing exposure/route coverage records now prevent nonmatch comparator promotion and route conformance; the approved coverage relationship must authorize a unique explicit `missing_record_ids` field.
- P2-35/P2-36: expected route definitions now require a source-linked relationship authorizing the approval marker, route identity/version and sequence fields; route relationship effectivity must contain the event's full clock-uncertainty interval. Route segments expose source, relationship and effective bounds. A caller `approved: true` without the relationship refuses; coverage that omits the route source remains incomplete.
- P2-37: outcome timestamps now require an explicit source-relationship `timestamp` key before time-stratified counterevidence can use them. A held-out test reproduced the previous `VALID` result with an undeclared time field; the same input now refuses.
- P2-38: an independent product/time counterexample preserves normal-exposed and abnormal-unexposed members, a missing outcome denominator, source-authorized product/time strata, and a server-confirmed next verification. Product IDs omitted from relationship keys remain absent from output strata; no association or cause is asserted.
- P2-39 closed the B01 process-time provenance gap: chronology now requires the wafer-step relationship to authorize the event `timestamp`; the held-out case reproduced the previous false `VALID` output. Two older fixtures omitted timestamp authorization and were updated to model valid relationships, preserving the stricter rule.
- P2-40 closed an MCP response-envelope gap: each returned typed row must be represented in response source/relationship references, and every selected plan time field must be relationship-authorized. Three mutated peer variants independently failed before analysis.
- Extended transport qualification with a real Streamable HTTP peer challenge for server-side permission denial, row-limit enforcement, confirmed cancellation, successful retry, and matching recovered-read audit query hashes. HTTP peer test: `test_streamable_http_denial_bounds_cancellation_and_recovery`.
- Added P1-compatible `buildP2PanelModels` as a pure five-panel model so the React shell can render with P1-owned table/graph components; local DOM panels remain the standalone fallback. `qualification/ui_state_smoke.js` verifies exact evidence object pass-through without inventing relationships. The P1 checkout is absent from the parent workspace, so `ui/P1_HOST_INTEGRATION_PROPOSAL.md` records concrete host wiring using only the frozen manifest.
- MCP-01…MCP-05 added independent protocol counterexamples. Duplicate relationship IDs, keys missing from all verified source definitions, and duplicate semantic source IDs were each accepted before the adapter fix; they now refuse before a bounded read. The MCP client checks response uniqueness and verified source-declared join-key membership.
- Added a sixth independently bounded MCP role for process-history coverage. The complete synthetic workflow now links each of four wafer histories to the exact declared coverage record, source, relationship, and time scope while keeping that assertion unauthenticated. Cancellation returns no partial evidence after the first audited read; recovery completes all six role reads.
- Current full suite after the six-source investigation and release fixes: **148 tests discovered/executed/passed, zero skips** with pinned MCP SDK 2.3.0; core mode **148 discovered, 129 executed/passed, 19 SDK-only protocol skips**, and zero failures/errors. Scientific summary reports P2-01…P2-43 and **37 separate fixed-answer cases**, plus seeded 100-case exact-chamber, exact-tool, and time-window oracles. All are synthetic, visible during development, and not company-qualified or blinded.
- The current candidate passes two deterministic builds and clean extraction with source integrity, hash-pinned no-index MCP installation, all 148 SDK tests, six-source MCP-to-evidence workflow, offline React install/mount tests, demo, and rollback. Exact counts are reconciled in `qualification/evidence/test-run-reconciliation.json`; release remains `CANDIDATE`, and only macOS arm64/CPython 3.11 with host-cached npm packages is covered.
- Scanned all 28 pinned optional MCP dependencies with pip-audit 2.10.1 against OSV using the exact lock without environment resolution. No known vulnerabilities were returned. Company ownership, transfer rights, and OSS approval remain pending.

## Current evidence

- `qualification/evidence/test-suite.log`
- `qualification/evidence/science-oracle-summary.json`
- `tests/test_heldout_adversarial.py`
- `qualification/evidence/browser-workflow-current.json`
- `qualification/evidence/browser-current-export.json`
- `qualification/evidence/browser-accessibility-current.json`
- `qualification/evidence/browser-accessibility-export.json`
- `qualification/evidence/browser-workflow-2026-11-22.json` (historical, superseded)
- `qualification/evidence/browser-ui-smoke.json`
- `qualification/evidence/browser-keyboard-export.json`
- `qualification/evidence/ui-state-smoke.json`
- `qualification/evidence/browser-process-forensics-current.json`
- `qualification/evidence/mcp-end-to-end-workflow.json`
- `qualification/evidence/graph-library-benchmark.json`
- `qualification/evidence/mcp-dependency-vulnerability-scan.json`
- `qualification/evidence/security-tool-availability.json`
- `qualification/evidence/bundle-verification.log`
- `qualification/evidence/test-run-reconciliation.json`
- `integration/artifacts/P2_REACT_HOST_HANDOFF_VERIFICATION.json`
- `release/GATE_REPORT.json`
- `release/RELEASE_RECEIPT.json`

## Remaining qualification gates

- Live authorized Fab Insight discovery, real source semantics/permissions, and first company result: `PENDING_INTERNAL`.
- Literal Samsung R01–R53 text: `NOT_VERIFIED`; no invented requirement mappings.
- Company target OS/runtime, site network controls, approved model host, company engineer/accessibility review, and P1 shell integration remain unverified.
- A blinded/independent manufacturing engineering holdout and user task-time study remain unverified; the separate 37-case fixed-answer suite is synthetic and not blinded. Synthetic oracle results are not company validation or ROI.
- Caller-declared material-edge coverage cannot authenticate completeness against a live source. Company-specific source semantics and an independent manufacturing holdout remain pending.
- Project ownership/transfer rights and company OSS approval remain `PENDING_INTERNAL`, despite the current optional-dependency vulnerability scan and license inventory.
- P1 shell integration, screen-reader/accessibility acceptance, and target-host engineer usability remain unverified despite the current synthetic browser replay.
- The NetworkX fixture measures relationship-neighborhood traversal only; representative fab-scale history reconstruction and a fully faithful OCEL2 test corpus remain out of scope until authorized semantics are available.
- The designated company deployment target is unknown. Only macOS arm64 CPython 3.11 optional-MCP offline install is qualified.
- No Git repository exists in the supplied folder, so no evaluated commit is recorded.

Never promote this build beyond `CANDIDATE` while any required external gate remains partial or unverified. Actual company qualification remains separate.
# Current continuation checkpoint — 2026-11-23

The entries below this heading include historical checkpoints and are superseded where counts or coverage labels differ.

- Current pinned SDK test suite: **162/162 passed, zero skips**. Core run: **162 discovered, 138 executed/passed, 24 optional SDK-only tests skipped**, zero failures/errors. The 24 are MCP transport/permission/provenance/cancel/recovery cases plus the six-source reference-host API workflow; none are counted as passes in core mode. Full IDs are in `qualification/evidence/test-run-reconciliation.json`.
- Current React module tests: **7/7** on React 18.3.1 and **7/7** on React 19.3.1; React 18 declarations type-check. The current handoff extraction passes offline npm install, all seven module tests, and six-source evidence validation.
- Scientific summary: `PASS_LOCAL_SYNTHETIC_ORACLES`. Coverage remains strictly `ASSERTED_UNVERIFIED` for the fixture; exposure cannot claim verified unexposed population, route coverage is incomplete, and causality is not established.
- Standalone browser evidence covers the real synthetic MCP-to-panel workflow and export. Shared-suite integration, actual source permissions/semantics, authenticated coverage grants, target OS, independent manufacturing holdout, and transfer rights remain separate pending qualifications.
- Latest candidate status: two deterministic archive builds match and the exact candidate passes clean extraction under the pinned macOS arm64 CPython 3.11 MCP environment. The run includes source integrity, the full 162-test protocol suite, six-source evidence generation, offline React install/tests/typecheck/build, demo and rollback. Exact checksum and receipt are in `release/BUNDLE_SHA256SUMS.txt` and `release/RELEASE_RECEIPT.json`; full output is `qualification/evidence/bundle-verification.log`.
- Next executable qualification requires external inputs: designated target OS/runtime/network policy; actual combined shared-suite host; an authorized and independently reviewed manufacturing holdout; and source ownership/transfer approval. Current local engineering is complete against synthetic external contracts, without claiming any of those pending statuses.

## Separate engineering revision — 2026-11-23

- The frozen candidate and its source manifest remain unchanged at their recorded hashes. Current development is in `/Users/haewonkim/home/work/product 2/P2_ENGINEERING_PHASE_2026-11-23`; no release archive was rebuilt.
- B01 chronology now surfaces a process-row lot ID that conflicts with effective-dated membership, including the exact membership record. B05 proposes an authorization-gated, not-executed bounded read with exact process-step and membership-record refs and separately filtered declared keys for each source relationship.
- Independent checks on the working revision: SDK Python suite 167/167 passed; held-out adversarial module 38/38 passed; React suite 14/14 passed; local UI state smoke passed. A fresh loopback browser workflow showed the conflict, the next-check row and drilldown to `H-STEP-2` / `H-MEM-B`. Partial exposure coverage kept the comparison wafer `UNKNOWN`; causality stayed `NOT_ESTABLISHED`.
- The next executable action is recorded in `progress/NEXT_ACTIONS_ENGINEERING.json`: replay the complex 100-wafer case on the working revision, search to a conflicted wafer, and verify proposal/provenance discoverability. Release/transfer and company qualification states are not changed by these synthetic checks.

