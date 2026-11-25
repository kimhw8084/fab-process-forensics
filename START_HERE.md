# Start here — FAB Process Forensics P2 candidate

This folder contains the available product and qualification resources. No setup dependency download or external research source is required for the local candidate workflow.

## Verify and run

1. Use Python 3.10 or newer.
2. Run `python bootstrap_check.py` to verify local source hashes and run the P2 test suite.
3. Run `python -m fabintel demo` for a deterministic synthetic evidence envelope.
4. Run `python -m fabintel preflight` to see the honest `PENDING_INTERNAL_QUALIFICATION` state.
5. Run `python -m fabintel serve --host 127.0.0.1 --port 8767`, then open `http://127.0.0.1:8767/`.

In the UI, load or open a local JSON snapshot, then choose an abnormal wafer cohort/outcome, an abnormal lot, or a process/maintenance/change interval scoped to an exact chamber/tool window. Condition labels are operator-supplied and unverified; tool scope matches exact event `tool_id` values, and missing tool assignment remains unknown. A lot start uses only outcome rows whose declared relationship includes both lot and wafer keys; it does not imply the snapshot contains every wafer in the lot. Apply the start to the snapshot, review caller-declared sources, relationships, scope, coverage, and payload/event/outcome limits, then run the deterministic analysis. Any snapshot edit clears previous findings and export and requires review again. The UI displays wafer journeys and route variants, classifies exact, possible, not-observed-exposed, and unknown populations conservatively, links exposure and outcome rows to source and relationship IDs, shows limitations, and downloads the evidence envelope. Coverage remains caller-declared until authenticated by an authorized live source. The built-in data is synthetic. No Fab Insight or company connector is included.

## Transfer candidate

`python release/build_bundle.py` creates a deterministic source ZIP and SHA-256 sidecar. `python release/verify_bundle.py` extracts it into a temporary folder, runs source integrity and scientific tests, runs the demo, installs with the local standard library only, and checks rollback. These checks cover the current macOS/arm64 host, not a blocked-egress target-site installation.

See `release/GATE_REPORT.json` for per-gate evidence and unresolved statuses. The product is `CANDIDATE`; no external or internal readiness claim is made.
