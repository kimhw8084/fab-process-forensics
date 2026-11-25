# P2 React host handoff

This local handoff is for a compatible shared React host review. It contains the versioned headless Process Forensics module, synthetic React host tests, frozen evidence/product contracts, exact mount proposal, and six-source mock evidence, including separately source-linked process-history coverage. P2 also has its own product-neutral reference runner in `ui/reference-host/`; that runner is not a substitute for combined-suite integration and is not a second suite framework.

## Mounting

Follow `ui/P1_HOST_INTEGRATION_PROPOSAL.md` when the shared host integration is available. The host registers `ui/contribution.manifest.json`, mounts `P2ProcessForensicsPanels` at the P2 route, and adapts its accessible table, journey, evidence inspector, cancellation, retry, and export callbacks to the exported types in `ui/p2-react/dist/index.d.ts`.

The host owns route registration, source selection and permissions, request lifecycle, navigation, and export. The shared v1.0.0 evidence and product-manifest contracts are included unchanged; no shared contract modification is required for this module contribution.

## Verification

The synthetic evidence in `qualification/evidence/mcp-end-to-end-workflow.json` is consumed by the module tests. The locked npm development toolchain can be installed with `npm ci --offline --ignore-scripts` from `ui/p2-react` when its pinned packages are already in the local npm cache; `npm test` builds types and mounts all five panels, including bounded fallback pagination for large histories. The current module suite passes seven tests. The separate React 18.3.1 and 19.3.1 synthetic host compatibility matrix passes seven tests per host; the React 18 declaration fixture type-check also passed. The independently runnable reference host is built from these same panels and is qualified separately through real browser interaction and the SDK-backed six-source workflow. A clean handoff extraction verifies only the shared-host module; it does not verify an unavailable combined suite's exact API or browser workflow.

## Boundaries

All mock source semantics and mock permissions are synthetic and are not Samsung/company approval. The package metadata currently uses `UNLICENSED`; this local handoff does not grant source redistribution or company transfer rights. Do not publish or redistribute it without the applicable owner approval.
