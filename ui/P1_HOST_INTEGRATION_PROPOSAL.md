# P2 React module handoff for the P1 host

Status: P2 module `1.0.0` is implemented and executable against a synthetic React host. The P1 source tree and its component API are not present in the approved local workspace, so actual suite mounting remains pending the one P1 host integration.

## Contribution package

Register `ui/contribution.manifest.json` with the existing P1 product registry. It declares product `p2`, route `/fab-intelligence/p2`, module version `1.0.0`, evidence contract `1.0.0`, and these module files:

The manifest uses integration mode `react-host-module`; the prior DOM renderer remains available as the legacy fallback.

- Runtime ESM: `ui/p2-react/dist/index.js`
- Manifest export: `ui/p2-react/dist/index.js:P2ProcessForensicsPanels`
- Type declarations: `ui/p2-react/dist/index.d.ts`
- Source: `ui/p2-react/src/`
- Package metadata and peer range: `ui/p2-react/package.json`
- Synthetic mount compatibility test: `ui/p2-react/test/p2-host.integration.test.mjs`
- Integrated mock-MCP envelope: `qualification/evidence/mcp-end-to-end-workflow.json`

The module peer-depends on React `>=18.2.0 <20`, has no other runtime dependencies, and does not create a route or page shell. Its local fixture was executed with React/React DOM `19.3.1`; a copied host fixture also passed on React/React DOM `18.3.1` and TypeScript declaration checking against `@types/react 18.3.28`. P1 still needs to confirm its exact host version. The package development tool licenses and full dependency closure are recorded in the React-module qualification evidence.

## Mount in the existing P1 route

The host registers the existing P2 route and mounts this component inside the shared shell. The host validates the evidence envelope and maps its own current request state and shared components into the P2 adapter types:

```tsx
import {
  P2ProcessForensicsPanels,
  type P2EvidenceEnvelope,
  type P2TableProps,
  type P2JourneyTimelineProps,
} from "@fab-intelligence/p2-process-forensics-panels";

function P2Route({ request }: { request: P1InvestigationRequest }) {
  const evidence = request.evidence as P2EvidenceEnvelope | undefined;
  return (
    <P2ProcessForensicsPanels
      state={request.state}
      evidence={evidence}
      components={{
        Table: (props: P2TableProps) => <P1AccessibleTable {...adaptP1TableProps(props)} />,
        JourneyTimeline: (props: P2JourneyTimelineProps) => <P1JourneyView {...adaptP1JourneyProps(props)} />,
      }}
      onCancel={request.cancel}
      onRetry={request.retry}
      onStartInvestigation={() => openP1InvestigationRequest("p2")}
      onInspectEvidence={reference => openP1EvidenceInspector(reference)}
      onExportEvidence={envelope => exportP1Evidence(envelope)}
    />
  );
}
```

`P1InvestigationRequest`, `P1AccessibleTable`, `P1JourneyView`, and the `adaptP1...` functions above name the existing host API that P1 supplies; they are not new P2 or shared-contract exports. The executable P2 adapter contract is `P2TableProps` and `P2JourneyTimelineProps` in the module declarations. Map the P1 components to these props without changing the frozen evidence or product contracts. If the P1 graph contract cannot render journey relationships, use the accessible chronological table supplied by the P2 module and keep P1's shared graph conventions for any graph view.

## Panel and responsibility mapping

The mounted contribution has five domain panels: `journey` (wafer/lot history), `exposure` (verified exposure and comparator populations), `route` (route/rework variants and conformance), `counterevidence` (competing hypotheses), and `evidence` (sources, permissions, uncertainty, and reproducible evidence). Summary claims and limitations appear inside the evidence panel and the top status banner. The B01 chronological table remains available when P1 renders a journey visualization.

P1 retains route/navigation, source selection, authentication and permissions, request lifecycle, cancellation, retry, evidence inspection navigation, and export signing/download. P2 renders the validated evidence envelope, emits source/relationship references to the host inspector, and accepts host callbacks. It contains no fetch, MCP session, credential, authorization decision, or export implementation.

Refusal, error, cancellation, empty history, partial coverage, ambiguous chronology, and synthetic-demo states are explicit. Source permission fields are displayed as evidence references and do not independently establish access authorization. The module does not make causal claims beyond the envelope's supported claims.

## Compatibility check

From the product root:

```sh
cd ui/p2-react
npm ci --offline --ignore-scripts
npm test
```

The test mounts the component in jsdom using synthetic host table and journey adapters, checks every domain panel and table structure, follows evidence references to host callbacks, verifies host cancellation/retry/export delegation, exercises large-history pagination, and tests refusal, error, and empty states. It does not claim integration with an unavailable combined-suite source tree or its assistive-technology/browser acceptance suite.

## Remaining P1-owned work

P1 must confirm its React version and adapt its existing table/timeline/evidence-inspector components, register the route, and run its own browser workflow. This one host dependency does not block independent P2 scientific, MCP, or release work. No P1-owned contract or company approval was inferred or changed here.
