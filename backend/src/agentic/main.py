"""FastAPI application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from saq.web.starlette import saq_web
from scalar_fastapi import Theme, add_scalar_reference
from sqlmodel import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from .agents.harnesses import seed_harnesses
from .config import settings
from .db import create_db_and_tables, engine
from .jobs import close_queue, get_queue, reconcile_runs
from .provenance import ProvenanceMiddleware
from .routers import (
    agent_runs,
    agent_streams,
    changes,
    feedback,
    fs,
    gantt,
    github,
    graph,
    groups,
    harnesses,
    inbox,
    items,
    metrics,
    operations,
    people,
    repositories,
    reviews,
    schedules,
    sessions,
    stack,
    task_dependencies,
    task_items,
    task_writes,
    tasks,
    worktrees,
)
from .routers import settings as settings_router
from .routers import tags as tags_router
from .schedules import reconcile_scheduled_runs, scheduler_loop

log = structlog.get_logger(__name__)


def _refresh_due_once() -> dict:
    """Run one pass of the refresh policy in a worker thread (slackx/ghx block).

    Opens its own session so the blocking fetches never touch the event loop's
    connection. ``refresh_due_items`` records each source's outcome, which is
    what the Settings page shows.
    """
    from .refresh import policies_from_settings
    from .routers.items import refresh_due_items
    from .settings_store import get_settings

    with Session(engine) as session:
        policies = policies_from_settings(get_settings(session))
        if not any(text.strip() for text in policies.values()):
            return {"refreshed": 0}
        return refresh_due_items(session, policies)


async def _refresh_due_forever() -> None:
    """Tick on a timer and refresh the items the policy says are due."""
    tick = settings.item_refresh_tick
    if tick <= 0:
        return
    while True:
        await asyncio.sleep(tick)
        try:
            result = await asyncio.to_thread(_refresh_due_once)
        except Exception as exc:  # noqa: BLE001
            log.warning("item refresh tick failed", error=str(exc))
            continue
        if result.get("refreshed"):
            log.info("refreshed due items", refreshed=result["refreshed"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    with Session(engine) as session:
        seed_harnesses(session)
    # Connect the run queue and fail any run left behind by a previous process.
    await get_queue()
    await reconcile_runs()
    # A scheduled run executes in this process, so any left running by a
    # previous process is gone.
    reconcile_scheduled_runs()
    # Re-fetch Slack/GitHub items on the configured schedule.
    refresh_task = asyncio.create_task(_refresh_due_forever())
    # Fire the user-defined scheduled tasks whose time has come.
    schedule_task = asyncio.create_task(scheduler_loop())
    log.info("agentic ready", data_dir=str(settings.data_dir))
    yield
    refresh_task.cancel()
    schedule_task.cancel()
    with suppress(asyncio.CancelledError):
        await refresh_task
    with suppress(asyncio.CancelledError):
        await schedule_task
    await close_queue()


app = FastAPI(title="Agentic", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)

# Render the OpenAPI reference with Scalar at /docs (Swagger UI and ReDoc are off).
add_scalar_reference(app, route="/docs", theme=Theme.SATURN, scalar_favicon_url="/icon.svg", telemetry=False)


@app.get("/redoc", include_in_schema=False)
def redoc_removed() -> None:
    """ReDoc is no longer served; the reference lives at /docs."""
    raise HTTPException(status_code=404, detail="ReDoc is not served; see /docs")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Records each mutating request (client + actor) and exposes the context to handlers.
app.add_middleware(ProvenanceMiddleware)

for module in (
    repositories,
    groups,
    items,
    tasks,
    task_items,
    task_dependencies,
    task_writes,
    worktrees,
    harnesses,
    agent_runs,
    agent_streams,
    sessions,
    changes,
    inbox,
    metrics,
    operations,
    settings_router,
    fs,
    github,
    gantt,
    graph,
    tags_router,
    people,
    stack,
    reviews,
    feedback,
    schedules,
):
    app.include_router(module.router)

# The task- and item-side people links are mounted at their natural paths.
app.include_router(people.link_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentic"}


class _LiveQueueRegistry:
    """Point the SAQ web UI at the process-wide queue before each request.

    ``saq_web`` captures the queues it is given in a module global, but the app
    builds its queue lazily (and the test suite rebuilds it per test), so the
    live queue is resolved per request rather than wired once at import.
    """

    def __init__(self, inner: ASGIApp) -> None:
        self._inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            from saq.web import starlette as saq_starlette

            queue = await get_queue()
            saq_starlette.QUEUES[queue.name] = queue
        await self._inner(scope, receive, send)


def _mount_saq_monitor() -> None:
    """Serve the SAQ run-queue monitor at /saq (a read/retry/abort view)."""

    # The Mount below only matches "/saq/..." (its regex is ^/saq/), so the bare
    # "/saq" would otherwise fall through to the SPA catch-all and render blank.
    @app.get("/saq", include_in_schema=False)
    def saq_redirect() -> RedirectResponse:
        return RedirectResponse(url="/saq/")

    app.mount("/saq", _LiveQueueRegistry(saq_web("/saq", queues=[])), name="saq")


def _mount_frontend() -> None:
    static_dir = settings.static_dir
    if not (static_dir / "index.html").exists():
        log.info("frontend build not found; API only", static_dir=str(static_dir))
        return
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    if (static_dir / "icons").is_dir():
        app.mount("/icons", StaticFiles(directory=static_dir / "icons"), name="icons")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(static_dir.resolve())):
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")


_mount_saq_monitor()
_mount_frontend()
