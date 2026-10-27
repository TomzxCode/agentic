"""JSON-RPC methods for the Agentic server.

Mirrors slackx's rpc/methods.py structure: a registry of methods, a dispatch
function, and handlers. The primary generic escape hatch is ``cli.run``, which
runs the ``agentic`` CLI on the server, so any operation available on the CLI
is reachable over JSON-RPC.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from .protocol import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    SERVER_ERROR,
    RpcError,
)

log = None  # keep import-light; populated lazily if needed

Handler = Callable[["RpcContext", dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class RpcContext:
    """Server-owned state every RPC method operates against."""

    api_base_url: str | None = None
    allow_exec: bool = True
    executable: str | None = None
    base_args: tuple[str, ...] = ()
    started_at: float = field(default_factory=time.time)
    app: Any = None

    @property
    def self_url(self) -> str:
        return (self.api_base_url or os.environ.get("AGENTIC_API_URL") or "http://127.0.0.1:8600").rstrip("/")


@dataclass(frozen=True)
class Method:
    name: str
    description: str
    params: tuple[str, ...]
    handler: Handler


_METHODS: dict[str, Method] = {}


def method(name: str, description: str, params: tuple[str, ...] = ()) -> Callable[[Handler], Handler]:
    def register(handler: Handler) -> Handler:
        _METHODS[name] = Method(name, description, params, handler)
        return handler

    return register


def list_methods(allow_exec: bool = True) -> list[dict[str, Any]]:
    entries = _METHODS.values()
    if not allow_exec:
        entries = [e for e in entries if e.name != "cli.run"]
    return [
        {"name": e.name, "description": e.description, "params": list(e.params)}
        for e in sorted(entries, key=lambda x: x.name)
    ]


def server_version() -> str:
    try:
        return version("agentic")
    except PackageNotFoundError:
        return "0.1.0"


async def dispatch(ctx: RpcContext, name: str, params: dict[str, Any]) -> Any:
    if name == "cli.run" and not ctx.allow_exec:
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {name}")
    entry = _METHODS.get(name)
    if entry is None:
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {name}")
    try:
        return await entry.handler(ctx, params)
    except RpcError:
        raise
    except SystemExit as exc:
        raise RpcError(SERVER_ERROR, str(exc) or "command aborted") from exc
    except Exception as exc:  # noqa: BLE001
        raise RpcError(SERVER_ERROR, f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_params(params: dict[str, Any], allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(params) - set(allowed))
    if unknown:
        raise RpcError(
            INVALID_PARAMS,
            f"unknown parameter(s): {', '.join(unknown)}",
            {"allowed": list(allowed)},
        )


def _str_param(params, name, *, required=False, default=None, nullable=False):
    if name not in params:
        if required:
            raise RpcError(INVALID_PARAMS, f"missing required parameter: {name}")
        return default
    value = params[name]
    if value is None:
        if nullable:
            return None
        if required:
            raise RpcError(INVALID_PARAMS, f"missing required parameter: {name}")
        return default
    if not isinstance(value, str):
        raise RpcError(INVALID_PARAMS, f"parameter {name} must be a string")
    return value


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------


@method("rpc.discover", "List the JSON-RPC methods this server exposes.")
async def _rpc_discover(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ())
    return {
        "name": "agentic",
        "version": server_version(),
        "methods": list_methods(ctx.allow_exec),
    }


@method("system.methods", "List the JSON-RPC methods this server exposes.")
async def _system_methods(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ())
    return {"methods": list_methods(ctx.allow_exec)}


@method("server.info", "Report the server version and method count.")
async def _server_info(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ())
    return {
        "name": "agentic",
        "version": server_version(),
        "apiBaseUrl": ctx.self_url,
        "execEnabled": ctx.allow_exec,
        "methods": len(list_methods(ctx.allow_exec)),
        "startedAt": datetime.fromtimestamp(ctx.started_at, UTC).isoformat(),
    }


@method("cli.run", "Run an agentic CLI command on the server and return its output and exit code.", ("args", "stdin"))
async def _cli_run(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("args", "stdin"))
    args = params.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(i, str) for i in args):
        raise RpcError(INVALID_PARAMS, "args must be a non-empty array of strings")
    stdin = params.get("stdin", "")
    if stdin is None:
        stdin = ""
    if not isinstance(stdin, str):
        raise RpcError(INVALID_PARAMS, "stdin must be a string")

    # Ensure the child talks to this server. Append trailing flags only when
    # the command is not itself an rpc subcommand.
    base_args = () if (args and args[0] == "rpc") else ctx.base_args
    # Inject api-url so the CLI reaches this server even on a non-default port.
    extra = []
    if ctx.self_url and "--api-url" not in args and "api_url" not in " ".join(args):
        extra = ["--api-url", ctx.self_url]
    command = [ctx.executable or "agentic", *args, *extra, *base_args]
    # If executable is python module fallback
    if ctx.executable is None and not _on_path("agentic"):
        command = [sys.executable, "-m", "agentic_cli", *args, *extra, *base_args]

    process = await asyncio.to_thread(
        subprocess.run,
        command,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )
    return {
        "stdout": process.stdout,
        "stderr": process.stderr,
        "exitCode": process.returncode,
    }


def _on_path(name: str) -> bool:
    import shutil

    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# In-process REST proxy (fully in-process fulfillment, no subprocess/network)
# ---------------------------------------------------------------------------


@method(
    "api.request",
    "Call an Agentic REST endpoint in-process and return its response.",
    ("method", "path", "query", "body", "headers"),
)
async def _api_request(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("method", "path", "query", "body", "headers"))
    if ctx.app is None:
        raise RpcError(SERVER_ERROR, "no app bound to this RPC context")

    import httpx
    from httpx import ASGITransport

    http_method = _str_param(params, "method", default="GET")
    assert http_method is not None
    http_method = http_method.upper()
    path = _str_param(params, "path", required=True)
    assert path is not None
    if not path.startswith("/"):
        path = "/" + path

    query = params.get("query", {})
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise RpcError(INVALID_PARAMS, "query must be a JSON object")
    body = params.get("body")
    headers = params.get("headers", {})
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        raise RpcError(INVALID_PARAMS, "headers must be a JSON object")

    transport = ASGITransport(app=ctx.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentic") as client:
        response = await client.request(
            http_method,
            path,
            params=query,
            json=body if body is not None and not isinstance(body, str) else None,
            content=body if isinstance(body, str) else None,
            headers={str(k): str(v) for k, v in headers.items()},
        )

    try:
        parsed = response.json()
    except Exception:  # noqa: BLE001
        parsed = response.text
    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": parsed,
    }


@method("http.request", "Alias for api.request.")
async def _http_request(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    return await _api_request(ctx, params)
