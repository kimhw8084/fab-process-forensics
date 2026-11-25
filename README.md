# FAB Process Forensics P2 candidate

This folder contains the P2 source, frozen v1.0.0 shared contracts, local synthetic fixtures, deterministic analysis, reusable headless investigation panels, a loopback-only engineer UI, a configurable read-only MCP adapter tested against a synthetic server, qualification evidence, and candidate packaging tools. The core uses Python's standard library; the optional MCP SDK is pinned and vendored for offline installation on macOS arm64 CPython 3.11.

**Release state: CANDIDATE.** Do not present this package as `EXTERNAL_TRANSFER_READY` or `READY_INTERNAL`. No authorized Fab Insight MCP connection, actual source mappings, company permissions, target-site network-isolation proof, source license/ownership approval, or company engineering evaluation is included.

## Run locally

From this folder with Python 3.10 or newer:

```text
python bootstrap_check.py
python -m fabintel demo
python -m fabintel preflight
python -m fabintel serve --host 127.0.0.1 --port 8767
```

The UI is available at `http://127.0.0.1:8767/`. Load a local snapshot and choose an abnormal wafer cohort, an abnormal lot, or a process/maintenance/change interval scoped to an exact chamber/tool window. Condition labels are operator-supplied and unverified; tool scope matches exact event `tool_id` values, and missing tool assignment remains unknown. A lot start uses only outcome rows with a declared relationship that includes both lot and wafer keys; it cannot establish complete lot membership. Review source-linked records, effective-dated relationships, scope, coverage provenance, and payload/event/outcome limits before analysis. Editing the snapshot clears prior findings and export and disables analysis until preflight runs again. Its per-process token protects the loopback API from cross-origin requests. Preflight and analysis process only local JSON; neither connects to a fab data source or authenticates company permissions. Stop the foreground process with Ctrl-C.

To operate the seven-role synthetic MCP investigation in a browser, install the staged MCP SDK with `python release/install_offline.py --with-mcp`, build `ui/reference-host/dist` from the locked React/Vite dependencies (`cd ui/p2-react && npm ci --offline --ignore-scripts && npm run host:build`), then run `python -m fabintel serve --host 127.0.0.1 --port 8765` and open `http://127.0.0.1:8765/reference/`. This reference runner uses the actual P2 React panels and the official SDK against the local read-only synthetic peer. It performs discovery plus bounded reads across seven source roles, shows B01/B02/B03/B05 evidence and provenance, supports cancel/retry and downloads the evidence envelope. Its coverage claims are explicitly unverified synthetic assertions. After building, browser operation needs no Node/npm or external network.

For a configured MCP environment, `python -m fabintel onboard-live --transport transport.json --start ... --end ... --output proposal.json` inspects tool/source/relationship descriptors only; it does not read manufacturing rows. Review the exact proposal and its `proposal_sha256`. A unique, structurally compatible mapping may use one digest-bound `APPROVE_EXACT_PROPOSAL` decision; ambiguous roles require explicit per-role decisions. `onboard-review` validates and pins that review. Only `investigate-mcp` executes its bounded read plan, and the MCP server remains the permission authority. The local review record does not establish company authorization.

For authorized internal OpenCode onboarding, open this extracted P2 root and start with the single instruction `@p2-internal-onboarding`. The skill uses the configured company-approved model only, refuses public/cloud fallback, keeps descriptors and evidence outside this source tree, and requires an engineer-approved digest-bound plan before bounded reads. No external AI service is used by the product; if the company-approved model or MCP connection is unavailable, run only local diagnostics and leave company qualification pending.

For a local evidence snapshot, run `python -m fabintel analyze path/to/snapshot.json --output result.json`. The snapshot must contain source records, approved relationship records, timezone-aware timestamps, and the full exposure scope. Only `SOURCE_VERIFIED` coverage supports a confirmed `NOT_OBSERVED_EXPOSED` negative; caller assertions remain `ASSERTED_UNVERIFIED`, and nonmatches remain unknown or separately labeled as asserted nonmatches, never verified unaffected comparators.

## Offline package workflow

`python release/install_offline.py` creates a bundle-managed virtual environment without pip or package downloads. `python release/uninstall_offline.py` removes only that environment. Build and verify a deterministic source ZIP with:

```text
python release/build_bundle.py
python release/verify_bundle.py
```

The verifier checks a fresh extraction, integrity manifest, hash-checked no-index MCP installation, full test suite, demo, and rollback. This is qualified only on the observed macOS/arm64 CPython 3.11 host. It does not prove a target-site installation or network policy. The Python runtime must be supplied and qualified for the eventual target OS.

## Local resources and unresolved authority

All implementation inputs used here are in this folder. Golden Agentic Engineering is staged at the supplied pinned commit, and applicable practices were adapted into Codex skills. Golden is an external engineering reference, not company qualification. The authoritative literal R01–R53 text remains unavailable and is `NOT_VERIFIED`; no requirement text was invented. The template under `requirements/` contains blank logical MCP operation mappings and must only be populated through authorized internal discovery.
