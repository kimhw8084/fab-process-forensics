# P2 React panel contribution

Version `1.0.0` is a headless module for a compatible shared React host. It does not create a suite route, choose sources, request data, manage authentication, or download files. The host passes a validated v1 P2 evidence envelope and owns start, cancel, retry, navigation, source permissions, and export actions.

The module exports `P2ProcessForensicsPanels`, `buildP2PanelModels`, and the TypeScript types in `src/types.ts`. A shared host may adapt its accessible table and journey visualization through the `components.Table` and `components.JourneyTimeline` props. The default table and timeline are semantic, keyboard-accessible fallbacks. Fallback tables page through 100 rows and journey detail pages show 25 wafers at a time; a host adapter receives the complete typed row set and may use its own virtualization. Chronological tables remain available alongside a host graph. `onInspectEvidence` delegates provenance drill-down to the host evidence inspector. Evidence is rendered only for the current `ready` request; stale envelopes are hidden while loading, cancelled, or failed.

## Mounting

Install this module into the P1 product registry and mount it inside the existing P2 route:

```tsx
<P2ProcessForensicsPanels
  state={request.state}
  evidence={request.evidence}
  components={{ Table: P1TableAdapter, JourneyTimeline: P1JourneyTimelineAdapter }}
  onCancel={request.cancel}
  onRetry={request.retry}
  onStartInvestigation={openHostInvestigationRequest}
  onInspectEvidence={openHostEvidenceInspector}
  onExportEvidence={hostEvidenceExport}
/>
```

The adapter props are declared in `P2TableProps` and `P2JourneyTimelineProps`; P1 maps them to its selected shared components. The P2 package has a React peer dependency (`>=18.2.0 <20`) and no other runtime dependency. The local compatibility fixture uses React, React DOM, TypeScript, and jsdom as development-only dependencies.

## Local qualification

Run `npm ci --offline --ignore-scripts` followed by `npm test` when the pinned packages are present in the local npm cache. The seven tests mount the component in a synthetic React host and exercise bounded large-history pagination, keyboard-focusable actions, evidence drill-down, cancellation, retry, source and relationship provenance, uncertainty/refusal/empty/stale-result states, and the frozen evidence contract. No mock permission label is company approval.
