"""JSON-RPC 2.0 HTTP endpoint for the Agentic server.

The endpoint lives at POST /rpc on the app built by agentic.main. It accepts
a single request object or a batch, supports notifications, and always answers
request-level failures with a JSON-RPC error object and HTTP 200.
"""

from __future__ import annotations

import hmac
import json
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .methods import RpcContext, dispatch
from .protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    RpcError,
    error_response,
    parse_request,
    success_response,
)

RPC_PATH = "/rpc"


async def _handle_one(ctx: RpcContext, payload: Any) -> dict[str, Any] | None:
    try:
        request = parse_request(payload)
    except RpcError as exc:
        return error_response(None, exc.code, exc.message, exc.data)

    try:
        result = await dispatch(ctx, request.method, request.params)
    except RpcError as exc:
        if request.is_notification:
            return None
        return error_response(request.id, exc.code, exc.message, exc.data)

    if request.is_notification:
        return None
    return success_response(request.id, result)


def _authorized(request: Request, token: str) -> bool:
    header = request.headers.get("authorization", "")
    supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not supplied:
        supplied = request.headers.get("x-agentic-token", "").strip()
    return hmac.compare_digest(supplied, token)


def add_rpc_routes(
    fastapp: FastAPI,
    *,
    api_base_url: str | None = None,
    token: str | None = None,
    allow_exec: bool = True,
    executable: str | None = None,
    base_args: tuple[str, ...] = (),
) -> None:
    """Register the JSON-RPC endpoint on ``fastapp``."""
    ctx = RpcContext(
        api_base_url=api_base_url,
        allow_exec=allow_exec,
        executable=executable,
        base_args=base_args,
        app=fastapp,
    )

    @fastapp.post(RPC_PATH, include_in_schema=False)
    async def json_rpc(request: Request) -> Response:
        if token and not _authorized(request, token):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="agentic"'},
            )
        try:
            payload = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(error_response(None, PARSE_ERROR, "Parse error"))

        if isinstance(payload, list):
            if not payload:
                return JSONResponse(error_response(None, INVALID_REQUEST, "Invalid Request", "Empty batch"))
            responses = []
            for item in payload:
                response = await _handle_one(ctx, item)
                if response is not None:
                    responses.append(response)
            if not responses:
                return Response(status_code=204)
            return JSONResponse(responses)

        response = await _handle_one(ctx, payload)
        if response is None:
            return Response(status_code=204)
        return JSONResponse(response)
