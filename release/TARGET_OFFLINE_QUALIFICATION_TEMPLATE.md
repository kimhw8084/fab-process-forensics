# Offline installation qualification for P2

This bootstrap runs with Python 3.10+ standard library only. It is NOT evidence that later production dependencies install offline.

- Discover and document actual approved target OS and arch before declaring them supported; build matching wheels, binary caches and UI static assets externally.
- Lock direct/transitive source hashes and licenses; generate and inspect SBOM and vulnerability scan with date of vulnerability database.
- Extract fresh artifact into network-isolated machine with no preexisting package cache; verify offline install, launch, full user path, cold-start, DNS/eRPC egress failures, cancel, permission denial and rollback.
- Record exact commands, OS+arch, image hash, package hashes, system clock, test logs and network isolation method in release evidence.
- The real internal MCP/model endpoints are approved intranet exceptions, not a reason to permit public internet access.
- Cross-platform builds are not automatically valid just because Python source is portable.
