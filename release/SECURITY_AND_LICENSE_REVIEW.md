# Security, dependency, and license review

Date: 2026-11-23  
Status: `PARTIAL`; this document is not a release approval.

## Local source and runtime inventory

- Core application/runtime imports use Python standard library modules only. The optional MCP transport uses the official MCP Python SDK 2.3.0; its pinned dependency closure is staged under `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/`.
- The product-neutral browser reference host uses local compiled React assets, HTML, and CSS with no CDN, remote font, analytics, or plugin registry. React, React DOM, and Scheduler are embedded in the static bundle, with upstream license notices in `ui/reference-host/THIRD_PARTY_NOTICES.md`.
- Node/npm are build and test tools only. The browser assets run without Node/npm and no `node_modules` tree is bundled. The lockfile and host-local npm cache allow a separate offline build.
- The optional SDK wheelhouse includes hash-pinned wheels, a per-wheel license inventory, and CycloneDX SBOM. It is not installed by the default core installer.
- `release/SBOM.spdx.json` inventories local files and reports project source ownership as `NOASSERTION`.
- A `pip-audit==2.10.1` scan against every exact entry in the pinned MCP lock queried the live OSV service on 2026-11-23 (UTC timestamp in evidence) and reported no known vulnerabilities across 28 packages. The scan used `--no-deps --disable-pip` to avoid platform-marker omissions. The result and lock hash are recorded in `qualification/evidence/mcp-dependency-vulnerability-scan.json`. The scanner itself was staged temporarily under `/tmp` and is not a product dependency.
- The locked React/Vite graph was checked with `npm audit` on 2026-11-23; it reported zero known vulnerabilities across the locked tree. Per-package license metadata is in `qualification/evidence/p2-react-dependency-audit.json`. The report separates embedded browser runtime packages from build/test tools. Source ownership and transfer rights remain unverified.
- Syft, Grype, and OSV-Scanner remain absent from the current PATH. `qualification/evidence/security-tool-availability.json` records the current availability and the separate pip-audit result.
- Runtime requires an already-installed Python 3.10+ interpreter. The bundle does not contain a Python runtime.

## Reviewed controls

- The API host accepts only loopback bind addresses, serves fixed paths, limits request bodies to 25 MiB and event/outcome arrays to 100,000 rows each, and does not log request content.
- The JSON API performs no external connection, tool call, database query, source write, or manufacturing actuation.
- Every analyzed event and outcome requires source metadata and an effective-dated relationship record; a Boolean flag alone is refused. Local snapshots and synthetic mappings do not authenticate company permissions. Only an out-of-band exact-scope authorization callback can produce `SOURCE_VERIFIED` coverage. Caller claims remain `ASSERTED_UNVERIFIED`, and cannot create a verified nonexposure comparator.
- Cross-source wafer identity requires an explicit approved identity relationship. The shared evidence envelope rejects unknown root and claim fields.
- No secrets or company mappings are included. The built-in records are synthetic.
- The loopback cancel route requires the per-process token. Analysis UUIDs are rate-bounded, only one engine analysis runs at a time, API request concurrency is capped, row processing cooperatively checks cancellation, and no partial evidence is returned. Ctrl-C signals active analysis and the server waits for its request threads to finish. The offline installer creates a managed venv without pip; the rollback removes only that marked venv.

## Release-blocking checks not performed

- The P2 source does not include a project license or ownership/transfer authorization. Do not treat `NOASSERTION` as permission to redistribute.
- No target-company security review or target-OS scanner result is included or claimed. The package audits are limited to the pinned Python MCP and npm dependency graphs at their recorded scan times; they do not cover the OS, Python runtime, browser host, or an internal deployment.
- A host-local macOS sandbox test denies outbound sockets while allowing loopback; this is not a target-site network-isolation or firewall qualification.
- There is no actual authentication boundary or internal MCP adapter to review. This candidate accepts local snapshots and must not be treated as an authenticated company service.

Gate E09 remains `PARTIAL` pending project ownership/transfer confirmation, company OSS review, target-OS coverage, and ongoing security review. Recorded Python and npm scans found no known vulnerabilities in the scanned locked dependency graphs at their respective capture times. Gate E05 remains `PENDING_INTERNAL` pending real source authorization and server-side least-privilege evidence.

## Current locked-dependency scan refresh — 2026-11-24

- `pip-audit 2.10.1` queried OSV for all 28 exact package entries in `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock`; the scan reported zero known vulnerabilities. Dependency resolution and installation were disabled.
- `npm 11.20.0 audit --package-lock-only` reported zero known vulnerabilities in the locked React dependency tree (99 dependencies reported by npm).
- Exact lockfile and raw report hashes are recorded in `qualification/evidence/dependency-security-scan-2026-11-24.json`.
- These scans cover only the two named dependency graphs at the scan date. They do not qualify the OS, Python runtime, browser runtime, target-company policy, source ownership, redistribution rights, or manufacturing data. Gate E09 remains `PARTIAL`; Gate E05 remains `PENDING_INTERNAL`.

## Bundled license-text reconciliation — 2026-11-24

- The pinned Python wheel inventory records an SPDX license expression and SHA-256 for each bundled license file. The `h11`, `mcp`, and `mcp-types` wheels had empty package metadata for the license expression; their bundled license files were hash-verified and identify the MIT License. The inventory and generated SPDX `licenseDeclared` fields now record `MIT` for those three packages. The wheel files retain the complete license texts.
- The staged Golden Agentic Engineering reference includes its MIT `LICENSE`; it applies to that reference repository only, not to P2 source ownership or any third-party files. The compiled React runtime includes its separate React, React DOM, and Scheduler notices.
- The P2 source package remains `NOASSERTION`; no project license, ownership statement, or transfer authorization is supplied. This correction resolves dependency metadata only and does not grant redistribution rights or close E09.
