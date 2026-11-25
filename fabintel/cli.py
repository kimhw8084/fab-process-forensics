"""P2 local commands; live MCP metadata or reads require explicit subcommands."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from fabintel.catalog import synthetic_catalog
from fabintel.contracts import validate_envelope
from fabintel.project import analyze

BASE = Path(__file__).resolve().parent.parent
MAX_INPUT_BYTES = 25 * 1024 * 1024
ADAPTER_CONTRACT = json.loads((BASE / "contracts" / "adapter-operations.v1.json").read_text(encoding="utf8"))
LOGICAL_OPERATIONS = {item["name"] for item in ADAPTER_CONTRACT["logical_operations"]}


def _read_json(path: str):
    file_path = Path(path)
    if file_path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"Input exceeds the {MAX_INPUT_BYTES}-byte local processing limit.")
    return json.loads(file_path.read_text(encoding="utf8"))


def _readiness_diagnostic():
    report_path = BASE / "release" / "GATE_REPORT.json"
    try:
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes)
        gates = report["gates"]
        product_states = report["product_states"]
        transfer = product_states["EXTERNAL_TRANSFER_READY"]
        internal = product_states["INTERNAL_QUALIFICATION_PENDING"]
        implementation = product_states["P2_PRODUCT_IMPLEMENTATION_COMPLETE"]
        standalone = product_states["P2_STANDALONE_WORKFLOW_VERIFIED"]
        external_ids = ("E01", "E02", "E03", "E04", "E06", "E07", "E08", "E09", "E10", "E11")
        internal_ids = ("E05", "E12")

        def selected(ids):
            return {
                gate_id: {
                    "status": gates[gate_id]["status"],
                    "gap": gates[gate_id].get("gap", ""),
                }
                for gate_id in ids
            }

        external_gates = selected(external_ids)
        internal_gates = selected(internal_ids)
        external_status = "PASS" if all(item["status"] == "PASS" for item in external_gates.values()) else "PARTIAL"
        return {
            "source": "release/GATE_REPORT.json",
            "source_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "external_engineering": {
                "status": external_status,
                "gates": external_gates,
                "open_gate_ids": [key for key, value in external_gates.items() if value["status"] != "PASS"],
                "p2_implementation": implementation["status"],
                "standalone_workflow": standalone["status"],
            },
            "formal_transfer_and_target_security": {
                "status": transfer["status"],
                "gap": transfer.get("gap", ""),
            },
            "internal_qualification": {
                "status": internal["status"],
                "gates": internal_gates,
                "gap": internal.get("gap", ""),
            },
            "canonical_requirements": {
                "status": "NOT_VERIFIED",
                "source": "requirements/AUTHORITY_AND_GAPS.md",
                "reason": "The authoritative literal Samsung R01-R43 text is not bundled; do not reconstruct it.",
            },
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "source": "release/GATE_REPORT.json",
            "status": "NOT_VERIFIED",
            "reason": "The packaged gate report is missing or invalid; no readiness status was inferred.",
        }


def _preflight_report(payload=None):
    if payload is None:
        return {
            "status": "PENDING_INTERNAL_QUALIFICATION", "network_requests": 0,
            "adapter": "no live adapter configured",
            "reasons": [
                "Real approved MCP capabilities and permissions are not available in this folder.",
                "Approved local model, UI host, and company target OS require authorized verification.",
            ],
        }
    missing = []
    if not isinstance(payload, dict):
        missing.append("discovery payload must be a JSON object")
        payload = {}
    if _contains_credential_field(payload):
        missing.append("credential material must not be included in a capability capture")
    if payload.get("contract_version") != ADAPTER_CONTRACT["contract_version"]:
        missing.append(f"adapter contract version must match {ADAPTER_CONTRACT['contract_version']}")
    operations = payload.get("operations")
    if not isinstance(operations, dict):
        missing.append("operations mapping for the logical adapter contract")
        operations = {}
    mapped_tools = set()
    for operation in sorted(LOGICAL_OPERATIONS):
        if not isinstance(operations.get(operation), str) or not operations[operation].strip():
            missing.append(f"logical operation mapping: {operation}")
        else:
            mapped_tools.add(operations[operation].strip())
    for operation in set(operations) - LOGICAL_OPERATIONS:
        missing.append(f"unsupported logical operation mapping: {operation}")
    tool_versions = payload.get("tool_versions")
    if not isinstance(tool_versions, dict):
        missing.append("exact version mapping for discovered tools")
        tool_versions = {}
    exact_tool_versions = set()
    for tool_name in sorted(mapped_tools):
        version = tool_versions.get(tool_name)
        if not isinstance(version, str) or not version.strip() or version.strip().lower() in {"latest", "unknown", "n/a", "template"}:
            missing.append(f"exact tool version: {tool_name}")
        else:
            exact_tool_versions.add(tool_name)
    permission = payload.get("permission_scope")
    if not isinstance(permission, dict) or permission.get("read_only") is not True:
        missing.append("read-only permission scope attestation")
    else:
        scopes = permission.get("source_scopes")
        if not isinstance(scopes, list) or not scopes or any(not isinstance(scope, str) or not scope.strip() for scope in scopes):
            missing.append("at least one explicit approved source scope")
    limits = payload.get("limits")
    if not isinstance(limits, dict):
        missing.append("bounded query limits")
    else:
        for key in ("max_rows", "max_bytes", "timeout_seconds"):
            if not isinstance(limits.get(key), int) or isinstance(limits.get(key), bool) or limits[key] < 1:
                missing.append(f"positive limit: {key}")
    for key in ("semantic_version", "auth_scope"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            missing.append(f"non-empty discovery field: {key}")
    if payload.get("audit_supported") is not True:
        missing.append("audit support must be explicitly true")
    if payload.get("cancel_supported") is not True:
        missing.append("cancellation support must be explicitly true")
    return {
        "status": "PENDING_INTERNAL_QUALIFICATION",
        "capture_structure": "PASS" if not missing else "INCOMPLETE",
        "missing": missing,
        "contract_version_checked": ADAPTER_CONTRACT["contract_version"],
        "operation_mappings_checked": sum(1 for operation in LOGICAL_OPERATIONS if isinstance(operations.get(operation), str) and operations[operation].strip()),
        "distinct_tools_checked": len(mapped_tools),
        "tool_versions_checked": len(exact_tool_versions),
        "network_requests": 0,
        "meaning": "Local capture review only; payload claims are not live MCP authorization or compatibility evidence.",
    }


def _contains_credential_field(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if any(marker in normalized for marker in ("password", "secret", "apikey", "authorization", "credential")) or normalized in {"token", "accesstoken", "refreshtoken"}:
                return True
            if _contains_credential_field(child):
                return True
    elif isinstance(value, list):
        return any(_contains_credential_field(item) for item in value)
    return False


def main():
    parser = argparse.ArgumentParser(prog="python -m fabintel")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("demo")
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--capabilities", help="path to a locally captured, versioned, read-only capability JSON; do not include credentials")
    onboarding = commands.add_parser("onboard")
    onboarding.add_argument("--descriptors", required=True,
                            help="path to a local MCP tool/source/relationship descriptor capture; no credentials or source rows")
    onboarding.add_argument("--output", default="", help="write the non-authorizing mapping proposal under this path")
    live_onboarding = commands.add_parser("onboard-live")
    live_onboarding.add_argument("--transport", required=True, help="authorized local MCP transport JSON; only environment-variable references for credentials")
    live_onboarding.add_argument("--start", required=True, help="timezone-aware metadata relationship window start")
    live_onboarding.add_argument("--end", required=True, help="timezone-aware metadata relationship window end")
    live_onboarding.add_argument("--output", default="", help="write metadata-only mapping proposal")
    review_onboarding = commands.add_parser("onboard-review")
    review_onboarding.add_argument("--proposal", required=True, help="live metadata-only onboarding proposal JSON")
    review_onboarding.add_argument("--decisions", required=True, help="explicit reviewer selection JSON")
    review_onboarding.add_argument("--output", default="", help="write review-bound bounded investigation config")
    live_investigation = commands.add_parser("investigate-mcp")
    live_investigation.add_argument("--proposal", required=True, help="the proposal used to materialize the reviewed config")
    live_investigation.add_argument("--approved-config", required=True, help="review-bound P2 investigation config")
    live_investigation.add_argument("--transport", required=True, help="authorized local MCP transport JSON")
    live_investigation.add_argument("--scope", default="", help="optional exact target/cohort/exposure JSON")
    live_investigation.add_argument("--output", default="", help="write the reproducible evidence envelope")
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--tables", type=int, default=13000)
    catalog.add_argument("--output", default="")
    analysis = commands.add_parser("analyze")
    analysis.add_argument("input", help="bounded investigation JSON snapshot")
    analysis.add_argument("--output", default="", help="write evidence envelope under this path")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.command == "serve":
        from fabintel.server import serve_local
        serve_local(args.host, args.port)
        return 0
    if args.command == "doctor":
        obj = {
            "state": "CANDIDATE", "external_transfer_ready": False,
            "internal_qualified": False, "product": json.loads((BASE / "product.json").read_text(encoding="utf8")),
            "readiness": _readiness_diagnostic(),
            "note": "Offline deterministic P2 candidate. Real MCP, target OS, security, license, and release gates remain separate.",
        }
    elif args.command == "preflight":
        obj = _preflight_report(_read_json(args.capabilities) if args.capabilities else None)
    elif args.command == "onboard":
        from fabintel.onboarding import propose_mappings
        capture = _read_json(args.descriptors)
        if _contains_credential_field(capture):
            raise ValueError("Descriptor capture must not contain credential material.")
        obj = propose_mappings(capture)
        if args.output:
            Path(args.output).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf8")
            print("WROTE non-authorizing onboarding proposal:", args.output, file=sys.stderr)
            return 0
    elif args.command == "onboard-live":
        from fabintel.onboarding_pipeline import propose_from_live_mcp_metadata
        source = _read_json(args.transport)
        transport = source.get("transport") if isinstance(source, dict) else None
        if not isinstance(transport, dict):
            raise ValueError("Transport file must contain one versioned transport object.")
        timeout = source.get("request_timeout_seconds", 10)
        max_bytes = source.get("max_response_bytes", 1048576)
        obj = asyncio.run(propose_from_live_mcp_metadata(
            transport, time_window={"start": args.start, "end": args.end},
            request_timeout_seconds=timeout, max_response_bytes=max_bytes,
        ))
        if args.output:
            Path(args.output).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf8")
            print("WROTE metadata-only onboarding proposal; no source rows read:", args.output, file=sys.stderr)
            return 0
    elif args.command == "onboard-review":
        from fabintel.onboarding_pipeline import materialize_live_review, verify_materialized_config
        report = _read_json(args.proposal)
        decisions = _read_json(args.decisions)
        obj = materialize_live_review(report, decisions)
        verify_materialized_config(obj, report["proposal"])
        if args.output:
            Path(args.output).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf8")
            print("WROTE review-bound plan; server authorization remains required:", args.output, file=sys.stderr)
            return 0
    elif args.command == "investigate-mcp":
        from fabintel.mcp_adapter import ConfiguredMCPAdapter
        from fabintel.mcp_workflow import investigate_with_mcp
        from fabintel.onboarding_pipeline import verify_materialized_config
        report, approved = _read_json(args.proposal), _read_json(args.approved_config)
        transport_record = _read_json(args.transport)
        transport = transport_record.get("transport") if isinstance(transport_record, dict) else None
        if not isinstance(transport, dict):
            raise ValueError("Transport file must contain one versioned transport object.")
        proposal = report.get("proposal") if isinstance(report, dict) else None
        verify_materialized_config(approved, proposal)
        scope = _read_json(args.scope) if args.scope else {}
        plan = approved["approved_plan"]
        source_ids = plan["source_ids"]
        refs = [{"source_id": source_id, "entity_type": "source", "entity_id": source_id}
                for source_id in source_ids]
        mcp_config = {
            "schema_version": "p2-mcp-client-config/v1", "transport": transport,
            "tools": approved["mcp_tools"],
            "request_timeout_seconds": transport_record.get("request_timeout_seconds", 10),
            "max_response_bytes": transport_record.get("max_response_bytes", 1048576),
        }
        async def run_investigation():
            async with ConfiguredMCPAdapter(mcp_config) as adapter:
                return await investigate_with_mcp(
                    adapter, plan, approved["permission_scope"], approved["limits"], refs,
                    target_wafer_ids=scope.get("target_wafer_ids"),
                    cohort=scope.get("cohort_wafer_ids"),
                    suspected_exposure=scope.get("suspected_exposure"),
                )
        obj = asyncio.run(run_investigation())
        validate_envelope(obj)
        if args.output:
            Path(args.output).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf8")
            print("WROTE MCP-backed evidence envelope:", args.output, file=sys.stderr)
            return 0
    elif args.command == "catalog":
        obj = {"catalog_version": "SYNTHETIC-1", "tables": synthetic_catalog(args.tables)}
        if args.output:
            Path(args.output).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf8")
            print("WROTE SYNTHETIC catalog:", args.output, file=sys.stderr)
            return 0
    elif args.command == "analyze":
        obj = analyze(_read_json(args.input))
        validate_envelope(obj)
        if args.output:
            Path(args.output).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf8")
            print("WROTE evidence envelope:", args.output, file=sys.stderr)
            return 0
    else:
        fixture = _read_json(str(BASE / "fixtures" / "case_positive.json"))
        obj = analyze(fixture)
        validate_envelope(obj)
    print(json.dumps(obj, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
