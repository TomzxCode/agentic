"""Send Uvicorn access records through the application's structlog logger.

The access line carries only the method, the path, and the status, so a failed
request leaves "400" in the logs with no reason. ``RequestErrorMiddleware`` adds
a second line for a failed response with the ``detail`` the API answered with,
which is where every handler puts its explanation. The same middleware times the
request so the access line itself carries how long it took. At debug level the
request's timings follow as separate ``request phase``, ``request db``, and
``request tools`` lines, so the access line stays short and the detail says what
took the time.
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .debug import log_breakdown
from .log_setup import debug_enabled

log = structlog.get_logger(__name__)

# Start of the request being served, so the access line (which Uvicorn writes
# while the response starts) can report the duration. It stays set until the
# middleware returns, and the handler skips it when a record comes from
# somewhere other than a request.
_request_started: ContextVar[float | None] = ContextVar("agentic_request_started", default=None)

# An error body is a JSON envelope with a short detail; anything larger is not
# one of ours, so stop buffering rather than hold a whole payload to parse.
_MAX_ERROR_BODY = 8 * 1024
# A detail can embed a tool's output; keep the log line one readable line.
_MAX_DETAIL = 500


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def _log_breakdown() -> None:
    """Log the request's timings as separate debug lines, when debug is on."""
    if not debug_enabled():
        return
    # A logging handler must never fail the response it is describing.
    try:
        log_breakdown()
    except Exception as exc:  # noqa: BLE001
        log.warning("request breakdown failed", error=str(exc))


class AccessLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        started = _request_started.get()
        if started is None:
            log.info(record.getMessage())
            return
        log.info(record.getMessage(), duration_ms=_elapsed_ms(started))
        _log_breakdown()


def _detail_text(payload: Any) -> str | None:
    """Read the human reason out of an API error body."""
    if not isinstance(payload, dict):
        return None
    detail = payload.get("detail")
    if isinstance(detail, str):
        return " ".join(detail.split()) or None
    if not isinstance(detail, list):
        return None
    # FastAPI's request-validation errors: [{"loc": [...], "msg": "..."}].
    parts = []
    for item in detail:
        if isinstance(item, dict):
            location = ".".join(str(part) for part in item.get("loc", ()))
            message = " ".join(str(item.get("msg") or "").split())
            parts.append(f"{location}: {message}" if location else message)
        else:
            parts.append(" ".join(str(item).split()))
    return "; ".join(part for part in parts if part) or None


def _response_detail(body: bytes) -> str | None:
    if not body:
        return None
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        return None
    detail = _detail_text(payload)
    if detail is None:
        return None
    return detail[:_MAX_DETAIL] + ("..." if len(detail) > _MAX_DETAIL else "")


class RequestErrorMiddleware:
    """Log the reason behind a failed request, which the access line omits.

    The response body is passed through untouched; it is only read, and only
    when the status says the request failed.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        token = _request_started.set(started)
        status = 0
        chunks: list[bytes] = []
        size = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status, size
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and status >= 400 and size < _MAX_ERROR_BODY:
                body = message.get("body", b"")
                chunks.append(body)
                size += len(body)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_started.reset(token)

        if status < 400:
            return
        detail = _response_detail(b"".join(chunks))
        fields: dict[str, Any] = {
            "method": scope.get("method", "GET"),
            "path": scope.get("path", ""),
            "status": status,
            "duration_ms": _elapsed_ms(started),
        }
        if detail:
            fields["detail"] = detail
        if status >= 500:
            log.error("request failed", **fields)
        else:
            log.warning("request failed", **fields)


def configure_request_logging() -> None:
    """Replace Uvicorn's formatter in each server process, including reloads."""
    logger = logging.getLogger("uvicorn.access")
    logger.handlers = [AccessLogHandler()]
    logger.propagate = False
