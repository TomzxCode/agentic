"""Request-scoped debugging/profiling data, exposed like a tiny debug bar."""

from __future__ import annotations

import time
from contextvars import ContextVar, Token

from sqlalchemy import event

from .db import engine

# Mutable per-request state (a dict so worker threads mutate the same object).
_debug_state: ContextVar[dict | None] = ContextVar("agentic_debug_state", default=None)

_RECENT_LIMIT = 20
_recent_requests: list[dict] = []


def start_request() -> dict:
    state = {"count": 0, "time_ms": 0.0, "start": time.perf_counter(), "queries": []}
    _debug_state.set(state)
    return state


def record_query(statement: str, duration_ms: float) -> None:
    state = _debug_state.get()
    if state is not None:
        state["count"] += 1
        state["time_ms"] += duration_ms
        state["queries"].append({"sql": (statement or "").strip()[:300], "duration_ms": round(duration_ms, 2)})


def current_state() -> dict | None:
    return _debug_state.get()


def recent_requests() -> list[dict]:
    return list(reversed(_recent_requests))


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    if _debug_state.get() is None:
        return
    context._agentic_debug_start = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    start = getattr(context, "_agentic_debug_start", None)
    if start is None:
        return
    record_query(statement, (time.perf_counter() - start) * 1000.0)


class DebugMiddleware:
    """Attach per-request timing and database query counts as response headers."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        state = start_request()
        token: Token = _debug_state.set(state)
        response_started = {"done": False}
        method = scope.get("method", "GET")
        path = scope.get("path", "")

        async def send_wrapper(message) -> None:
            if message.get("type") == "http.response.start" and not response_started["done"]:
                response_started["done"] = True
                duration_ms = (time.perf_counter() - state["start"]) * 1000.0
                headers = list(message.get("headers", []))
                headers.append((b"x-debug-duration-ms", f"{duration_ms:.2f}".encode("latin-1")))
                headers.append((b"x-debug-db-queries", str(state["count"]).encode("latin-1")))
                headers.append((b"x-debug-db-time-ms", f"{state['time_ms']:.2f}".encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if not path.startswith("/api/debug"):
                duration_ms = (time.perf_counter() - state["start"]) * 1000.0
                entry = {
                    "method": method,
                    "path": path,
                    "duration_ms": round(duration_ms, 2),
                    "db_queries": state["count"],
                    "db_time_ms": round(state["time_ms"], 2),
                    "queries": list(state["queries"]),
                }
                _recent_requests.append(entry)
            if len(_recent_requests) > _RECENT_LIMIT:
                del _recent_requests[: len(_recent_requests) - _RECENT_LIMIT]
            _debug_state.reset(token)
