# Read only MCP adapter

`fabintel.mcp_adapter.ConfiguredMCPAdapter` implements a configurable client for the six immutable logical operations in `contracts/adapter-operations.v1.json`: `discover`, `semantics`, `relationships`, `read_bounded`, `cancel`, and `audit`. It uses the official MCP Python SDK 2.3.0 for protocol and transport. The implementation contains no company endpoint names, credentials, source schemas, or permission defaults.

## Client configuration

The exact structure is defined in `contracts/p2-mcp-client-config.v1.schema.json`. Tool names are supplied by an authorized deployment; the client requires a distinct name for each logical operation and requires MCP tool annotations to mark every operation read-only and non-destructive.

Example Streamable HTTP configuration for a local mock service:

```json
{
  "schema_version": "p2-mcp-client-config/v1",
  "transport": {
    "kind": "streamable_http",
    "url": "http://127.0.0.1:8765/mcp"
  },
  "tools": {
    "discover": "discover",
    "semantics": "semantics",
    "relationships": "relationships",
    "read_bounded": "read_bounded",
    "cancel": "cancel",
    "audit": "audit"
  },
  "request_timeout_seconds": 8,
  "max_response_bytes": 32768
}
```

Remote Streamable HTTP requires HTTPS. HTTP is accepted only for loopback hosts. Credentials are referenced by environment-variable name and are never embedded in the config. Stdio arguments are a literal argument vector; shell command strings are not accepted. The adapter bounds each response, checks negotiated protocol, and refuses missing operations or unsafe annotations.

## Call sequence and validation

1. `discover()` records advertised operation/semantic versions, server row/byte/time limits, authorization scopes, and audit support.
2. `semantics(source_ids, version)` requires exactly one definition for every requested source, approved status, non-empty semantic versions, row grain, field definitions/units, effective bounds, and a source content hash. Duplicate source IDs are refused rather than overwritten.
3. `relationships(entity_refs, time_window)` accepts explicit approved or unapproved relationship records. An unapproved relation stays unapproved. Relationship IDs must be unique in the response; each approved join key must exist in the verified semantics of at least one declared source. Approved relations must cover the requested time range and match the discovered source hash and semantic version.
4. `read_bounded(plan, permission_context, limits)` requires a declared timezone-aware timestamp field, discovered semantics and relationship IDs, a permission scope advertised by the server, and limits at or below server limits. Every plan relationship must authorize the selected time field, and every row's source/relationship must also appear in the response-level provenance lists. It validates each row's time, grain, source version, approved relationship keys, total response bytes, and query hash.
5. `cancel(operation_id)` carries a UUID to the server and requires an explicit stopped/not-stopped response. Cancellation does not synthesize a partial result.
6. `audit(operation_id)` requires a completed read and checks permission scope, exact source IDs plus semantic versions and hashes, time bounds, and query hash.

These client checks supplement but do not replace server-enforced authorization, read-only source privileges, query limits, cancellation, and audit controls. Local configuration is not an authorization grant. The synthetic server demonstrates denied permission, over-limit requests, malformed time/grain/provenance, cancellation, and subsequent session recovery. Both stdio and Streamable HTTP tests negotiate the six operations; a separate Streamable HTTP challenge verifies server denial, row-limit enforcement, confirmed cancellation, retry, and matching audit query hashes after recovery.

`fabintel.mcp_workflow.investigate_with_mcp` connects the read path to the P2 analyzer. The mock engineer workflow requests process-step, wafer-outcome, exposure-coverage, process-history-coverage, approved route-definition, and route-coverage records in six separate `read_bounded` calls because their verified grains differ. Exposure, journey, and route coverage use separate sources so one declaration cannot qualify another analysis. Each explicit P2 `read_plans` dataset role must match the source semantics `record_kind`; unsupported or mismatched roles refuse before analysis. The role mapping is P2-local orchestration, not a new MCP operation or a company field requirement. Every read receives its own audit, source/relationship provenance, time check, and query hash before it is mapped into the snapshot. The journey fixture's four observed histories now carry a separately source-linked `COVERAGE_DECLARED_COMPLETE` record with its exact source, relationship, and record ID; that is still a synthetic caller assertion, not authenticated completeness. The workflow then runs journey/exposure/route/counterevidence analysis and records all read/audit references in the envelope. The synthetic fixture's record-kind labels are only test semantics. The result remains `SYNTHETIC_DEMO` and explicitly marks its approval and permission labels as unauthenticated for company use. `python qualification/run_mock_mcp_workflow.py` captures the reproducible multi-grain synthetic example.

## Offline dependency qualification

The core engine remains Python standard library only. The optional MCP SDK and its transitive dependency closure are staged in `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/`, with a hash-pinned requirements lock, wheelhouse, license inventory, and CycloneDX SBOM. `python release/install_offline.py --with-mcp` installs only from this wheelhouse with `--no-index` and `--require-hashes`. The bundled wheelhouse has been exercised only on macOS arm64 CPython 3.11; other target platforms remain `NOT_VERIFIED` until matching pinned artifacts and offline tests exist.

The current local mock tests verify stdio and Streamable HTTP against the pinned SDK, including denial and cancellation/recovery over HTTP. This is external protocol compatibility evidence only. Actual company binding, schemas, credentials, permission scope, source provenance, deployment settings, license approval, and security approval remain `PENDING_INTERNAL`.
