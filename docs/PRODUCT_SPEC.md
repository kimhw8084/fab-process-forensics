# Complete engineering product specification — FAB Process Forensics

**Scope:** B01 Wafer Journey + B02 Exposure Mapper + B03 Route Mining + B05 Counterevidence  
**Product ID:** `p2`  
**Shared interface:** `contracts/SHARED_ARCHITECTURE.md` v1.0.0  
**State of supplied code:** BOOTSTRAP_ONLY. The actual product is to be built by Codex.

## Required result, not just a feature list
Give the engineer reliable backward wafer-journey and forward event-exposure reconstruction with tested contradictory explanations, instead of a visually convincing but potentially fictional causal graph.

## One real end-to-end engineer workflow
**Start:** Start from abnormal wafer/lot cohort and outcome, OR from a process/chamber/maintenance/change interval. Resolve candidate approved source relationships and query limits before traversal.

**Finish:** One validated chronological/relational investigation: exact manufacturing step instances, process-route/rework variants, exposed/unknown/unexposed populations with justifications, positive AND contradictory facts, data coverage, and evidence links. Never a fabricated root cause.

Codex must implement the complete path, not four/five disconnected notebooks. The operator must be able to produce a new authorized investigation, inspect evidence source-by-source, understand uncertainty, save/share a reviewable artifact and rerun the same result with frozen inputs and software version.

## Combined capability contract
| Subsystem | Required source evidence | Implementation required | Explicit scientific refusal boundary |
|---|---|---|---|
| **B01 journey** | Approved wafer/lot/route/equipment/step-instance entities and event times | Time-aware typed graph with repeated step occurrences; reconcile split/merge and incomplete histories | No guessed links or chronological order for ambiguous clocks |
| **B02 exposure** | Real chamber/tool processing assignment, maintenance intervals, bounded time windows | Predicate-based exact exposure using validated equipment + step instance + time criteria; separate exposure scopes | Sharing equipment group != common chamber exposure; time overlap alone != exposure |
| **B03 route intelligence** | Object-centric event records, approved route definitions and rework semantics | Process variants, conformance, rework and skipped/repeated operations; compare simple traversal vs object-centric mining | Never treat incomplete records as route violations |
| **B05 counterevidence** | Candidate causes, observed and unobserved cohorts, confounders, missing event coverage | Evidence matrix: support, contradiction, missing, non-discriminating evidence; prioritized next verification | Ranked hypothesis is not an established root cause |

## Shared scientific preconditions
1. Actual authorized source definitions are discovered from the existing approved Fab Insight MCP and checked for version/effective time; no invented company tool names or table joins.
2. Result data retains wafer/lot/step-instance/metric/tool/chamber where applicable, and always declares its true grain, timestamp semantics, units, sampling plan, exclusions and approved relationship source.
3. LLM may help translate user intent into a proposed plan; deterministic tools independently approve allowed sources/relationships/operations, compute results, and validate claims.
4. Every claim is typed, sourced, uncertainty-qualified, and distinguishable from a hypothesis. Invalid or incomplete analysis returns REFUSED/PARTIAL/INCONCLUSIVE as appropriate.
5. If advanced functionality requires unavailable real data, the rest of the product remains independently useful; no demo-generated fake findings in company mode.
6. No manufacturing equipment commands, recipes updates, unsupervised process holds, or other side effects.

## Expected usable deliverables
- Deterministic API/CLI and an interactive product view in ONE Fab Intelligence workspace, compatible with P1–P4 manifests.
- Source, population and assumption inspector; explanatory visuals with tabular alternatives; missing-data and refusal handling; evidence dossier with immutable source provenance.
- Independent scientific tests, held-out challenge suites, model-off path, permission-denial tests, full integration and UI interaction verification.
- Fully offline and tested target-OS binary/dependency package, licensing and SBOM, checksums, rollback/kill switch, minimal authorized internal MCP/model preflight.
- Reproducible user task evaluations and a nonfabricated ROI study plan; no unmeasured claims of customer adoption/financial returns.

## Non-goals and controlled dependencies
- Not a new semantic approval system or replacement for Fab Insight MCP.
- Not a generic RAG chatbot, autonomous production control service, or unrelated corporate workflow tool.
- Not a duplicate of the existing standalone sampling-prediction project.
- Not a promise that synthetic data proves any Samsung engineering effect.
- Keep independent capability modes when full cross-process/yield/change-control data is unavailable.

## Mandatory review artifacts
1. Algorithm and OSS tournament (`docs/SCIENCE_AND_METHODS.md`), showing why each included component is needed.
2. Data/source contract, every real permission/scope and invalid join case.
3. Product user journey, edge states and UI test evidence.
4. Scientific negative/positive oracles, verified comparisons with a simple baseline.
5. `release/GATE_REPORT.json` with gate-by-gate actual evidence and honest states.
6. Transfer package hash, offline dependency provenance, approved licensing and valid internal first-run preflight.
