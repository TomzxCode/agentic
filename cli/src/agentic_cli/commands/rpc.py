"""JSON-RPC commands for a running Agentic server."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from ..rpc_client import DEFAULT_RPC_URL, RpcClient, RpcError, RpcTransportError

rpc_app = App(name="rpc", help="Call a running Agentic server over JSON-RPC.")


def register(app: App) -> None:
    app.command(rpc_app)


MethodArg = Annotated[str, Parameter(help="JSON-RPC method to call, e.g. server.info.")]
ParamsJsonArg = Annotated[str | None, Parameter(help="JSON object of method parameters, or '-' / '@path'.")]
ParamsArg = Annotated[str | None, Parameter(name="--params", help="JSON object of method parameters.")]
ParamsFileArg = Annotated[Path | None, Parameter(name="--params-file", help="Read parameters from a file or stdin with '-'.")]
CompactArg = Annotated[bool, Parameter(name="--compact", help="Print the result as one compact JSON line.")]
UrlArg = Annotated[str | None, Parameter(name="--url", help="RPC endpoint URL.")]
TokenArg = Annotated[str | None, Parameter(name="--token", help="Bearer token.")]


def _load_params(raw_json, raw, params_file):
    supplied = [v for v in (raw_json, raw, params_file) if v is not None]
    if len(supplied) > 1:
        raise ValueError("use only one of the params argument, --params, or --params-file")
    if raw_json is not None:
        if raw_json == "-":
            text = sys.stdin.read()
        elif raw_json.startswith("@"):
            text = Path(raw_json[1:]).read_text()
        else:
            text = raw_json
    elif params_file is not None:
        text = sys.stdin.read() if str(params_file) == "-" else params_file.read_text()
    else:
        text = raw or ""
    if not text.strip():
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"parameters are not valid JSON: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("parameters must be a JSON object")
    return value


@rpc_app.command(name="call")
def call(
    method: MethodArg,
    params_json: ParamsJsonArg = None,
    *,
    params: ParamsArg = None,
    params_file: ParamsFileArg = None,
    url: UrlArg = None,
    token: TokenArg = None,
    compact: CompactArg = False,
) -> int:
    """Call a JSON-RPC method on a running Agentic server and print the result."""
    try:
        payload = _load_params(params_json, params, params_file)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    endpoint = url or os.environ.get("AGENTIC_RPC_URL") or DEFAULT_RPC_URL
    token = token or os.environ.get("AGENTIC_RPC_TOKEN") or None

    async def _run():
        async with RpcClient(endpoint, token=token) as client:
            try:
                result = await client.call(method, payload)
            except RpcError as exc:
                print(f"error: [{exc.code}] {exc.message}", file=sys.stderr)
                if exc.data is not None:
                    print(json.dumps(exc.data, ensure_ascii=False, indent=2), file=sys.stderr)
                return 1
            except RpcTransportError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=None if compact else 2) + "\n")
            return 0

    return asyncio.run(_run())


@rpc_app.command(name="methods")
def methods(
    *,
    url: UrlArg = None,
    token: TokenArg = None,
    json_output: Annotated[bool, Parameter(name="--json", help="Print catalog as JSON.")] = False,
) -> int:
    """List the methods a running Agentic server exposes."""
    endpoint = url or os.environ.get("AGENTIC_RPC_URL") or DEFAULT_RPC_URL
    token = token or os.environ.get("AGENTIC_RPC_TOKEN") or None

    async def _run():
        async with RpcClient(endpoint, token=token) as client:
            try:
                catalog = await client.methods()
            except RpcError as exc:
                print(f"error: [{exc.code}] {exc.message}", file=sys.stderr)
                return 1
            except RpcTransportError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
        if json_output:
            sys.stdout.write(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
            return 0
        if not catalog:
            sys.stdout.write("No methods exposed.\n")
            return 0
        rows = [(str(e.get("name", "?")), str(e.get("description") or "")) for e in catalog]
        width = max(len("METHOD"), *(len(n) for n, _ in rows))
        sys.stdout.write(f"{'METHOD':<{width}}  DESCRIPTION\n")
        for name, desc in rows:
            sys.stdout.write(f"{name:<{width}}  {desc}\n")
        return 0

    return asyncio.run(_run())


@rpc_app.command(name="exec")
def exec_command(
    *args: Annotated[str, Parameter(allow_leading_hyphen=True, help="Command and args to run on the server.")],
    url: UrlArg = None,
    token: TokenArg = None,
) -> int:
    """Run an agentic CLI command on the server and mirror its output."""
    endpoint = url or os.environ.get("AGENTIC_RPC_URL") or DEFAULT_RPC_URL
    token = token or os.environ.get("AGENTIC_RPC_TOKEN") or None

    async def _run():
        async with RpcClient(endpoint, token=token) as client:
            try:
                result = await client.exec(list(args))
            except RpcError as exc:
                print(f"error: [{exc.code}] {exc.message}", file=sys.stderr)
                return 1
            except RpcTransportError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        sys.stdout.write(stdout)
        if stderr:
            sys.stderr.write(stderr)
        return int(result.get("exitCode", 0))

    return asyncio.run(_run())