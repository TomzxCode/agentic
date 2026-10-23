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
from .agents.pool import pool
from .config import settings
from .db import create_db_and_tables, engine
from .debug import DebugMiddleware, recent_cli_calls, recent_requests
from .jobs import close_queue, get_queue, reconcile_runs
from .log_setup import configure_logging
from .provenance import ProvenanceMiddleware
from .request_logging import configure_request_logging
from .routers import (
    agent_runs,
    agent_streams,
    changes,
    decisions,
    events,
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
    my_pulls,
    operations,
    people,
    repositories,
    reviews,
    schedules,
    sessions,
    slack,
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
configure_logging()
configure_request_logging()


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


def _auto_record_changes_once() -> int:
    """Record changes for authored, task-linked merged PRs the store already holds.

    A merge an earlier process observed (or that predates this feature) would
    otherwise wait for its item's next refresh, leaving the metrics short of a
    change that already landed. Opens its own session, like the refresh pass.
    """
    from .auto_changes import record_merged_pr_changes

    with Session(engine) as session:
        return len(record_merged_pr_changes(session))


def _review_scan_once() -> dict:
    """Run the review scan when its cadence says it is due (gh blocks).

    Opens its own session so the ``gh`` calls never touch the event loop's
    connection. The scan records its own last pass, which is what the Settings
    page shows.
    """
    from .review_scan import run_due_review_scan

    with Session(engine) as session:
        return run_due_review_scan(session)


async def _review_scan_forever() -> None:
    """Tick on a timer and ask GitHub which pull requests await a review."""
    tick = settings.review_scan_tick
    if tick <= 0:
        return
    while True:
        await asyncio.sleep(tick)
        try:
            await asyncio.to_thread(_review_scan_once)
        except Exception as exc:  # noqa: BLE001
            log.warning("review scan tick failed", error=str(exc))


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
    # Record the merged pull requests already on file, so the metrics do not
    # wait for each item's next refresh.
    recorded = await asyncio.to_thread(_auto_record_changes_once)
    if recorded:
        log.info("recorded changes for merged pull requests at startup", count=recorded)
    # Re-fetch Slack/GitHub items on the configured schedule.
    refresh_task = asyncio.create_task(_refresh_due_forever())
    # Ask GitHub which pull requests await the user's review, on its own cadence.
    scan_task = asyncio.create_task(_review_scan_forever())
    # Fire the user-defined scheduled tasks whose time has come.
    schedule_task = asyncio.create_task(scheduler_loop())
    # Hold an ACP session for the default harness so the task view can list its
    # model choices without spawning it. Best effort: an unavailable harness
    # retries in the background and never delays startup.
    if settings.warm_harness_session:
        pool.start()
    log.info("agentic ready", data_dir=str(settings.data_dir))
    yield
    if settings.warm_harness_session:
        await pool.stop()
    refresh_task.cancel()
    scan_task.cancel()
    schedule_task.cancel()
    with suppress(asyncio.CancelledError):
        await refresh_task
    with suppress(asyncio.CancelledError):
        await scan_task
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

# Expose per-request timing and database query counts for the web UI debug bar.
app.add_middleware(DebugMiddleware)


@app.get("/api/debug/requests")
def debug_requests() -> list[dict]:
    return recent_requests()


@app.get("/api/debug/cli")
@app.get("/api/debug/cli-calls")
@app.get("/api/debug/cli_calls")
@app.get("/api/debug/rpc")
@app.get("/api/debug/rpc-calls")
@app.get("/api/debug/rpc_calls")
def debug_cli_calls() -> list[dict]:
    return recent_cli_calls()


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
    events,
    inbox,
    metrics,
    my_pulls,
    operations,
    settings_router,
    fs,
    github,
    gantt,
    graph,
    tags_router,
    people,
    slack,
    stack,
    reviews,
    feedback,
    decisions,
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
