# Product-specific risks and mandatory mitigations

| Risk | Mitigation / release condition |
|---|---|
| Overconnected graph | Typed relationship approvals, exact join grain and cardinality checks |
| Partial data interpreted as full route | Explicit event coverage/unknown edges; no total completeness claim without route oracle |
| Time overlap mistaken for causal exposure | Separate exposure predicates and unknown sets; precise equipment/chamber scopes |
| LLM narrative invents a path | Deterministic graph->claim validation; independent source-to-claim audit |
| Large graph memory explosion | Bounded traversal, paging and query limits; benchmark representative 13K-schema discovery |
| Licenses/low maturity of research engines | Baseline plain graph and benchmark candidate before selection |
