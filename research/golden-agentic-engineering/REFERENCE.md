# Golden Agentic Engineering reference snapshot

This folder contains the Golden source material used in the P2 continuation, copied from the exact user-pinned commit:

- Repository: https://github.com/kimhw8084/golden-agentic-engineering
- Commit: `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e`
- Commit URL: https://github.com/kimhw8084/golden-agentic-engineering/commit/dc2ece864b2d744e47dfe8c7d9ad78aadbed369e
- Upstream license: [`LICENSE`](LICENSE), MIT for original Golden starter files.
- Upstream checksum list: [`SHA256SUMS.txt`](SHA256SUMS.txt).

The selected snapshot keeps the routing contract, relevant engineering skills and agents, manufacturing/MCP/UI/offline guidance, qualification status, and SDK candidate evidence beside this product. It does not copy Golden's unrelated app examples, control-plane implementation, or unrelated skill instructions.

## Qualification boundary

Golden identifies itself at this commit as an OpenCode-first, pre-company qualification pilot. Its synthetic MCP, React/NiceGUI examples, and offline evidence are engineering references, not company qualification or Samsung approval. The P2 Codex skills under `.agents/skills/` are scoped adaptations of the relevant Golden routes and this product's frozen v1 contract. They do not create a new authority, UI shell, MCP wire protocol, or company semantic map.

## Selected local references

- `standards/rules.json`, `standards/release.json`: deterministic rule catalog and pilot release status.
- `workflows/task-routing.json`, `schemas/task-routing.schema.json`: task classification, direct/specialist routing, and skill/MCP ordering.
- `opencode-skills/`: relevant manufacturing, MCP, React, NiceGUI, offline toolchain, and release skills.
- `opencode-agents/`: primary engineering, investigation, architecture, and independent verification roles.
- `integrations/mcp/README.md`: official SDK candidate and protocol qualification notes.
- `offline/README.md`, `offline/mcp-sdk-candidate/`: no-egress process and pinned MCP SDK candidate records.
- `research/`, `DEPENDENCY_LICENSE_REPORT.md`, `evidence/`: candidate selection, license scope, and date-bound prequalification evidence.
- The current-host SDK wheelhouse used for P2 testing is staged under `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/`; its hashes, lock, license inventory, and SBOM travel with it.

At the time of this snapshot, Golden reports 19 deterministic rule descriptors against 151 proposed requirements; its overall state is PRE_QUALIFICATION. Consult `docs/QUALIFICATION_MATRIX.md` and `evidence/PRECOMPANY_EVIDENCE.json` for the original scope and limits.
