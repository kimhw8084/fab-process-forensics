# Concrete engineer experience and acceptance walkthrough — FAB Process Forensics

This document defines the acceptance target for one coherent engineer workflow. The current candidate implements a local snapshot loader, a provenance-and-limit preflight before analysis, deterministic analysis, and JSON export in `ui/index.html`. It does not use an authenticated workspace, query Fab Insight MCP, or authenticate caller-declared permissions. The target acceptance items below remain in force; local demonstration is not company qualification.

## Minimum user journey
1. Start from an abnormal wafer cohort, an abnormal lot, or a suspected process/chamber/tool exposure interval. All starts use the same event model.
2. Display source/relationship approval status and actual chamber/time provenance before exposing a path. Show unknown/partial edges differently from approved ones.
3. Wafer journey timeline with separate rework occurrences and support for split/merge lot membership. Selecting an event drills to source/effective time.
4. Exposure sets: exposed, potentially exposed, unknown, and not observed exposed only under a source-linked coverage declaration; show the coverage source, relationship, record ID, denominator, and missing population.
5. Route variants panel with chronological uncertainties, explicit rework references, route-version changes, coverage states, and missing-event notes.
6. Hypothesis/counterevidence matrix that actively finds contradictory normal-vs-abnormal cases; export complete trace and tested predicate.

### Current local candidate flow

1. Load the bundled synthetic example or open a caller-supplied local JSON snapshot.
2. Choose **Abnormal wafer cohort and outcome**, **Abnormal lot and outcome**, or **Process/maintenance/change interval**. The operator labels the interval context, and the output marks that label as unverified. Equipment scope is one exact chamber or exact tool ID. If both chamber and tool are present in the snapshot, chamber remains the selected scope and tool is context; a tool-only scope matches the exact event `tool_id`. Missing tool assignment remains unknown and no chamber membership is inferred. A lot start derives wafer membership only from outcome rows whose declared relationship keys include `lot_id` and `wafer_id`; it retains normal outcomes as counterevidence and warns that the local snapshot may be incomplete. Applying a start edits only the local snapshot and issues no query.
3. Run **Review source relationships and limits**. The loopback preflight lists source records, declared relationship keys/grains/effective dates, relationship row usage, event/outcome counts, exposure scope, coverage, and request bounds. It performs no analysis or data query.
4. The analysis button becomes available only after a successful review; any input edit invalidates that review, clears prior findings and disables export. While analysis is running, the same control becomes **Cancel analysis**. Editing the snapshot also requests cancellation.
5. Run the deterministic engine and inspect journeys, route variants, exposure evidence, source-linked condition-event context, four exposure states, outcome support and counterevidence, confounder strata, uncertainty, and limitations; export the envelope as JSON. A cancellation stops at cooperative row-processing checkpoints and returns no partial findings or export; the reviewed snapshot can be run again.

The local browser flow uses a visible, keyboard-operable **Open JSON file** button that activates the hidden native file input. Source/relationship tables and result tables render captions, header scopes and table sections; the concise preflight announcement is separated from the full provenance region so assistive technology is not asked to announce every table cell as a live update. A local automated browser replay exercised keyboard activation and verified the rendered semantics, but did not operate the native OS dialog manually or use screen-reader assistive technology.

## P2 panels for shared-host integration

`ui/contribution.manifest.json` declares the frozen P2 product route, required data, analysis entrypoint, and evidence version. `ui/p2-panels.js` exports DOM-only render functions for findings, journey/route, exposure, counterevidence, and provenance. The functions accept host-provided containers and a validated evidence envelope. They create text and tables using DOM APIs and add no router, token set, or shared UI framework. The local demonstration invokes the same panel module; P1 can mount these panels inside its selected shell when that shell and its visual components are available.

Preflight status `READY_FOR_LOCAL_ANALYSIS` means the caller-declared snapshot is structurally usable under local limits. It does not mean the source or permissions were authenticated.

The local start controls support caller-declared abnormal wafer cohorts, lot membership explicitly represented in related outcome rows, or one process/maintenance/change interval scoped to an exact chamber/tool window over an already loaded snapshot. A maintenance/change label is caller context rather than verified condition evidence. Lot-level source discovery requires an authorized adapter and remains unavailable here.


## Actual interaction acceptance
- Using the input form or structured engineering request, user can choose/confirm exact scope and identify output in deterministic mode with an approved source context.
- Source inspector shows permission, semantic version, metric/unit, population count, join grain, sampling coverage and effective date; if invalid, the analysis cannot misrepresent it as verified.
- All charts provide accessible text/tabular data; keyboard navigation and screen-reader semantics are evaluated in the actual qualified browser.
- File selection must have a visible keyboard-accessible activation control; rendered tables require captions and scoped column headers; long provenance content must not be announced as one verbose live-region update. Local browser evidence checks these structures, while target screen-reader acceptance remains outstanding.
- The local deterministic analysis can be cancelled from the keyboard-operable run control or by editing the snapshot. Cancellation is scoped by a per-request UUID, uses the authenticated loopback API, returns no partial evidence, and leaves the reviewed unchanged snapshot available for retry. Actual bounded MCP-query cancellation still requires internal adapter qualification.
- Partial failures remain visible with precise retry and provenance boundaries.
- Export artifacts include exact data reference/query IDs, chosen evidence snapshot, input hash, method/software version, parameters, exclusions, uncertainty and timestamp. Repeat analysis matches within fixed deterministic numerical tolerance.
- Model offline/unavailable or hallucinated tool call: engine remains useful, forbids unauthorized source access, and either follows deterministic form controls or declines unsupported natural-language conversion safely.
- Empty data and conflicting source definitions result in an actionable state without replacing missing evidence with synthetic values.

## Avoid overbuilding
Reuse one existing approved engineering UI platform where compatible; otherwise one local/intranet host for all P1–P4. Keep JS/CSS bundled locally; no remote icons, fonts, scripts, license checks or telemetry. OpenCode MCP Apps rendering is optional and must be independently confirmed before relying on it.
