"""Live SSE streams for a run and for a task page.

The worker runs in another process, so its in-process event bus cannot reach
these streams; a stream replays persisted events and then polls the database
(and the local bus) for new ones.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, col, select
from sse_starlette.sse import EventSourceResponse

from ..crud import get_task_or_404
from ..db import engine, get_session
from ..events import bus
from ..models.agents import AgentEvent, AgentRun
from ..models.base import RunStatus
from ..models.tasks import Task, TimelineEvent

router = APIRouter(prefix="/api", tags=["agents"])


def _sse(event: dict) -> dict:
    # Always use the default event name so EventSource.onmessage fires client-side;
    # the real kind travels inside the JSON payload as `type`.
    return {"event": "message", "data": json.dumps(event)}


def _task_signature(session: Session, task_id: str) -> tuple:
    """A cheap value that changes when anything the task page shows changes.

    The worker runs in another process, so its in-process event bus cannot reach
    these streams; the signature lets a stream notice its writes by polling the DB.
    A single query (with scalar subqueries) keeps the polling cheap.
    """
    row = session.exec(
        select(
            Task.title,
            Task.summary,
            Task.updated_at,
            select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task_id).scalar_subquery(),
            select(func.group_concat(AgentRun.id + ":" + AgentRun.status))
            .where(AgentRun.task_id == task_id)
            .scalar_subquery(),
            select(func.max(TimelineEvent.created_at)).where(TimelineEvent.task_id == task_id).scalar_subquery(),
        ).where(Task.id == task_id)
    ).first()
    if row is None:
        return ("deleted",)
    title, summary, updated_at, run_count, runs_blob, last_event = row
    return (
        title,
        summary or "",
        updated_at.isoformat() if updated_at else "",
        run_count or 0,
        runs_blob or "",
        last_event.isoformat() if last_event else "",
    )


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> EventSourceResponse:
    async def generator() -> AsyncIterator[dict]:
        async with bus.subscribe(f"run:{run_id}") as queue:
            with Session(engine) as session:
                run = session.get(AgentRun, run_id)
                if run is None:
                    yield {"event": "message", "data": json.dumps({"type": "error", "error": "run not found"})}
                    return
                finished = run.status in (RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled)
                replay = list(
                    session.exec(
                        select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(col(AgentEvent.id))
                    ).all()
                )
            last_id = 0
            if replay and replay[-1].id is not None:
                last_id = replay[-1].id
            for row in replay:
                yield _sse({"seq": row.seq, "type": row.type, "text": row.text, "data": row.data_json})
            if finished:
                yield _sse({"type": "run_finished", "data": {"run_id": run_id}})
                return
            while True:
                # A run executed in this process publishes on the local bus.
                while True:
                    try:
                        event = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    yield _sse(event)
                    if event.get("type") == "run_finished":
                        return
                # A worker (another process) persists its events, so poll for them.
                with Session(engine) as session:
                    rows = list(
                        session.exec(
                            select(AgentEvent)
                            .where(AgentEvent.run_id == run_id, col(AgentEvent.id) > last_id)
                            .order_by(col(AgentEvent.id))
                        ).all()
                    )
                    run = session.get(AgentRun, run_id)
                    status = run.status if run is not None else RunStatus.failed
                for row in rows:
                    last_id = row.id or last_id
                    yield _sse({"seq": row.seq, "type": row.type, "text": row.text, "data": row.data_json})
                if status in (RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled):
                    yield _sse({"type": "run_finished", "data": {"run_id": run_id}})
                    return
                await asyncio.sleep(1)

    return EventSourceResponse(generator(), ping=15)


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str, session: Session = Depends(get_session)) -> EventSourceResponse:
    get_task_or_404(session, task_id)

    async def generator() -> AsyncIterator[dict]:
        async with bus.subscribe(f"task:{task_id}") as queue:
            last: tuple | None = None
            while True:
                # API-originated events arrive on the local bus; a worker's writes
                # are picked up by the signature poll below.
                while True:
                    try:
                        event = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    yield {"event": "message", "data": json.dumps(event)}
                with Session(engine) as s:
                    signature = _task_signature(s, task_id)
                if last is None:
                    last = signature
                elif signature != last:
                    last = signature
                    yield {"event": "message", "data": json.dumps({"kind": "task", "action": "updated"})}
                await asyncio.sleep(2)

    return EventSourceResponse(generator(), ping=15)
