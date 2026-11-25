# P2 research status — 2026-11-22

These evaluations are not company qualification or proof of Samsung manufacturing performance.

- Existing Fab Insight MCP and approved internal OpenCode/LLM remain required integration points; actual company interfaces are unknown. P2 now has a configurable official MCP SDK client tested against synthetic stdio and Streamable HTTP servers. Actual company binding remains internal.
- P1-owned DuckDB, Pandera, statsmodels, ruptures, and River remain P1 candidates; compare them against simple deterministic baselines before adding them.
- NetworkX 3.1 was measured against P2 typed adjacency traversal. See `qualification/evidence/graph-library-benchmark.json`. It remains an independent algorithm oracle, not a product runtime dependency.
- The stdlib material-edge interval index matched the fixture-derived oracle on 100,000 synthetic time queries and exceeded the precommitted 1.25× batch speedup threshold; it remains a synthetic local screen with additional traced memory, not fab-scale qualification. See `qualification/evidence/benchmark-material-edge-index-run.log`.
- DuckDB was not adopted because the bounded local snapshot workload did not present an analytical use case that justified adding a native runtime dependency.
- Cytoscape.js remains a shared-shell visualization choice for P1; P2 contributes headless panels and does not establish a separate visualization foundation.
- Object-centric mining screening and the permissive-license/fit decision are documented in `docs/DECISION_RECORD.md`; no candidate is bundled.
- The optional MCP SDK wheelhouse is hash-pinned, has a per-wheel license inventory and CycloneDX SBOM, and passed the recorded pip-audit scan. Company OSS/license-transfer approval remains pending.

The user-authorized Golden Agentic Engineering source is staged under `research/golden-agentic-engineering/` at commit `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e`. It is a reusable engineering reference, not Samsung qualification. Deployment does not require network access to this source.
