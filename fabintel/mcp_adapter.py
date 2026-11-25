"""Configurable read-only MCP adapter for the frozen P2 logical operations.

The adapter uses the official MCP Python SDK for wire protocol and transport.
It validates logical-operation responses, but server-side authorization and
bounded query enforcement remain mandatory and authoritative.
"""
from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse
import uuid


LOGICAL_OPERATIONS = (
    "discover", "semantics", "relationships", "read_bounded", "cancel", "audit",
)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class MCPAdapterError(RuntimeError):
    """Base error for protocol and logical-contract failures."""


class MCPConfigurationError(MCPAdapterError):
    """The local MCP client configuration is invalid or unsafe."""


class MCPContractError(MCPAdapterError):
    """A remote response did not satisfy the frozen logical contract."""


class MCPPermissionDenied(MCPAdapterError):
    """The remote service denied this read-only request."""


class MCPUnsupported(MCPAdapterError):
    """A required logical operation is unavailable or unsafe."""


class MCPReadCancelled(MCPAdapterError):
    """The remote service confirmed that a bounded read was cancelled."""


def _finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise MCPContractError(f"{label} must be a timezone-aware timestamp.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MCPContractError(f"{label} is not a valid ISO-8601 timestamp.") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise MCPContractError(f"{label} has no timezone; the time scope is ambiguous.")
    return result.astimezone(timezone.utc)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MCPContractError(f"{label} must be a structured object.")
    return value


def _strings(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise MCPContractError(f"{label} must be a list of non-empty strings.")
    if not allow_empty and not value:
        raise MCPContractError(f"{label} must not be empty.")
    return value


def _config(config: Any) -> dict[str, Any]:
    config = _object(config, "MCP configuration")
    required = {"schema_version", "transport", "tools", "request_timeout_seconds", "max_response_bytes"}
    if set(config) != required or config.get("schema_version") != "p2-mcp-client-config/v1":
        raise MCPConfigurationError("MCP config must match p2-mcp-client-config/v1 exactly.")
    timeout = config.get("request_timeout_seconds")
    response_bytes = config.get("max_response_bytes")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 300:
        raise MCPConfigurationError("request_timeout_seconds must be between 0 and 300.")
    if not isinstance(response_bytes, int) or isinstance(response_bytes, bool) or not 1024 <= response_bytes <= 104857600:
        raise MCPConfigurationError("max_response_bytes must be between 1 KiB and 100 MiB.")
    transport = _object(config.get("transport"), "transport")
    kind = transport.get("kind")
    if kind == "stdio":
        if set(transport) - {"kind", "command", "args", "cwd", "environment"}:
            raise MCPConfigurationError("stdio transport has unsupported fields.")
        if not isinstance(transport.get("command"), str) or not transport["command"]:
            raise MCPConfigurationError("stdio command must be an executable path or command name.")
        args = transport.get("args", [])
        if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise MCPConfigurationError("stdio args must be a list of strings; shell text is not accepted.")
        if transport.get("cwd") is not None and not isinstance(transport.get("cwd"), str):
            raise MCPConfigurationError("stdio cwd must be a string when supplied.")
        environment = transport.get("environment", {})
        if not isinstance(environment, dict):
            raise MCPConfigurationError("stdio environment must map child names to parent variable names.")
        if any(not _ENV_NAME.fullmatch(key) or not isinstance(value, str) or not _ENV_NAME.fullmatch(value)
               for key, value in environment.items()):
            raise MCPConfigurationError("stdio environment mappings must use environment variable names.")
    elif kind == "streamable_http":
        if set(transport) - {"kind", "url", "headers_from_environment"}:
            raise MCPConfigurationError("Streamable HTTP transport has unsupported fields.")
        parsed = urlparse(transport.get("url", ""))
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise MCPConfigurationError("Streamable HTTP URL must be an absolute origin URL without embedded credentials or fragments.")
        if parsed.scheme != "https" and not loopback:
            raise MCPConfigurationError("Remote Streamable HTTP requires HTTPS; plain HTTP is allowed only on loopback.")
        headers = transport.get("headers_from_environment", {})
        if not isinstance(headers, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not _ENV_NAME.fullmatch(v)
                                                for k, v in headers.items()):
            raise MCPConfigurationError("HTTP headers must map names to environment variable names.")
    else:
        raise MCPConfigurationError("transport.kind must be stdio or streamable_http.")
    tools = _object(config.get("tools"), "tools")
    if set(tools) != set(LOGICAL_OPERATIONS) or any(not isinstance(v, str) or not v for v in tools.values()):
        raise MCPConfigurationError("tools must map each frozen logical operation to one configured MCP tool name.")
    if len(set(tools.values())) != len(LOGICAL_OPERATIONS):
        raise MCPConfigurationError("Each logical operation must map to a distinct MCP tool.")
    return config


class ConfiguredMCPAdapter:
    """One MCP client session mapped to the six shared logical operations."""

    def __init__(self, config: dict[str, Any], *, environment: Mapping[str, str] | None = None):
        self.config = _config(config)
        self._environment = os.environ if environment is None else environment
        self._client: Any = None
        self._http_client: Any = None
        self._http_transport: AbstractAsyncContextManager | None = None
        self._tools: dict[str, Any] = {}
        self._discovery: dict[str, Any] | None = None
        self._semantics: dict[str, dict[str, Any]] = {}
        self._relationships: dict[str, dict[str, Any]] = {}
        self._active_operations: set[str] = set()
        self._reads: dict[str, dict[str, Any]] = {}
        self._skip_configured_tool_check = False

    @classmethod
    async def inspect_tool_descriptors(
        cls, transport: dict[str, Any], *, request_timeout_seconds: float = 10,
        max_response_bytes: int = 1048576, environment: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Use the official SDK to inspect permitted MCP tool metadata only.

        The bootstrap session cannot call tools: its names are placeholders and
        configured-tool validation is explicitly disabled for this session.
        It returns schemas and annotations without invoking a source operation.
        """
        config = {
            "schema_version": "p2-mcp-client-config/v1", "transport": transport,
            "tools": {name: f"__P2_DISCOVERY_ONLY_{name}__" for name in LOGICAL_OPERATIONS},
            "request_timeout_seconds": request_timeout_seconds,
            "max_response_bytes": max_response_bytes,
        }
        adapter = cls(config, environment=environment)
        adapter._skip_configured_tool_check = True
        async with adapter:
            descriptors = []
            for name, tool in sorted(adapter._tools.items()):
                schema = getattr(tool, "input_schema", None)
                if schema is None:
                    schema = getattr(tool, "inputSchema", None)
                if schema is None and hasattr(tool, "model_dump"):
                    dumped = tool.model_dump(by_alias=True)
                    schema = dumped.get("inputSchema", dumped.get("input_schema"))
                annotations = getattr(tool, "annotations", None)
                if hasattr(annotations, "model_dump"):
                    annotations = annotations.model_dump(by_alias=True)
                if not isinstance(annotations, dict):
                    annotations = {}
                descriptors.append({
                    "name": name,
                    "description": getattr(tool, "description", "") or "",
                    "inputSchema": schema if isinstance(schema, dict) else {},
                    "annotations": annotations,
                })
            return {
                "protocol_version": adapter.protocol_version,
                "tools": descriptors,
                "inspection": "OFFICIAL_SDK_METADATA_ONLY_NO_TOOL_CALLS",
            }

    @classmethod
    def from_file(cls, path: str | Path, *, environment: Mapping[str, str] | None = None):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MCPConfigurationError("Could not read a valid local MCP configuration file.") from exc
        return cls(data, environment=environment)

    async def __aenter__(self):
        try:
            from mcp import Client
            from mcp.client.stdio import StdioServerParameters
        except ImportError as exc:
            raise MCPConfigurationError("The pinned MCP SDK is optional and not installed; install the staged offline MCP extra first.") from exc

        transport = self.config["transport"]
        timeout = float(self.config["request_timeout_seconds"])
        if transport["kind"] == "stdio":
            child_env = {
                child: self._environment[parent]
                for child, parent in transport.get("environment", {}).items()
                if parent in self._environment
            }
            if len(child_env) != len(transport.get("environment", {})):
                raise MCPConfigurationError("A configured child environment source is missing from the current environment.")
            params = StdioServerParameters(
                command=transport["command"], args=transport.get("args", []),
                cwd=transport.get("cwd"), env=child_env or None,
            )
            self._client = Client(params, read_timeout_seconds=timeout)
        else:
            try:
                from httpx2 import AsyncClient as HTTPClient
                from mcp.client.streamable_http import streamable_http_client
            except ImportError as exc:
                raise MCPConfigurationError("The selected SDK bundle lacks Streamable HTTP dependencies.") from exc
            headers = {}
            for name, env_name in transport.get("headers_from_environment", {}).items():
                value = self._environment.get(env_name)
                if not value:
                    raise MCPConfigurationError(f"Configured HTTP credential environment variable {env_name} is empty or unavailable.")
                headers[name] = value
            self._http_client = HTTPClient(headers=headers, timeout=timeout, follow_redirects=False)
            self._http_transport = streamable_http_client(transport["url"], http_client=self._http_client)
            self._client = Client(self._http_transport, read_timeout_seconds=timeout)
        try:
            await self._client.__aenter__()
            protocol = getattr(self._client, "protocol_version", None)
            if not isinstance(protocol, str) or not protocol:
                raise MCPUnsupported("MCP client and server did not negotiate a protocol version.")
            listed = await self._client.list_tools()
            self._tools = {tool.name: tool for tool in listed.tools}
            configured_items = self.config["tools"].items() if not self._skip_configured_tool_check else ()
            for logical, configured_name in configured_items:
                tool = self._tools.get(configured_name)
                if tool is None:
                    raise MCPUnsupported(f"Configured logical operation {logical} is not advertised by the MCP server.")
                annotations = getattr(tool, "annotations", None)
                read_only = getattr(annotations, "read_only_hint", None)
                destructive = getattr(annotations, "destructive_hint", None)
                if isinstance(annotations, dict):
                    read_only = annotations.get("readOnlyHint")
                    destructive = annotations.get("destructiveHint")
                if read_only is not True or destructive is not False:
                    raise MCPUnsupported(f"Configured logical operation {logical} lacks explicit non-destructive read-only annotations.")
        except BaseException:
            await self._close()
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._close()

    async def _close(self):
        client, self._client = self._client, None
        http_client, self._http_client = self._http_client, None
        try:
            if client is not None:
                await client.__aexit__(None, None, None)
        finally:
            if http_client is not None:
                await http_client.aclose()

    def _require_open(self):
        if self._client is None:
            raise MCPConfigurationError("MCP adapter must be used inside an async context manager.")

    @property
    def protocol_version(self) -> str | None:
        """The protocol version negotiated by the current SDK session."""
        value = getattr(self._client, "protocol_version", None)
        return value if isinstance(value, str) else None

    async def _call(self, logical: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._require_open()
        tool_name = self.config["tools"][logical]
        try:
            result = await asyncio.wait_for(
                self._client.call_tool(tool_name, arguments),
                timeout=float(self.config["request_timeout_seconds"]),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise MCPAdapterError(f"The MCP server did not complete logical operation {logical}.") from exc
        if getattr(result, "is_error", False):
            text = " ".join(
                getattr(part, "text", "") for part in getattr(result, "content", [])
                if getattr(part, "type", None) == "text"
            )
            if text.strip().endswith("PERMISSION_DENIED"):
                raise MCPPermissionDenied(f"The MCP server denied logical operation {logical}.")
            if text.strip().endswith("REQUEST_CANCELLED"):
                raise MCPReadCancelled("The MCP server confirmed the read was cancelled.")
            raise MCPAdapterError(f"The MCP server rejected logical operation {logical}.")
        payload = getattr(result, "structured_content", None)
        if not isinstance(payload, dict):
            raise MCPContractError(f"Logical operation {logical} did not return structured content.")
        try:
            size = len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise MCPContractError(f"Logical operation {logical} returned non-JSON structured content.") from exc
        if size > self.config["max_response_bytes"]:
            raise MCPContractError(f"Logical operation {logical} exceeded the local response byte bound.")
        return payload

    async def discover(self) -> dict[str, Any]:
        payload = _object(await self._call("discover", {}), "discover response")
        for name in ("tool_versions", "semantic_versions", "limits", "auth_scopes", "audit_support", "capabilities"):
            if name not in payload:
                raise MCPContractError(f"discover response is missing {name}.")
        if (not isinstance(payload["tool_versions"], dict)
                or any(not isinstance(name, str) or not name or not isinstance(version, str) or not version
                       for name, version in payload["tool_versions"].items())
                or not isinstance(payload["semantic_versions"], list)
                or any(not isinstance(version, str) or not version for version in payload["semantic_versions"])):
            raise MCPContractError("discover tool or semantic versions are malformed.")
        if (not isinstance(payload["capabilities"], list)
                or any(not isinstance(name, str) or not name for name in payload["capabilities"])
                or not set(LOGICAL_OPERATIONS).issubset(set(payload["capabilities"]))):
            raise MCPUnsupported("MCP discovery does not advertise all six frozen logical operations.")
        if payload["audit_support"] is not True:
            raise MCPUnsupported("MCP discovery does not confirm audit support.")
        limits = _object(payload["limits"], "discover limits")
        for key in ("max_rows", "max_bytes", "max_seconds"):
            value = limits.get(key)
            if not _finite_number(value) or value <= 0:
                raise MCPContractError(f"discover limit {key} must be a positive number.")
        _strings(payload["auth_scopes"], "discover auth_scopes")
        self._discovery = payload
        return payload

    async def semantics(self, source_ids: list[str], semantic_version: str | None = None) -> dict[str, Any]:
        if self._discovery is None:
            raise MCPConfigurationError("Call discover before requesting semantics.")
        source_ids = sorted(set(_strings(source_ids, "source_ids")))
        if semantic_version is not None and (not isinstance(semantic_version, str) or not semantic_version):
            raise MCPContractError("semantic_version must be a non-empty string when supplied.")
        payload = _object(await self._call("semantics", {
            "source_ids": source_ids, "semantic_version": semantic_version,
        }), "semantics response")
        entries = payload.get("sources")
        if (not isinstance(entries, list)
                or any(not isinstance(item, dict) or not isinstance(item.get("source_id"), str) for item in entries)):
            raise MCPContractError("semantics response must define exactly the requested sources.")
        entry_ids = [item["source_id"] for item in entries]
        if len(entry_ids) != len(set(entry_ids)) or set(entry_ids) != set(source_ids):
            raise MCPContractError("semantics response must define exactly the requested sources.")
        for item in entries:
            if not isinstance(item, dict) or item.get("approved") is not True:
                raise MCPContractError("Source semantics are not approved for use.")
            if not isinstance(item.get("semantic_version"), str) or not item["semantic_version"]:
                raise MCPContractError("Source semantics have no version.")
            if semantic_version and item["semantic_version"] != semantic_version:
                raise MCPContractError("Source semantics version differs from the requested version.")
            if not isinstance(item.get("grain"), str) or not item["grain"]:
                raise MCPContractError("Source semantics have no row grain.")
            if not isinstance(item.get("column_definitions"), dict) or not isinstance(item.get("units"), dict):
                raise MCPContractError("Source semantics column or unit definitions are malformed.")
            effectivity = _object(item.get("effectivity"), "source effectivity")
            if _timestamp(effectivity.get("start"), "source effectivity start") >= _timestamp(effectivity.get("end"), "source effectivity end"):
                raise MCPContractError("Source effectivity interval is not positive.")
            if not isinstance(item.get("source_hash"), str) or not _HEX_64.fullmatch(item["source_hash"]):
                raise MCPContractError("Source semantics have no content hash.")
            self._semantics[item["source_id"]] = item
        return payload

    async def relationships(self, entity_refs: list[dict[str, Any]], time_window: dict[str, str]) -> dict[str, Any]:
        if self._discovery is None:
            raise MCPConfigurationError("Call discover before requesting relationships.")
        if not isinstance(entity_refs, list) or not entity_refs or any(not isinstance(ref, dict) for ref in entity_refs):
            raise MCPContractError("entity_refs must be a non-empty list of typed references.")
        window = _object(time_window, "relationship time window")
        start = _timestamp(window.get("start"), "relationship time window start")
        end = _timestamp(window.get("end"), "relationship time window end")
        if end <= start:
            raise MCPContractError("relationship time window must have positive duration.")
        payload = _object(await self._call("relationships", {"entity_refs": entity_refs, "time_window": time_window}), "relationships response")
        entries = payload.get("relationships")
        if not isinstance(entries, list):
            raise MCPContractError("relationships response must contain a relationships list.")
        response_ids = set()
        for relation in entries:
            if not isinstance(relation, dict) or not isinstance(relation.get("id"), str) or not relation["id"]:
                raise MCPContractError("Relationship response has an invalid relationship ID.")
            if relation["id"] in response_ids:
                raise MCPContractError("Relationship response contains a duplicate relationship ID.")
            response_ids.add(relation["id"])
            if relation.get("approved") is not True:
                continue
            source_ids = _strings(relation.get("source_ids"), "relationship source_ids")
            if any(source_id not in self._semantics for source_id in source_ids):
                raise MCPContractError("Approved relationship references source semantics that have not been verified by this client.")
            if not isinstance(relation.get("keys"), list) or not relation["keys"] or any(not isinstance(k, str) or not k for k in relation["keys"]):
                raise MCPContractError("Approved relationship has no declared join keys.")
            declared_keys = set().union(*(
                set(self._semantics[source_id]["column_definitions"])
                for source_id in source_ids
            ))
            if not set(relation["keys"]).issubset(declared_keys):
                raise MCPContractError("Approved relationship contains join keys absent from verified source semantics.")
            if not all(isinstance(relation.get(field), str) and relation[field] for field in ("cardinality", "grain")):
                raise MCPContractError("Approved relationship has no declared cardinality or grain.")
            rel_start = _timestamp(relation.get("effective_start"), "relationship effective_start")
            rel_end = _timestamp(relation.get("effective_end"), "relationship effective_end")
            if rel_end <= rel_start or rel_start > start or rel_end < end:
                raise MCPContractError("Approved relationship does not cover the requested time window.")
            if not isinstance(relation.get("source_reference"), dict):
                raise MCPContractError("Approved relationship has no source provenance reference.")
            source_ref = relation["source_reference"]
            if source_ref.get("source_ids") != source_ids:
                raise MCPContractError("Relationship source-reference IDs do not match its declared source IDs.")
            for source_id in source_ids:
                if (source_ref.get("source_hash") != self._semantics[source_id]["source_hash"]
                        or source_ref.get("semantic_version") != self._semantics[source_id]["semantic_version"]):
                    raise MCPContractError("Relationship provenance hash does not match verified source semantics.")
            self._relationships[relation["id"]] = relation
        return payload

    async def read_bounded(
        self,
        approved_plan: dict[str, Any],
        permission_context: str,
        limits: dict[str, Any],
        *,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        if self._discovery is None:
            raise MCPConfigurationError("Call discover before a bounded read.")
        plan = _object(approved_plan, "approved_plan")
        plan_sources = set(_strings(plan.get("source_ids"), "approved_plan source_ids"))
        plan_relationships = set(_strings(plan.get("relationship_ids"), "approved_plan relationship_ids"))
        window = _object(plan.get("time_window"), "approved_plan time_window")
        start = _timestamp(window.get("start"), "approved_plan time window start")
        end = _timestamp(window.get("end"), "approved_plan time window end")
        if end <= start:
            raise MCPContractError("approved_plan time window must have positive duration.")
        time_field = plan.get("time_field")
        if not isinstance(time_field, str) or not time_field:
            raise MCPContractError("approved_plan must identify its time field.")
        if not plan_sources.issubset(self._semantics):
            raise MCPContractError("Read plan contains source IDs without verified approved semantics.")
        for source_id in plan_sources:
            time_definition = self._semantics[source_id]["column_definitions"].get(time_field)
            if (not isinstance(time_definition, dict) or time_definition.get("type") != "timestamp"
                    or time_definition.get("timezone_required") is not True):
                raise MCPContractError(f"Read plan time field {time_field} is not defined as a timezone-aware timestamp by source semantics.")
        if not plan_relationships.issubset(self._relationships):
            raise MCPContractError("Read plan contains relationship IDs not returned by relationship discovery.")
        for rel_id in plan_relationships:
            relation = self._relationships[rel_id]
            if time_field not in relation["keys"]:
                raise MCPContractError(f"Read plan time field {time_field} is not authorized by relationship {rel_id}.")
            if relation.get("approved") is not True or not plan_sources.intersection(relation["source_ids"]):
                raise MCPContractError("Read plan does not match an approved source relationship.")
            rel_start = _timestamp(relation["effective_start"], "relationship effective_start")
            rel_end = _timestamp(relation["effective_end"], "relationship effective_end")
            if start < rel_start or end > rel_end:
                raise MCPContractError("Read plan time scope exceeds the approved relationship effectivity.")
        raw_filters = plan.get("filters", {})
        if not isinstance(raw_filters, dict):
            raise MCPContractError("Read plan filters must be an object of source-declared exact-match fields.")
        declared_filter_fields = set.intersection(*(
            set(self._relationships[rel_id]["keys"]) for rel_id in plan_relationships
        ))
        declared_columns = set.intersection(*(
            set(self._semantics[source_id]["column_definitions"]) for source_id in plan_sources
        ))
        filters = {}
        for field, raw_value in raw_filters.items():
            if field not in declared_filter_fields or field not in declared_columns:
                raise MCPContractError(f"Read plan filter {field} is not declared by every approved source relationship.")
            values = [raw_value] if isinstance(raw_value, str) else raw_value
            if (not isinstance(values, list) or not values
                    or any(not isinstance(value, str) or not value for value in values)
                    or len(values) != len(set(values))):
                raise MCPContractError(f"Read plan filter {field} must contain unique, non-empty exact-match values.")
            filters[field] = values
        if filters:
            plan["filters"] = filters
        if not isinstance(permission_context, str) or permission_context not in self._discovery["auth_scopes"]:
            raise MCPPermissionDenied("Requested permission context is not in the server-discovered scope.")
        limits = _object(limits, "read limits")
        server_limits = self._discovery["limits"]
        normalized_limits = {}
        for key in ("max_rows", "max_bytes", "max_seconds"):
            value = limits.get(key)
            if not _finite_number(value) or value <= 0 or value > server_limits[key]:
                raise MCPContractError(f"read limit {key} is invalid or exceeds the server-declared bound.")
            if key != "max_seconds" and not float(value).is_integer():
                raise MCPContractError(f"read limit {key} must be an integer.")
            normalized_limits[key] = int(value) if key != "max_seconds" else float(value)
        op_id = str(uuid.UUID(operation_id)) if operation_id else str(uuid.uuid4())
        self._active_operations.add(op_id)
        try:
            payload = _object(await self._call("read_bounded", {
                "approved_plan": plan,
                "permission_context": permission_context,
                "limits": normalized_limits,
                "operation_id": op_id,
            }), "read_bounded response")
        except MCPReadCancelled:
            raise
        finally:
            self._active_operations.discard(op_id)
        if payload.get("cancelled") is True:
            raise MCPReadCancelled("The MCP server confirmed the read was cancelled.")
        rows = payload.get("typed_rows")
        if not isinstance(rows, list) or len(rows) > normalized_limits["max_rows"]:
            raise MCPContractError("read_bounded returned malformed or over-limit typed rows.")
        returned_source_list = _strings(payload.get("source_ids"), "read_bounded source_ids", allow_empty=True)
        returned_relationship_list = _strings(payload.get("relationship_ids"), "read_bounded relationship_ids", allow_empty=True)
        returned_sources = set(returned_source_list)
        returned_relationships = set(returned_relationship_list)
        if len(returned_sources) != len(returned_source_list) or len(returned_relationships) != len(returned_relationship_list):
            raise MCPContractError("read_bounded source and relationship references must be unique.")
        if not returned_sources.issubset(plan_sources) or not returned_relationships.issubset(plan_relationships):
            raise MCPContractError("read_bounded returned a source or relationship outside the approved plan.")
        if not isinstance(payload.get("source_versions"), dict):
            raise MCPContractError("read_bounded has no source version map.")
        if not isinstance(payload.get("truncated"), bool):
            raise MCPContractError("read_bounded truncation status must be explicit.")
        if not isinstance(payload.get("audit_id"), str) or not payload["audit_id"]:
            raise MCPContractError("read_bounded has no server audit ID.")
        if payload.get("operation_id") != op_id:
            raise MCPContractError("read_bounded operation ID does not match the request.")
        if not isinstance(payload.get("query_hash"), str) or not _HEX_64.fullmatch(payload["query_hash"]):
            raise MCPContractError("read_bounded has no valid query hash.")
        expected_query_hash = operation_hash({
            "approved_plan": plan,
            "permission_context": permission_context,
            "limits": normalized_limits,
        })
        if payload["query_hash"] != expected_query_hash:
            raise MCPContractError("read_bounded query hash does not match the submitted bounded plan.")
        if payload.get("permission_scope") != permission_context:
            raise MCPContractError("read_bounded permission scope differs from the discovered request scope.")
        response_window = _object(payload.get("query_window"), "read_bounded query window")
        if (_timestamp(response_window.get("start"), "read_bounded query start") != start
                or _timestamp(response_window.get("end"), "read_bounded query end") != end):
            raise MCPContractError("read_bounded time window differs from the submitted query scope.")
        source_grains = {self._semantics[source_id]["grain"] for source_id in plan_sources}
        if len(source_grains) != 1:
            raise MCPContractError("A bounded read across different row grains must be split into separate reads.")
        expected_grain = next(iter(source_grains))
        if payload.get("row_grain") != expected_grain:
            raise MCPContractError("read_bounded declared a row grain that conflicts with verified semantics.")
        for row in rows:
            if not isinstance(row, dict):
                raise MCPContractError("read_bounded returned a non-object typed row.")
            source_id = row.get("source_id")
            relationship_id = row.get("relationship_id")
            if (not isinstance(source_id, str) or not isinstance(relationship_id, str)
                    or source_id not in plan_sources or relationship_id not in plan_relationships
                    or source_id not in returned_sources or relationship_id not in returned_relationships):
                raise MCPContractError("A returned row has no approved source/relationship in the read plan.")
            if row.get("grain") != expected_grain or row.get("source_version") != self._semantics[source_id]["semantic_version"]:
                raise MCPContractError("A returned row's grain or source version conflicts with verified semantics.")
            relation = self._relationships[relationship_id]
            missing_relation_keys = [key for key in relation["keys"] if key not in row]
            if source_id not in relation["source_ids"] or missing_relation_keys:
                raise MCPContractError(
                    "A returned row does not satisfy its source relationship keys: "
                    + ", ".join(missing_relation_keys[:8])
                )
            timestamp = _timestamp(row.get(time_field), f"row {time_field}")
            if not start <= timestamp < end:
                raise MCPContractError("A returned row falls outside the approved time window.")
        serialized_bytes = len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        if serialized_bytes > normalized_limits["max_bytes"]:
            raise MCPContractError("read_bounded response exceeds the server-enforced byte bound.")
        if set(payload["source_versions"]) != returned_sources:
            raise MCPContractError("read_bounded source version keys do not match the returned source IDs.")
        for source_id in returned_sources:
            if payload["source_versions"].get(source_id) != self._semantics[source_id]["semantic_version"]:
                raise MCPContractError("read_bounded source version differs from discovered semantics.")
        self._reads[op_id] = payload
        return payload

    async def cancel(self, operation_id: str) -> dict[str, Any]:
        try:
            operation_id = str(uuid.UUID(operation_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise MCPContractError("cancel requires a valid operation UUID.") from exc
        payload = _object(await self._call("cancel", {"operation_id": operation_id}), "cancel response")
        if not isinstance(payload.get("confirmed_stopped"), bool):
            raise MCPContractError("cancel response must explicitly report whether the server stopped the operation.")
        return payload

    async def audit(self, operation_id: str) -> dict[str, Any]:
        try:
            operation_id = str(uuid.UUID(operation_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise MCPContractError("audit requires a valid operation UUID.") from exc
        payload = _object(await self._call("audit", {"operation_id": operation_id}), "audit response")
        read = self._reads.get(operation_id)
        if read is None:
            raise MCPContractError("No completed bounded read is available to verify against this audit record.")
        if not isinstance(payload.get("permission_scope"), str) or payload["permission_scope"] != read["permission_scope"]:
            raise MCPContractError("Audit permission scope does not match the bounded read.")
        if not isinstance(payload.get("sources"), list):
            raise MCPContractError("Audit response has no source provenance list.")
        if any(not isinstance(item, dict) or not isinstance(item.get("source_id"), str) for item in payload["sources"]):
            raise MCPContractError("Audit source provenance contains a malformed entry.")
        source_ids = {item["source_id"] for item in payload["sources"]}
        if source_ids != set(read["source_ids"]) or len(source_ids) != len(payload["sources"]):
            raise MCPContractError("Audit source references do not match the bounded read.")
        for item in payload["sources"]:
            source = self._semantics.get(item["source_id"])
            if (source is None or item.get("semantic_version") != source["semantic_version"]
                    or item.get("source_hash") != source["source_hash"]):
                raise MCPContractError("Audit source semantic version or hash differs from verified source semantics.")
        if not isinstance(payload.get("timestamps"), dict):
            raise MCPContractError("Audit response has no time scope.")
        start = _timestamp(payload["timestamps"].get("start"), "audit time scope start")
        end = _timestamp(payload["timestamps"].get("end"), "audit time scope end")
        read_start = _timestamp(read["query_window"].get("start"), "read time scope start")
        read_end = _timestamp(read["query_window"].get("end"), "read time scope end")
        if (start, end) != (read_start, read_end):
            raise MCPContractError("Audit time scope differs from the bounded read.")
        if payload.get("query_hash") != read["query_hash"]:
            raise MCPContractError("Audit query hash differs from the bounded read.")
        return payload


def operation_hash(value: dict[str, Any]) -> str:
    """Canonical digest helper used by synthetic server and adapter fixtures."""
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
