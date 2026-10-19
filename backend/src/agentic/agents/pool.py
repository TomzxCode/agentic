"""A warm ACP session for the default harness, held by the API process.

The SPA asks a harness which models it offers before it starts a run, and that
list lives only on a live ACP session. Rather than spawn a harness per request,
the API keeps one session open for the default harness from startup, so the
model picker answers in a single request. Runs are untouched: the worker still
spawns its own session per run, so a run survives an API restart.

Everything here is best effort. An unavailable harness, a spawn that fails, or a
process that dies leaves the pool empty and retries with backoff; the server
starts either way and the panel falls back to an empty, refreshable list.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from acp import spawn_agent_process
from sqlmodel import Session

from ..config import settings
from ..db import engine
from ..models.agents import Harness
from .client import AgenticClient
from .harnesses import get_harness
from .runner import harness_env, initialize, session_model, session_model_choices

log = structlog.get_logger(__name__)

# While the held session is good, the loop only re-reads the default harness and
# compares it to what it holds, so a change made in Settings is picked up within
# this many seconds even when nothing wakes the loop.
IDLE_POLL = 15.0
INITIAL_BACKOFF = 5.0
MAX_BACKOFF = 300.0
# How long the choices read from a harness the pool does not hold are reused.
ON_DEMAND_TTL = 600.0

Spawn = Callable[..., Any]


async def _drain(event: dict[str, Any]) -> None:
    """The held session publishes nothing; accept and drop its updates."""
    return None


@dataclass
class HarnessModels:
    """The model choices a harness reports, and where the answer came from."""

    harness_id: str
    choices: list[dict[str, str]] = field(default_factory=list)
    current: str | None = None
    # True when a session held open by this process answered.
    live: bool = False
    error: str | None = None


def fingerprint(harness: Harness) -> str:
    """What a held session was opened for, so a changed harness is reopened.

    The default harness changing is the id; its command, args, env or configured
    model changing also makes a held session stale, because the session was built
    from the old values.
    """
    return "|".join(
        [
            harness.id,
            harness.command,
            ",".join(harness.args or []),
            harness.model or "",
            ",".join(f"{k}={v}" for k, v in sorted((harness.env or {}).items())),
        ]
    )


class WarmSession:
    """One harness process with a live ACP session, held open for introspection."""

    def __init__(self, harness: Harness, cwd: str, *, spawn: Spawn | None = None) -> None:
        self.harness_id = harness.id
        self.fingerprint = fingerprint(harness)
        self.cwd = cwd
        self.choices: list[dict[str, str]] = []
        self.current: str | None = None
        self.session_id: str | None = None
        self._command = harness.command
        self._args = list(harness.args or [])
        self._env = harness_env(harness)
        self._spawn = spawn or spawn_agent_process
        self._stack = AsyncExitStack()
        self._process: Any = None

    @property
    def alive(self) -> bool:
        return self._process is not None and getattr(self._process, "returncode", None) is None

    async def open(self) -> None:
        """Spawn the harness, handshake, and open a session to read its models."""
        # A harness spawns in this directory, so it has to exist (a run resolves
        # the same root and creates it the same way).
        Path(self.cwd).mkdir(parents=True, exist_ok=True)
        client = AgenticClient(cwd=self.cwd, publish=_drain, auto_approve=settings.auto_approve_permissions)
        conn, process = await self._stack.enter_async_context(
            self._spawn(client, self._command, *self._args, env=self._env, cwd=self.cwd)
        )
        self._process = process
        await initialize(conn)
        session = await conn.new_session(cwd=self.cwd)
        self.session_id = session.session_id
        self.choices = session_model_choices(session)
        self.current = session_model(session)

    async def close(self) -> None:
        self._process = None
        with contextlib.suppress(Exception):
            await self._stack.aclose()


def _default_harness() -> Harness | None:
    """The harness a run with no harness of its own uses, read from the database."""
    with Session(engine) as session:
        try:
            return get_harness(session, None)
        except RuntimeError:
            return None


class HarnessSessionPool:
    """Holds one warm ACP session for the default harness.

    ``models`` answers from the held session when it is the one asked for, and
    otherwise opens a short-lived session on demand (cached briefly), so a
    non-default harness still lists its models without being pooled forever.
    """

    def __init__(self, *, spawn: Spawn | None = None) -> None:
        self._spawn = spawn
        self._session: WarmSession | None = None
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._stopping = False
        # The harness the loop is holding (or trying to hold), and why it is not
        # up, so the panel can say so without retrying a broken harness per load.
        self._wanted_id: str | None = None
        self._error: str | None = None
        # On-demand results, keyed by harness id: (fingerprint, read-at, models).
        self._cache: dict[str, tuple[str, float, HarnessModels]] = {}

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        """Hold a session for the default harness, in the background."""
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._maintain())

    async def stop(self) -> None:
        """Close the held session and stop the background loop."""
        self._stopping = True
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._drop()

    def refresh(self) -> None:
        """Reconsider the default harness now (a harness was changed)."""
        self._wake.set()

    # --- lookups ----------------------------------------------------------
    async def models(self, harness: Harness) -> HarnessModels:
        """The model choices a harness reports."""
        session = self._session
        if session is not None and session.harness_id == harness.id:
            if session.alive:
                return HarnessModels(harness.id, session.choices, session.current, live=True)
            return HarnessModels(harness.id, live=False, error="the harness session is not running")
        if harness.id == self._wanted_id:
            # The loop holds this harness and currently has no session for it.
            return HarnessModels(harness.id, live=False, error=self._error or "the session is not up yet")
        return await self._models_on_demand(harness)

    async def _models_on_demand(self, harness: Harness) -> HarnessModels:
        now = time.monotonic()
        cached = self._cache.get(harness.id)
        if cached is not None and cached[0] == fingerprint(harness) and now - cached[1] < ON_DEMAND_TTL:
            return cached[2]
        session = WarmSession(harness, str(settings.worktree_root), spawn=self._spawn)
        try:
            await session.open()
            models = HarnessModels(harness.id, session.choices, session.current, live=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a harness that will not start is not an API error
            log.warning("could not read a harness's models", harness_id=harness.id, error=str(exc))
            return HarnessModels(harness.id, live=False, error=str(exc))
        finally:
            await session.close()
        # Only a successful read is cached; a failure retries on the next request.
        self._cache[harness.id] = (fingerprint(harness), now, models)
        return models

    # --- the background loop ---------------------------------------------
    async def _maintain(self) -> None:
        backoff = INITIAL_BACKOFF
        while not self._stopping:
            harness = _default_harness()
            if harness is None:
                await self._idle(IDLE_POLL)
                continue
            self._wanted_id = harness.id
            session = self._session
            if (
                session is not None
                and session.harness_id == harness.id
                and session.fingerprint == fingerprint(harness)
                and session.alive
            ):
                await self._idle(IDLE_POLL)
                continue
            try:
                await self._open(harness)
                backoff = INITIAL_BACKOFF
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - retry, never crash the server
                log.warning("could not keep a warm harness session", harness_id=harness.id, error=str(exc))
                await self._drop()
                self._error = str(exc)
                await self._idle(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    async def _open(self, harness: Harness) -> None:
        session = WarmSession(harness, str(settings.worktree_root), spawn=self._spawn)
        try:
            await session.open()
        except BaseException:
            # A cancelled or failed open still spawns a process, so close it
            # rather than leaving it behind.
            await session.close()
            raise
        await self._drop()
        self._session = session
        self._error = None
        log.info("warm harness session up", harness_id=harness.id, models=len(session.choices))

    async def _drop(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            await session.close()

    async def _idle(self, seconds: float) -> None:
        """Sleep, waking early when something asks the pool to reconsider."""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
        self._wake.clear()


# The process-wide pool, started and stopped by the API's lifespan.
pool = HarnessSessionPool()


__all__ = ["HarnessModels", "HarnessSessionPool", "WarmSession", "fingerprint", "pool"]
