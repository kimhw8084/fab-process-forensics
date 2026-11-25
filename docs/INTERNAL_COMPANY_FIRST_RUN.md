# Shortest *authorized* company-side qualification

**Never run this external bootstrap against actual company production systems.** This is a future operator procedure that the developed product must make executable; the included `python -m fabintel preflight` is explicitly synthetic and reports PENDING.

Target intended internal flow:
1. Obtain company approval for transfer; verify archive checksum, scanner reports and approved target OS architecture.
2. Transfer only reviewed source + binaries/dependencies/manifest through an authorized process. No external outbound connections, cloud models, or shipping real company data back out.
3. Install fully offline on the qualified OS using documented install/test commands. Select approved local/intranet model endpoint and authentication references without embedding credentials.
4. Run production-capable `qualify-internal` preflight built during the Codex goal: capability/permission discovery, version mapping against existing Fab Insight MCP, approved semantics + joins, read-only bounded retrieval, unit/time/grain/sampling checks, exact model protocol, audit/cancel/recovery and approved UI host auth.
5. Perform a small authorized read-only true-data pilot with an engineer. Reject real conclusions if source semantics, geometry, constraints, statistics or history are unverified.
6. Publish only the passed scope and actual residual caveats; obtain authorized security/owner and engineering approval before production use.

Company-specific endpoint names, permissions, OS, deployment host, authenticators, models, accepted source definitions and ROI baselines **cannot be established from this ZIP**. The internal preflight must discover or explicitly request them there, never invent them externally. No claim of zero-minute or guaranteed immediate production is defensible.

## Local capability-capture checker in this candidate

The bundled `python -m fabintel preflight --capabilities FILE.json` command checks a local capability capture against `contracts/adapter-operations.v1.json`. Start from `requirements/mcp-discovery.template.json`; record the exact contract version, discovered logical-operation tool names and exact tool versions, non-empty authorized read-only source scopes, query limits, audit support, and cancellation support. Do not place tokens, passwords, or other credential values in the capture. A structural `PASS` means only that this capture is complete and version-mapped. The command makes no MCP connection and always reports `PENDING_INTERNAL_QUALIFICATION`; it does not validate server authorization, real source semantics, or a first engineering result.

### Descriptor mapping proposal

`python -m fabintel onboard --descriptors FILE.json --output PROPOSAL.json` scans a local capture of MCP `tools/list` descriptors plus source semantics and relationship descriptors. It matches only the six frozen logical-operation signatures and the seven P2 source roles (process instances, outcomes, three coverage roles, route definitions, and lot membership). Source/relationship versions, field types and meanings, typed identity, timezone-aware event times, relationship keys, hashes, grains, and effectivity are checked structurally. The report includes exact candidates, rejected/ambiguous mappings, effectivity-bounded query-plan templates, and unresolved operator decisions. The proposal has no execution path; no candidate value, `approved` field, capture label, or synthetic test output establishes live permission or company source approval. Remove credentials and source rows before capture. The report stays `REVIEW_REQUIRED` even when all structural candidates are unique; an authorized engineer must review mappings, scope and limits, then run the existing server-enforced preflight and investigation workflow.

The checked-in descriptor capture and 13k scan benchmark are synthetic harness evidence only. They measure parser time, mapping accuracy against fixed synthetic answers, and required review decisions, not human onboarding time, actual source validity or company readiness.
