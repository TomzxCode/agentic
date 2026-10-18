"""Request provenance: the client and the actor behind each mutating request.

Every request may declare, through two headers, which client sent it (``web``,
``cli``, or ``api``) and whether a human or a coding agent is behind it. The
middleware keeps those values in a contextvar for the duration of the request so
handlers can stamp the records they write (the task timeline in particular), and
it writes each mutating ``/api`` request to the operations log.

The values come from the caller rather than being guessed: the web UI always
sends ``web``/``human``, and the CLI sends ``cli`` plus whatever actor its
environment declares, which the ACP runner sets to ``agent`` for a harness.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum

import structlog
from sqlmodel import Session

from .db import engine
from .models.base import OperationActor, OperationClient
from .models.system import Operation

log = structlog.get_logger(__name__)

CLIENT_HEADER = "x-agentic-client"
ACTOR_HEADER = "x-agentic-actor"

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_context: ContextVar[tuple[OperationClient, OperationActor]] = ContextVar(
    "agentic_provenance", default=(OperationClient.api, OperationActor.human)
)


def _coerce[E: StrEnum](enum: type[E], value: str | None, default: E) -> E:
    if not value:
        return default
    try:
        return enum(value.strip().lower())
    except ValueError:
        return default


def resolve(client: str | None, actor: str | None) -> tuple[OperationClient, OperationActor]:
    """Map declared header values to enums, falling back to api/human."""
    return (
        _coerce(OperationClient, client, OperationClient.api),
        _coerce(OperationActor, actor, OperationActor.human),
    )


def current() -> tuple[OperationClient, OperationActor]:
    return _context.get()


def current_client() -> OperationClient:
    return _context.get()[0]


def current_actor() -> OperationActor:
    return _context.get()[1]


@contextmanager
def using(client: OperationClient, actor: OperationActor) -> Generator[None]:
    token = _context.set((client, actor))
    try:
        yield
    finally:
        _context.reset(token)


def _record(method: str, path: str, status_code: int, client: OperationClient, actor: OperationActor) -> None:
    try:
        with Session(engine) as session:
            session.add(
                Operation(
                    method=method,
                    path=path,
                    status_code=status_code,
                    client=client,
                    actor=actor,
                )
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001 - provenance must never fail a request
        log.warning("could not record operation", path=path, error=str(exc))


class ProvenanceMiddleware:
    """Set the request's provenance context and log each mutating operation."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        client, actor = resolve(headers.get(CLIENT_HEADER), headers.get(ACTOR_HEADER))
        token = _context.set((client, actor))
        status = {"code": 0}

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _context.reset(token)

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        if method in MUTATING_METHODS and path.startswith("/api/"):
            _record(method, path, status["code"], client, actor)
