# P2 overnight execution log

Started: 2026-11-22 (America/Chicago)  
Release state: `CANDIDATE`; internal requirements remain `PENDING_INTERNAL` or `NOT_VERIFIED`.

## Audit finding and current loop

Audit sources: `GOAL.md`, `docs/PRODUCT_SPEC.md`, `docs/SCIENCE_AND_METHODS.md`, `docs/TEST_AND_RELEASE_MATRIX.md`, `contracts/SHARED_ARCHITECTURE.md`, `requirements/AUTHORITY_AND_GAPS.md`, `requirements/EXTERNAL_GAP_LEDGER.md`, the P2 engine, and current fixed-answer/seeded test modules.

Highest-impact external gap selected: **B01 multi-hop lot lineage was not reconstructed.** `_route_analysis` indexed material relationships by endpoint and included only relationships incident to the event wafer or event lot. It could show a direct split/merge edge, but an engineer starting at lot C could not inspect a source-declared chain A → B → C unless every edge was directly incident to the event's lot. Existing fixtures covered a single direct split/merge but not a multi-hop lineage or sibling-wafer isolation.

Acceptance for the completed B01 loop:

1. Implement traversal over source-declared `SPLIT_FROM`/`MERGED_FROM` lot-to-lot edges at the event's full UTC uncertainty interval.
2. Preserve edge direction and source/relationship provenance. Do not traverse `LOT_MEMBERSHIP` into sibling wafers.
3. Return deterministic shortest paths and explicit possible states for uncertain edge/seed intervals.
4. Fixed-answer challenge now covers a two-hop chain, an expired edge, a possibly effective edge, an unsupported relationship type, a sibling-wafer path, and an undeclared `lot_id` that must not attach an unrelated material graph. Both focused B01 tests and the headless UI smoke pass; full suite and package qualification are in progress.

## Executed this session

- Started the requested B01/B02/B03/B05 product-spec audit using local specs, contracts, authority ledger, engine, and tests.
- Confirmed no P1 shell or component worktree is available inside this P2 folder; headless integration remains the current boundary. No company endpoints or credentials were accessed.
- Previous continuation added clock-uncertainty checks for time-scoped membership and cross-source identity, an interval index, and current offline package verification; see `progress/STATE.md` and `release/GATE_REPORT.json`.

## Completed loop: B01 multi-hop lot lineage

- Files: `products/p2/engine.py`, `ui/p2-panels.js`, `qualification/ui_state_smoke.js`, `tests/test_heldout_adversarial.py`, `docs/INPUT_SNAPSHOT_CONTRACT.md`, `docs/SCIENCE_AND_METHODS.md`, `docs/TEST_AND_RELEASE_MATRIX.md`, and gate/evidence ledgers.
- Behavior: source-declared `SPLIT_FROM` and `MERGED_FROM` lot-to-lot edges are traced only when temporally possible for an event. Output keeps direction, provenance, definite/possible timing, seed basis, missing evidence, and deterministic shortest paths. `LOT_MEMBERSHIP` never propagates to a sibling wafer. An undeclared event `lot_id` cannot connect the process row to unrelated material edges.
- Targeted commands: `rtk python -m unittest tests.test_heldout_adversarial.HeldoutAdversarialTests.test_multihop_lot_lineage_keeps_direction_time_and_sibling_boundary -v` and `...test_undeclared_event_lot_field_cannot_attach_unrelated_material_graph -v` → PASS.
- Headless journey panel now shows lineage paths and relationship IDs; `rtk sandbox-exec -f qualification/no_external_network.sb node qualification/ui_state_smoke.js` → PASS.
- Next executable action: run the full suite, refresh release evidence/package, then advance to B02 adversarial audit.

## Append each loop

For each completed loop, record the chosen requirement, changed files, command and result, evidence path, and the next executable action. Do not change company-only gates from `PENDING_INTERNAL`/`NOT_VERIFIED` without authorized evidence.

## Continuation loops — 2026-11-23

### B01/B02 effectivity uncertainty, B03 denominator, and B05 equipment alternatives

- **Chosen gaps:** event lot joins and exact exposure classification could accept a nominal timestamp even where clock uncertainty crossed source-relationship effective boundaries; route shares lacked an explicit population/observed denominator; hypothesis equipment context read raw chamber/tool fields even where a source relation did not declare them.
- **Changes:** full uncertainty interval now gates event-lot lineage seeds and exact/nonmatch exposure classification; uncertain effectivity gives `POSSIBLE` lineage or `UNKNOWN` exposure. Route evidence separates declared, event-bearing, ordered, chronology-uncertain, no-row, and out-of-coverage groups. Alternative equipment patterns now require field-level source keys, full effectivity, definite time overlap, and field-specific coverage before nonmatch classification; verified patterns stay descriptive and noncausal. P2 panels and headless smoke now expose these outputs.
- **Independent checks:** fixed-answer P2-26…P2-29 in `tests/test_heldout_adversarial.py`; `rtk sandbox-exec -f qualification/no_external_network.sb node qualification/ui_state_smoke.js` → PASS.
- **Evidence:** `qualification/evidence/ui-state-smoke.json`, `qualification/evidence/science-oracle-summary.json`, P2-26…P2-29 in the test log.

### Synthetic mock MCP to evidence envelope

- **Chosen gap:** protocol tests stopped at bounded retrieval and did not prove the configured MCP response could pass into the actual deterministic investigation and evidence envelope.
- **Changes:** `fabintel/mcp_workflow.py` runs discover → semantics → relationships → read_bounded → audit; validated synthetic rows feed the analyzer and an MCP provenance block records operation, protocol, source/relationship IDs, bounds, truncation state, and matching read/audit hashes. It keeps `SYNTHETIC_DEMO`, labels mock permissions unauthenticated for company use, and maps truncated rows to partial evidence.
- **Independent checks:** added `test_mock_peer_read_runs_journey_exposure_and_evidence_pipeline`; pinned MCP adapter suite and full suite pass. Refusal, server-denial, bounds, incorrect grain/time/provenance, cancellation and retry/recovery cases remain in `tests/test_mcp_adapter.py`.
- **Evidence:** `qualification/evidence/mcp-end-to-end-workflow.json` records the current protocol v2026-07-28 mock call sequence and no company authorization.

### Browser workflow refresh

- **Chosen gap:** the shared module had headless rendering checks but needed a real local browser interaction against the updated result panels.
- **Changes/evidence:** visible IAB session loaded the synthetic example, ran preflight, and ran analysis. Result panels displayed three W1 step instances with repeated ETCH, two ordered route variants and separate denominators, exact C1 exposed W1 vs covered C2 W2, normal-exposed/abnormal-not-observed counterevidence, and the source-linked C2 alternative pattern. Captured current observation in `qualification/evidence/browser-process-forensics-current.json`; screenshot was inspected in the browser workflow.
- **Limits:** synthetic local-only; no Samsung/Fab Insight service, P1 shell, target screen reader, or engineering acceptance was implied.

### B01 duplicates and negative lineage coverage

- **Chosen gaps:** duplicate records needed a separate fixed-answer challenge, and an empty material-edge snapshot could be misread as proof no split/merge existed.
- **Changes:** identical copies retain one step with an explicit duplicate count; conflicting same-source step-instance rows refuse the investigation. Lineage output now states `material_relationship_coverage=NOT_ESTABLISHED`; disconnected-edge status means only that no connected split/merge path was observed in the supplied snapshot.
- **Independent checks:** P2-30 and P2-31 in `tests/test_heldout_adversarial.py` verify exact duplicate collapse, conflicting record refusal/no artifact, and absent-edge completeness uncertainty. Both focused tests passed; `qualification/summarize_scientific_evidence.py` reports 31 fixed P2 cases and 26 separate fixed-answer cases PASS.

### B01 source-linked material completeness contract

- **Chosen gap:** B01 needs a way to distinguish a verified observed path from a complete material-edge snapshot before it can interpret missing edges. The local input had no material completeness record, so absence could only remain unknown.
- **Changes:** added optional `material_relationship_coverage` with typed covered entities, relationship types, covered material source IDs, effective coverage relationship, UTC interval and explicit missing-record list. The engine requires the coverage relationship to authorize those fields and effective bounds, the full event uncertainty to fit, source relationships for each declared edge type over the coverage interval, and the scope to include the lineage seed and observed endpoints. Membership coverage is required when membership edges establish the seed. Accepted state remains `CALLER_DECLARED_SOURCE_LINKED_COMPLETE`, explicitly unauthenticated; omission, invalid scope, missing records, type/source mismatch and time-bound failure remain incomplete/unknown.
- **Independent check:** P2-32 uses one positive synthetic coverage record and six invalid variants (omitted entity, type, source, clock window, missing record, and unauthorized field). Targeted pinned-SDK test → PASS.
- **Evidence:** `tests/test_heldout_adversarial.py`, `docs/INPUT_SNAPSHOT_CONTRACT.md`, P2-32 in `qualification/critical_cases.json`; full suite and package evidence refresh in progress.

### B02 actual-processing effectivity boundary

- **Chosen gap:** the exposure engine used actual uncertain processing intervals to decide overlap but checked the event source relationship's effective interval only against the point event timestamp uncertainty. A process whose timestamp was valid while its possible start crossed relationship effectivity could incorrectly become exact exposure.
- **Red test:** P2-33 initially failed: an interval crossing before relationship effective start was classified `EXPOSED` alongside the fully covered interval.
- **Change:** source relationship effectivity now must contain the full event timestamp uncertainty and, when actual bounds are present, the entire independently uncertain processing interval. Boundary-crossing records become `UNKNOWN`; evidence returns both intervals and the relationship bounds.
- **Independent result:** targeted P2-33 passes: fully covered interval remains exact, boundary-crossing interval is unknown, no potentially-exposed or nonmatch promotion. Full suite, headless smoke and package refresh follow.

### Historical full suite after P2-38

- After P2-32, the preceding candidate passed 130 tests and fresh offline package verification; see the prior lines and current `release/RELEASE_RECEIPT.json` for its checksums. That archive is superseded by P2-33.
- After P2-33, `rtk proxy /tmp/p2-offline-mcp-qualified/bin/python -m unittest discover -s tests -v` → **131 tests, PASS, zero skips**; `rtk python -m unittest discover -s tests -v` → **131 tests, PASS, 12 optional-SDK skips**.
- Refreshed local demo, headless UI smoke, scientific summary, and mock MCP end-to-end evidence. The summary reports P2-01…P2-33 and 28 separate fixed-answer cases PASS.
- **Package refresh:** required after P2-33; do not use the previous archive as current verification.
- **Historical:** the above suite and archive evidence are superseded by P2-34 through P2-36 below.

### B02 coverage missing-record refusal — P2-34

- **Audit finding:** `_coverage` accepted `complete: true` while ignoring a nonempty `missing_record_ids` list. That could promote a nonmatching population member to `NOT_OBSERVED_EXPOSED` and an unaffected comparator, and could enable route conformance despite a missing process row.
- **Red test:** the separate fixed-answer P2-34 case first failed because the listed missing row did not put the wafer in `UNKNOWN`.
- **Change:** exposure and route coverage now require a unique explicit missing-record list, authorize it through the named coverage relationship, reject nonempty lists for complete coverage, retain the IDs in evidence, and surface them in route population summaries.
- **Independent result:** P2-34 verifies unknown exposure, no comparator promotion, and `COVERAGE_INCOMPLETE` for route conformance. Full suites pass after subsequent B03 changes.

### B03 expected-route relationship and effectivity — P2-35/P2-36

- **Audit finding:** `expected_routes[]` accepted a caller `approved: true` plus a known source ID without any relationship authorizing the approval field or the expected operation sequence. It also compared definitions without checking definition-relationship effectivity against event clock uncertainty.
- **Red test:** P2-35 first failed because the engine returned `VALID` with route conformance from an unlinked expected-route declaration.
- **Change:** each route definition must reference an approved effective-dated relationship whose source and keys authorize approval, route ID/version, ordered operations, and any allowed sequence exceptions. Route coverage must include the definition source. Each segment reports route source, relationship and effective bounds. If event uncertainty crosses the definition relationship boundary, status is `ROUTE_DEFINITION_EFFECTIVITY_UNCERTAIN`, the overall result is partial, and neither match nor mismatch is asserted.
- **Independent checks:** P2-35 verifies refusal without a definition relationship and incomplete coverage when the route source is omitted. P2-36 verifies full-interval effectivity and provenance on the uncertain segment.
- **Evidence:** `tests/test_heldout_adversarial.py`, P2-35/P2-36 in `qualification/critical_cases.json`, `docs/INPUT_SNAPSHOT_CONTRACT.md`, `docs/SCIENCE_AND_METHODS.md`.

### Historical full suite after P2-36

- Pinned MCP SDK environment: `rtk proxy /tmp/p2-offline-mcp-qualified/bin/python -m unittest discover -s tests -v` → **134 tests, PASS, zero skips**.
- Core environment: `rtk proxy python -m unittest discover -s tests -v` → **134 tests, PASS, 12 optional-SDK skips**.
- Scientific summary: P2-01…P2-36, **31** separate fixed-answer cases, and the preserved 100-case chamber/tool/window seeded oracles → `PASS_LOCAL_SYNTHETIC_ORACLES`.
- Refreshed demo, headless UI smoke, and mock MCP end-to-end evidence. Release remains `CANDIDATE`; current manifest/SBOM/archive verification is still pending after these changes.
- **Historical:** P2-37/P2-38 below supersede the test and evidence counts.

### B05 outcome-time provenance and confounder challenge — P2-37/P2-38

- **Audit finding:** outcome timestamps entered time strata even when the approved outcome relationship did not declare `timestamp`; product mix and selection denominator behavior also lacked a separate held-out multistratum challenge.
- **Red test:** P2-37 reproduced a `VALID` counterevidence result while the relationship authorized only `wafer_id`, not the timestamp used for time analysis.
- **Change:** outcome provenance now requires the relationship to authorize `timestamp`; product IDs continue to enter product-mix strata only when `product_id` is also declared. The held-out P2-38 case uses normal/abnormal members in exact-exposure and observed-nonmatch groups across two products and outcome days, plus an event-bearing member with no outcome.
- **Independent checks:** P2-37 refuses the undeclared timestamp. P2-38 retains the population/outcome denominator and missing wafer, shows only source-authorized product/time strata, returns a server-confirmed `read_bounded` next verification, and asserts no statistical association or causal conclusion. A second variant omits the product key and gets no product IDs in output.
- **Evidence:** `tests/test_heldout_adversarial.py`, P2-37/P2-38 in `qualification/critical_cases.json`, `docs/INPUT_SNAPSHOT_CONTRACT.md`.

### Current full suite and next action

- Pinned MCP SDK environment: `rtk proxy /tmp/p2-offline-mcp-qualified/bin/python -m unittest discover -s tests -v` → **136 tests, PASS, zero skips**.
- Core environment: `rtk proxy python -m unittest discover -s tests -v` → **136 tests, PASS, 12 optional-SDK skips**.
- Scientific summary: P2-01…P2-38, **33** separate fixed-answer cases, and preserved 100-case chamber/tool/window seeded oracles → `PASS_LOCAL_SYNTHETIC_ORACLES`.
- Refreshed demo, headless UI smoke, mock MCP workflow and evidence summary after P2-38. The current package is stale; release stays `CANDIDATE`.
- **Historical next action:** inspect and challenge the MCP adapter's logical source mappings, relationship semantics, server denial, bounds, cancellation, audit mismatch, and retry/recovery across both supported transports. This was completed below; package refresh is now the current action.

### B01 process-time and MCP response provenance — P2-39/P2-40

- **Audit finding:** the journey engine used a process timestamp to establish chronology without requiring the process relationship to authorize that key. The MCP adapter also accepted typed-row source/relationship references omitted from the response-level provenance lists, and did not require each approved relationship to authorize the read plan's selected time field.
- **Independent red tests:** P2-39 reproduced a `VALID` chronology from an undeclared process timestamp. Three P2-40 synthetic-peer mutations omitted source references, omitted relationship references, or removed the relationship timestamp key; each previously passed the adapter boundary.
- **Change:** process-event relationships now require `wafer_id`, `step_instance_id`, and `timestamp`; MCP reads require time-key authorization and every row's source/relationship to appear in the response envelope as well as the approved plan. Older rework and operation-definition fixtures were corrected to declare their valid process timestamp key.
- **Independent result:** P2-39 refuses the undeclared time field; all P2-40 envelope/time mutations raise `MCPContractError`. A separate real Streamable HTTP peer test now verifies server-enforced permission denial and row limit, confirmed cancellation, clean retry, and matching audit hash after recovery.
- **Full verification:** pinned MCP SDK suite **139/139, zero skips**; core suite **139 total, 14 optional-SDK skips**; scientific summary `PASS_LOCAL_SYNTHETIC_ORACLES` with 40 fixed P2 cases, 34 separate fixed-answer cases, and preserved seeded exposure oracles. Demo, headless UI smoke, and MCP-to-analysis evidence were regenerated.
- **Next executable action:** refresh the offline product package from the exact current tree, build twice and compare hashes, then perform fresh extraction, hash-checked offline installation, complete suite, demo, rollback, and release receipt verification. Preserve `CANDIDATE`; internal permissions, sources, and R01–R53 remain pending/not verified.

### P1 React view-model boundary and MCP definition ambiguity — MCP-01…MCP-05

- **P1 availability:** the parent workspace contains only the P2 launchkit; no P1 React host checkout or host component API is available. No company application was queried.
- **P1 contribution:** added pure `buildP2PanelModels` output for `summary`, `journey`, `exposure`, `counterevidence`, and `evidence`, allowing the canonical P1 host to render with its own table/graph components. Added the manifest-derived `ui/P1_HOST_INTEGRATION_PROPOSAL.md`; existing P2 DOM panel and local browser workflow remain intact.
- **Independent UI check:** the no-network UI smoke verifies that journey, exposure, counterevidence, investigation scope, input hash, and model limitations pass through from the exact evidence envelope; the manifest contract test verifies the proposal's product, route, entrypoint, and mode.
- **MCP audit finding:** semantic-source records could duplicate an ID and overwrite one another; relationship records could duplicate an ID; and approved join keys were not checked against verified source column definitions. Synthetic peer variants reproduced each acceptance before the fix.
- **Change and tests:** adapter now rejects duplicate semantics and relationship IDs, and requires approved relationship keys to exist in the verified semantics of at least one relationship source. MCP-01…MCP-05 are documented in `docs/TEST_AND_RELEASE_MATRIX.md`; current checks also retain response provenance, time key, HTTP denial, bounds, cancellation, recovery, and audit hash.
- **Full verification:** pinned suite **142/142, zero skips**; core suite **142 total, 16 optional-SDK skips**; separate scientific summary `PASS_LOCAL_SYNTHETIC_ORACLES` with 40 fixed P2 cases, 34 fixed-answer cases, and seeded oracles. Demo, UI state smoke, and MCP-to-analysis evidence were refreshed.
- **Current-host package result:** two final same-source ZIP builds match in `release/BUNDLE_SHA256SUMS.txt`; fresh extraction, source integrity, hash-checked no-index MCP installation, the 142-test suite, demo, and rollback pass in `qualification/evidence/bundle-verification.log`. The current release receipt and gate report are generated with `CANDIDATE` state.
- **Next action:** integrate through the existing P1 host only when its checkout is available; the exact contribution proposal is `ui/P1_HOST_INTEGRATION_PROPOSAL.md`. Keep P1 host acceptance `PARTIAL`, blinded manufacturing review pending, real permissions/sources `PENDING_INTERNAL`, and canonical R01–R53 `NOT_VERIFIED`.

### Six-source investigation completion and handoff extraction — 2026-11-23

- **Highest-impact gap:** the successful MCP-to-panel investigation could reconstruct step instances and route/exposure outcomes but marked process-history coverage `COVERAGE_UNKNOWN`, leaving journey completeness unqualified.
- **Change:** added a separately bounded `history_coverage` role, verified against source `record_kind`, exact source/relationship semantics, time bounds, query hash, and audit. The synthetic mock reports a full caller-declared history scope for four wafers. Every journey retains the coverage record ID, source, relationship, and time window. Shared MCP operations and shared evidence schemas were not changed.
- **Independent challenge:** the six-source engineer workflow test requires all journeys to carry the exact history coverage provenance; it also checks repeated-instance rework, route mismatch, allowed alternate route, exposure/counterevidence, and no causal conclusion. The cancellation test cancels after the first audited source read, returns no partial evidence, then recovers across all six reads.
- **Results:** targeted MCP protocol suite 21/21 passed. Complete pinned suite 148/148 passed with zero skips; core suite discovered 148, ran and passed 129, skipped 19 SDK protocol cases, with zero failures/errors. Scientific summary remains `PASS_LOCAL_SYNTHETIC_ORACLES` (43 P2 cases, 37 separate fixed-answer cases and seeded 100-case oracles; not blinded).
- **Packaging defect found and repaired:** clean P1 handoff extraction showed that `npm ci --prefix ...` was resolving the package under the wrong name. Both handoff and product verifiers now run npm from the package root. Updated handoff clean extraction passed offline install, 6/6 mounted React tests, and six-role evidence check; the lockfile install reported zero vulnerabilities.
- **Boundaries:** the history completeness record is synthetic and caller-declared. It does not authenticate live-source completeness. Actual P1 shell integration remains unavailable; the local handoff is not transfer authorization. Final candidate source manifest, deterministic builds, fresh extraction, reconciliation, gate report, and receipt are the next executable release actions.

### Candidate extraction and release-gate repair — 2026-11-23

- **Pre-final current-host candidate:** two builds matched at SHA-256 `0cf62fc9aeacca28ae8a1eb3cbbdf55f4ea1751714f3b65d66dd1be956947e7b`. Clean extraction passed source integrity, hash-pinned no-index MCP installation, all 148 SDK-enabled tests, the six-source MCP-to-evidence workflow, offline React install/tests, demo, and virtual-environment rollback. The exact run is `qualification/evidence/bundle-verification.log`; the evidence-embedded final archive is rebuilt and independently verified as the last release gate.
- **Release integrity repair:** the first extraction caught source-manifest entries for generated `node_modules/.bin` links that the archive excludes. Source-manifest and SPDX enumeration now both omit `node_modules`; the local generated tree was removed, SPDX inventory reduced to 239 included source files, and extraction passed.
- **Gate repair:** corrected `release/update_gate_report.py` to use the actual current P1 proposal test name; E01 now reports `PARTIAL` with integration gaps explicit, E04 `PASS`, and E10 `PASS` for the observed host. Test reconciliation explicitly requires the full six-source extraction success marker and reports 148/148 SDK pass and 129/148 core execution with 19 skips separately.
- **Completion:** the source manifest, SPDX inventory, corrected gate report, reconciliation evidence, and progress records are embedded in the final candidate. Two identical builds and clean-extraction verification pass; the current bundle checksum is in `release/BUNDLE_SHA256SUMS.txt`, the gate report remains `CANDIDATE`, and the receipt records no external-transfer or internal-company qualification.

### Coverage authority boundary, React pagination, and final qualification refresh — 2026-11-23

- **Selected gap:** the six-source synthetic coverage fixture had structural completeness and time scope, but its caller assertion could be read as authenticated completeness. Negative exposure and route conclusions needed to remain conservative, including when relationship effectivity itself was ambiguous.
- **Changes:** coverage levels now distinguish `SOURCE_VERIFIED`, `ASSERTED_UNVERIFIED`, `PARTIAL`, `UNKNOWN`, and `CONTRADICTORY`. Caller fields cannot promote coverage; absence of events under caller assertion cannot establish a negative or comparator; ambiguous relationship coverage remains unknown; route conformance remains incomplete. The current six-source envelope is `PARTIAL`, with exposure coverage `ASSERTED_UNVERIFIED`, no verified-unexposed population, and incomplete route coverage. Large fallback React views page rows without dropping the complete typed/export evidence.
- **Independent challenge:** a held-out relationship-effectivity assertion checks that ambiguous exposure members never reappear in asserted nonmatches. A new reconciliation regression test found and fixed a real report bug: optional SDK skips include both MCP adapter and reference-host workflow tests, and full test IDs must be preserved. Unexpected non-SDK skips remain errors.
- **Results:** current pinned suite **162/162 passed, zero skips**; core **162 discovered, 138 passed/executed, 24 SDK-only skips, zero failures/errors**. Scientific summary is `PASS_LOCAL_SYNTHETIC_ORACLES`. React 18.3.1 and 19.3.1 hosts each pass **7/7**, including pagination; React 18 declarations type-check. Latest P2 React handoff fresh extraction passes offline npm install, 7/7 mounted tests, and six-role `PARTIAL` evidence validation (SHA-256 `9df253c2781b2d20b4cb501a4e7ba748760bd730d398d0fc67f3a0c2bd197caf`). Current npm audit reports zero findings across the locked tree; license metadata is present, but no transfer permission is inferred.
- **Boundaries:** actual shared-suite/P1 integration, company authorization and source semantics, authenticated completeness grants, target-OS testing, and transfer rights remain pending. The local browser run proves only the synthetic workflow. Current status labels are maintained separately in `release/GATE_REPORT.json`.
- **Next executable action:** regenerate the source manifest, SBOM and gate report from the updated evidence; make two deterministic candidate builds; fresh-extract the exact candidate and rerun offline installation, complete protocol suite, React host build/tests, demo, and rollback; then update the receipt and resumable action ledger.

### Current-source candidate and evidence reconciliation — 2026-11-23

- **Release result:** after the coverage boundary, React pagination, reconciliation regression, current npm audit, and final documentation updates, the candidate built twice with identical SHA-256 values. `release/verify_bundle.py`, invoked with the pinned `/tmp/fabintel-p2-sdk/bin/python` CPython 3.11 runtime, passed safe extraction, source integrity, hash-pinned offline MCP installation, all SDK protocol tests, the six-source MCP-to-evidence workflow, offline npm install, seven React tests, reference-host type-check and build, demo, and rollback. The latest exact checksum is in `release/BUNDLE_SHA256SUMS.txt`; receipt and full output are in `release/RELEASE_RECEIPT.json` and `qualification/evidence/bundle-verification.log`.
- **Reconciled qualification:** SDK mode discovered/executed/passed **162**, with zero skipped, failed, or errored. Core mode discovered **162**, executed/passed **138**, and explicitly skipped **24 SDK-dependent protocol/reference-host tests**; zero failures/errors. `qualification/reconcile_test_runs.py` now tests that both optional SDK modules are accounted by full IDs, rejects unexpected skips, and matches the exact release verifier marker before claiming fresh extraction.
- **Coverage boundary:** synthetic process/exposure completeness remains `ASSERTED_UNVERIFIED`; `verified_unexposed` is empty, unknown wafers are not comparators, route conformance is `COVERAGE_INCOMPLETE`, and no causal conclusion is established. The actual loopback browser was operated through the new six-source analysis, then a source relationship was opened for provenance inspection and evidence export was activated.
- **Supply-chain state:** npm audit reports zero findings in the locked React/Vite dependency graph, the pinned MCP SDK dependency scan reports zero known issues in its 28 locked packages, and the SPDX inventory contains 257 source files with ownership `NOASSERTION`. Target OS, project rights, company OSS approval, and internal qualification remain outside these local results.
- **Success states:** P2 implementation is complete for the external synthetic contracts; standalone local browser workflow is verified; the versioned shared React contribution is ready; actual shared-suite integration remains pending. External transfer remains not qualified, and internal company qualification remains pending.
- **Next action:** wait for the designated target environment, combined suite host, authorized independent manufacturing holdout, and documented source-transfer authority before those specific gates can run. Do not repeat local workspace checks absent new input.

### Independent engineering cycle — lot conflict and next verification — 2026-11-23

- **Deficiency:** the large synthetic browser case exposed a process-row lot value that disagreed with the effective-dated material membership. It was visible only in the row detail before the chronology correction, and the B05 next-check list lacked an exact material-conflict proposal.
- **Change:** primary chronology now displays event-row lot evidence alongside the time-scoped membership value and record ID. The B05 candidate builder adds a `LOT_MEMBERSHIP_CONFLICT` bounded-read proposal with affected wafer, exact process-step and membership-record references, separately filtered keys per relationship, an information bound, and explicit not-executed/server-authorization language.
- **Independent checks:** held-out case `test_lot_membership_conflict_proposes_pair_scoped_read_only_resolution`; held-out module 38/38; SDK Python suite 167/167; React 14/14; `qualification/ui_state_smoke.js` passed with separate key-list assertions. A fresh port-8801 browser run showed the 02:30 conflict, exact `H-STEP-2` and `H-MEM-B` under proposal provenance, comparison wafer `UNKNOWN` under partial coverage, and `NOT_ESTABLISHED` causality. A first malformed browser fixture was refused because `lot_id` was not present on every row under the declared relationship; the corrected source-linked fixture preflighted and ran.
- **Frozen baseline:** no candidate was rebuilt. The archived candidate remains SHA-256 `8cd4d26b58cec464e21bebc3a6c4704ea862ed496de5c729568f297970303f5d`; manifest file remains SHA-256 `dbfe462fa80ae9117a8541d9b6c75b7747c42d4683aee538d925babe8ccfcf88`.
- **Historical next action (closed this checkpoint):** replay the complex 100-wafer task on the working revision, filter to the conflict and verify the bounded proposal.

### P2 independent acceleration — 2026-11-23

P2 is an independent product. P1/P3/P4 availability or suite integration is not a prerequisite or completion gate; older integration entries in this file are historical. Existing interoperability artifacts are optional.

- `qualification/verify_complex_100_panel_flow.mjs` passes: filtering to `SYN-EW-010` leaves both conflicting process steps visible; `SYN-MEM-010-B` and the authorization-gated proposal remain inspectable. Relationship key sets stay separate; exact/potential/unknown exposure remains 24/25/51, verified-unexposed remains zero, coverage remains `CONTRADICTORY`, and causality remains `NOT_ESTABLISHED`. The JSON evidence export round-trip preserves the full envelope. Evidence: `qualification/evidence/complex-100-panel-flow.json`.
- Official-SDK mock MCP test denies without a read, then permits only after explicit synthetic authorization; two bounded reads retain pair-specific keys and audit correlation. Refreshed membership is ambiguous. Real browser operation of the smaller synthetic MCP scenario also returned ambiguity and displayed exact provenance.
- B05 ranking uses explicit evidence/coverage/population and bounded-request-count factors. Identical overlapping checks merge; different steps remain separate. No probability, actual latency, or causal score is claimed.
- Descriptor onboarding scanned 13,008 synthetic descriptors: 7/7 roles and 6/6 operations proposed, semantic decoy rejected, no false positives/reads, five review decisions. Human setup time remains unmeasured.
- Profile found the benchmark fixture builder, not the engine, repeatedly traversed the growing nested snapshot. A one-pass coverage update reduced profiled generation from 25.403 s to 1.101 s; fixed answers stayed identical. Current 100x analysis is 1.386 s, 386,088,960-byte peak RSS for the same 9,800 journeys / 40,400 rows / 23,187,869-byte payload. Evidence: `qualification/evidence/benchmark-engineering-phase-100x-before-generator-fix.json` and `qualification/evidence/benchmark-engineering-phase-100x.json`. Synthetic host only.
- Matched comparison safely extracted the pinned frozen archive and confirmed archive/manifest SHA-256. Protected science matched: 98 journeys, 403 steps, 24/25/51 exposure, zero verified-unexposed, contradictory coverage, and no causal conclusion. Current engine adds five bounded candidate checks, including the exact lot conflict; frozen baseline had none.
- Fresh regressions: Python 176/176 and React 14/14; zero skips. Logs and machine-readable evidence are recorded in `qualification/evidence/`.
- Frozen candidate and source-manifest checksums remain `8cd4d26b58cec464e21bebc3a6c4704ea862ed496de5c729568f297970303f5d` and `dbfe462fa80ae9117a8541d9b6c75b7747c42d4683aee538d925babe8ccfcf88`; no archive rebuild.
- Next: test a complex-history SDK MCP scenario only if it closes a concrete integration gap within current query/response/resource bounds. Otherwise continue only for a reproducible B01/B02/B03/B05 defect. Company access, target OS, manufacturing review, transfer rights, engineer task time and ROI remain pending.

### Bounded onboarding at 13k catalog scale and standalone browser closure — 2026-11-24

- **Measured deficiency:** live onboarding queried relationship metadata using 13,008 references even though only seven source descriptors had record kinds eligible for P2 roles. A matched official-SDK run measured metadata capture at 3.276 s, with 1.722 s in relationship lookup.
- **Implementation:** all 13,008 descriptors still receive semantics inspection, in fixed 64-source batches (204 batches). Relationship references are restricted to sources with one of the seven frozen P2 record kinds; this narrows query volume only and does not assign authority, authorize reads, or bypass engineer review. Added capture timings outside the digest-bound source capture so they do not alter approval hashes.
- **Measured result:** same synthetic catalog, SDK, and process class: relationship refs fell from 13,008 to 7; relationship phase from 1.722 s to 0.002 s; metadata capture from 3.276 s to 1.296 s (60.43% in one matched run). Seven roles remained uniquely review-required; 13,001 unclassified semantic decoys were not assigned roles. Detailed measurements and caveats: `qualification/evidence/onboarding-13k-mcp-performance-and-e2e-2026-11-24.json`.
- **End-to-end MCP qualification:** the official SDK test now performs catalog discovery, 204 bounded semantics calls, relationship capture, exact digest-bound synthetic review, seven bounded role reads, and complete B01/B02/B03/B05 analysis. It verifies 98 journeys, 404 process rows, route variants, 24/25/49 exposure populations, zero verified-unexposed, contradictory coverage, unverified caller maintenance context, an unexecuted exact lot-conflict check, matching read/audit hashes, and no causal conclusion.
- **Standalone host:** added the same 13k aliased catalog environment to the existing P2 reference runner. A real browser loaded 45 abnormal options and 98 observed cohort members, ran the seven-source workflow, searched to `SYN-EW-010`, showed repeated ETCH instances and exact `SYN-MEM-010-A/B` effective-dated records, and displayed the 24/25/49 exposure split, unknown coverage, route variants and counterevidence. Denial showed no MCP read. Explicit synthetic authorization ran the two exact bounded follow-up roles; refresh showed `SYN-MEM-010-A/B/C` and retained membership as ambiguous. Browser evidence hash after refresh began `5717faec46aa`; synthetic authorization did not establish company permission.
- **Regression:** SDK-enabled suite **197/197 passed**, 0 skipped. Core suite **197 discovered; 161 passed/executed; 36 optional-SDK cases skipped** (not counted as passes); 0 failures/errors. Full record: `qualification/evidence/engineering-phase-python-regression-2026-11-24.log`.
- **Configuration-effort evidence:** `qualification/evidence/onboarding-baseline-comparison-2026-11-24.json` confirms the frozen baseline exposes no live onboarding CLI while this revision provides `onboard-live → onboard-review → investigate-mcp`. It counts a single digest-bound review artifact and 5–7 source/relationship decisions in the existing 16 synthetic environments. Human setup time, company engineering hours and ROI remain unmeasured.
- **Frozen release:** candidate SHA-256 remains `8cd4d26b58cec464e21bebc3a6c4704ea862ed496de5c729568f297970303f5d`; source-manifest file SHA-256 remains `dbfe462fa80ae9117a8541d9b6c75b7747c42d4683aee538d925babe8ccfcf88`. No candidate rebuild or publish.
- **Next executable task:** extend the fixed-answer live-MCP benchmark to materially different synthetic source topologies (separate/combined roles, effective-dated/static membership, explicit/missing relationships, event/arrival time and chamber/group equipment), preserving independent expected answers and counting wrong mappings, abstentions and review decisions. Internal tool/source permissions remain `PENDING_INTERNAL`; no company discovery is authorized or required for this next task.

### Adversarial onboarding topology coverage and approval-boundary fix — 2026-11-24

- **Fixed-answer live-MCP benchmark:** seven isolated official-SDK peers passed across standard separate sources, arrival-time-only events, static membership, missing step-instance relationship key, equipment-group-only events, duplicate event versions, and a semantically untyped process/outcome descriptor with a misleading name. Eight independently fixed role expectations; zero false mappings, zero source-row reads, and zero automated approvals. The complete result is `qualification/evidence/onboarding-live-topologies-2026-11-24.json` against `qualification/fixtures/live_onboarding_topologies_expected_v1.json`.
- **Scientific/authorization repair:** `APPROVE_EXACT_PROPOSAL` had silently accepted a partial event role and auto-filled optional unknown acknowledgments. It now rejects partial roles. The held-out test confirms the explicit reviewer form succeeds only when all incomplete fields are acknowledged. A group-only source keeps chamber identity unknown.
- **Documented CLI end-to-end:** ran the actual three commands from the P2 onboarding skill against an alternate seven-source schema: official-SDK metadata discovery, digest-bound synthetic review, then seven bounded reads and B01/B02/B03/B05 evidence. Results: 98 journeys, 403 instances, six route variants, 1 exact exposed / 4 potentially exposed / 5 unknown / 0 observed-unexposed for ten selected wafers; maintenance stays caller-supplied/unverified; causality stays not established. Query/audit hashes correlate. Evidence manifest and deterministic gzip: `qualification/evidence/onboarding-cli-100-alias-e2e-2026-11-24.json` and `qualification/evidence/onboarding-cli-100-alias-evidence.json.gz`.
- **Effort boundary:** three CLI stages produce a complete synthetic investigation. A fully compatible mapping is consolidated into one digest-bound review record with zero individual source-role fields; an explicitly reviewed partial case selects all seven role mappings and acknowledges missing fields. Five topology cases refuse approval pending additional evidence. The frozen baseline lacks an equivalent live onboarding workflow, so historical engineering time saved cannot be measured.
- **Regression:** SDK mode 198 discovered/executed/passed, no skips. Core mode 198 discovered, 162 passed/executed, 36 SDK-dependent skips, no failures/errors. Onboarding SDK module 14/14 passed. Log: `qualification/evidence/engineering-phase-python-regression-onboarding-2026-11-24.log`.
- **Frozen baseline preserved:** candidate `8cd4d26b58cec464e21bebc3a6c4704ea862ed496de5c729568f297970303f5d`; source-manifest file `dbfe462fa80ae9117a8541d9b6c75b7747c42d4683aee538d925babe8ccfcf88`.
- **Next executable task:** measure a distinct engineer-facing latency boundary once against the P2 standalone host: use repeated fixed 100-wafer runs and split MCP discovery, bounded reads, analysis, first filtered result, and export. Reuse existing browser workflow; no new UI framework or synthetic data expansion. Update a baseline comparison only if it adds independently measurable usability evidence.

### Standalone browser latency sample — 2026-11-24

- Reopened the actual local React runner after a host restart, which refreshed its loopback session token. The first stale page was correctly denied; reload recovered without bypassing the token check.
- One confirmed browser run completed after a 3,334 ms click-to-completed-observation interval (browser automation and status-query overhead included). It rendered 98 journeys / 403 actual step instances / five ordered route variants, with 24 exact, 25 potential, 49 unknown, zero verified-unexposed, contradictory coverage, and no causal conclusion. Evidence ID `SYN-p2-cb397660e17b`.
- Searching `SYN-EW-010` returned one journey with five chronological steps and repeated ETCH. The fill/read call took 91 ms, but render latency was not isolated. A screenshot showed the wide table requires horizontal scrolling at 1260 px; no UI change is justified by this single observation.
- This is one synthetic sample only: no p50/p95, browser memory, export action, human time, or separately isolated stage timing is claimed. The five-run acceptance remains PARTIAL. Full facts and limitations: `qualification/evidence/browser-onboarding-workflow-latency-2026-11-24.json`. Frozen archive and source-manifest checksums were reverified; no rebuild.
- **Next executable action:** resume five independently observed browser runs using bounded one-run interactions; if the browser harness repeatedly times out, record that limitation once and advance to a different independent offline/security qualification task.

- Prepared `qualification/ONBOARDING_SITE_MEASUREMENT_PROTOCOL.md`: an authorized paired study against the site's actual current manual practice, with stop conditions, phase-level timing, independent evidence scoring, and ROI only after validated labor/cost inputs. It is ready for site review but has not been executed; no company time or savings is claimed.

### Current locked-dependency advisory refresh — 2026-11-24

- `pip-audit 2.10.1` queried OSV for all 28 exact entries in the pinned MCP SDK lock (dependency resolution/install disabled): zero known vulnerabilities. `npm 11.20.0 audit --package-lock-only` reported zero known vulnerabilities across the locked React tree (99 total dependencies reported).
- Raw results, command lines, and lock/report hashes: `qualification/evidence/dependency-security-scan-2026-11-24.json`. This refresh is limited to those dependency graphs; source ownership/transfer, OS/runtime security, company policy, and manufacturing qualification remain pending. Frozen candidate and source-manifest hashes are unchanged; no package rebuild.
