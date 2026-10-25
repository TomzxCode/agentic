"""Async JSON-RPC client for a running Agentic server."""

from __future__ import annotations

import itertools
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def endpoint_url(url: str) -> str:
    raw = url.strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    parts = urlsplit(raw)
    path = parts.path or "/rpc"
    if path == "/":
        path = "/rpc"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


DEFAULT_RPC_URL = "http://127.0.0.1:8600/rpc"


class RpcTransportError(RuntimeError):
    pass


class RpcClient:
    def __init__(self, url, *, token=None, timeout=60.0, client=None):
        self.url = endpoint_url(url)
        self.token = token
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._ids = itertools.count(1)

    async def call(self, method, params=None):
        request = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {}}
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        try:
            response = await self._client.post(self.url, json=request, headers=headers)
        except httpx.HTTPError as exc:
            raise RpcTransportError(f"could not reach {self.url}: {exc}") from exc
        if response.status_code == 401:
            raise RpcTransportError(f"server at {self.url} rejected the token (HTTP 401)")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RpcTransportError(f"server at {self.url} returned HTTP {response.status_code}: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise RpcTransportError(f"server at {self.url} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RpcTransportError(f"server at {self.url} returned an unexpected payload")
        error = payload.get("error")
        if isinstance(error, dict):
            raise RpcError(int(error.get("code", -32603)), str(error.get("message", "JSON-RPC error")), error.get("data"))
        if "result" not in payload:
            raise RpcTransportError(f"server at {self.url} returned no result")
        return payload["result"]

    async def methods(self):
        result = await self.call("rpc.discover")
        return list(result.get("methods", []))

    async def exec(self, args, stdin=""):
        return await self.call("cli.run", {"args": args, "stdin": stdin})

    async def aclose(self):
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.aclose()