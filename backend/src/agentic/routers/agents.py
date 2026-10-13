"""Harnesses and agent runs, streamed to the SPA over SSE."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select
from sse_starlette.sse import EventSourceResponse

from ..agents import get_harness, harness_available, seed_harnesses
from ..config import settings
from ..crud import add_timeline, get_task_or_404
from ..db import engine, get_session
from ..events import bus
from ..jobs import cancel_run as cancel_queued_run
from ..jobs import enqueue_run
from ..links import run_read
from ..models import (
    AgentEvent,
    AgentRun,
    Association,
    Harness,
    Repository,
    RunStatus,
    SourceItem,
    Task,
    TaskRepository,
    TimelineEvent,
    Worktree,
    utcnow,
)
from ..schemas import (
    AgentEventRead,
    ContextPreview,
    HarnessCreate,
    HarnessRead,
    HarnessStatus,
    HarnessUpdate,
    RunCreate,
    RunRead,
)
from ..services import build_context_prompt, build_summary_prompt

router = APIRouter(prefix="/api", tags=["agents"])

# Runs are processed by SAQ workers (see `agentic.jobs`); the API only enqueues.


# --- harnesses ------------------------------------------------------------
@router.get("/harnesses", response_model=list[HarnessStatus])
def list_harnesses(session: Session = Depends(get_session)) -> list[HarnessStatus]:
    seed_harnesses(session)
    statuses: list[HarnessStatus] = []
    for harness in session.exec(select(Harness)).all():
        available, detail = harness_available(harness)
        statuses.append(
            HarnessStatus(
                id=harness.id,
                name=harness.name,
                available=available,
                detail=detail,
                is_default=harness.is_default,
                model=harness.model,
            )
        )
    return statuses


@router.get("/harnesses/full", response_model=list[HarnessRead])
def list_harnesses_full(session: Session = Depends(get_session)) -> list[Harness]:
    seed_harnesses(session)
    return list(session.exec(select(Harness)).all())


@router.post("/harnesses", response_model=HarnessRead, status_code=201)
def create_harness(payload: HarnessCreate, session: Session = Depends(get_session)) -> Harness:
    harness = Harness(**payload.model_dump())
    if harness.is_default:
        session.exec(sa_update(Harness).where(col(Harness.id) != harness.id).values(is_default=False))
    session.add(harness)
    session.commit()
    session.refresh(harness)
    return harness


@router.patch("/harnesses/{harness_id}", response_model=HarnessRead)
def update_harness(harness_id: str, payload: HarnessUpdate, session: Session = Depends(get_session)) -> Harness:
    harness = session.get(Harness, harness_id)
    if harness is None:
        raise HTTPException(status_code=404, detail="Harness not found")
    data = payload.model_dump(exclude_unset=True)
    # At most one default: promoting a harness demotes the others.
    if data.get("is_default"):
        session.exec(sa_update(Harness).where(col(Harness.id) != harness_id).values(is_default=False))
    for key, value in data.items():
        setattr(harness, key, value)
    session.add(harness)
    session.commit()
    session.refresh(harness)
    return harness


@router.delete("/harnesses/{harness_id}", status_code=204)
def delete_harness(harness_id: str, session: Session = Depends(get_session)) -> None:
    harness = session.get(Harness, harness_id)
    if harness is None:
        raise HTTPException(status_code=404, detail="Harness not found")
    session.exec(sa_update(Task).where(col(Task.harness_id) == harness.id).values(harness_id=None))
    session.exec(sa_update(AgentRun).where(col(AgentRun.harness_id) == harness.id).values(harness_id=None))
    session.exec(sa_delete(Harness).where(col(Harness.id) == harness.id))
    session.commit()


# --- runs -----------------------------------------------------------------
def _resolve_cwd(session: Session, task: Task, payload: RunCreate) -> str:
    if payload.cwd:
        return str(Path(payload.cwd).expanduser())
    if payload.worktree_id:
        worktree = session.get(Worktree, payload.worktree_id)
        if worktree is None or worktree.task_id != task.id:
            raise HTTPException(status_code=404, detail="Worktree not found")
        return worktree.path
    active = session.exec(
        select(Worktree)
        .where(Worktree.task_id == task.id, Worktree.status == "active")
        .order_by(col(Worktree.created_at).desc())
    ).first()
    if active is not None:
        return active.path
    task_repos = session.exec(
        select(TaskRepository).where(TaskRepository.task_id == task.id).order_by(col(TaskRepository.created_at))
    ).all()
    if task_repos:
        repo = session.get(Repository, task_repos[0].repository_id)
        if repo is not None:
            return repo.path
    settings.worktree_root.mkdir(parents=True, exist_ok=True)
    return str(settings.worktree_root)


@router.get("/tasks/{task_id}/runs", response_model=list[RunRead])
def list_runs(task_id: str, session: Session = Depends(get_session)) -> list[RunRead]:
    get_task_or_404(session, task_id)
    rows = session.exec(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(col(AgentRun.created_at).desc())
    ).all()
    return [run_read(session, run) for run in rows]


def _spawn(
    session: Session,
    task: Task,
    *,
    prompt: str,
    kind: str,
    harness_id: str | None,
    cwd: str,
    worktree_id: str | None,
) -> AgentRun:
    harness = get_harness(session, harness_id or task.harness_id)
    run = AgentRun(
        task_id=task.id,
        harness_id=harness.id,
        cwd=cwd,
        worktree_id=worktree_id,
        prompt=prompt,
        kind=kind,
        status=RunStatus.queued,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.post("/tasks/{task_id}/runs", response_model=RunRead, status_code=201)
async def create_run(task_id: str, payload: RunCreate, session: Session = Depends(get_session)) -> RunRead:
    task = get_task_or_404(session, task_id)
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    cwd = _resolve_cwd(session, task, payload)
    run = _spawn(
        session,
        task,
        prompt=payload.prompt,
        kind="chat",
        harness_id=payload.harness_id,
        cwd=cwd,
        worktree_id=payload.worktree_id,
    )
    add_timeline(session, task_id, "run_started", f"Agent run: {payload.prompt[:120]}", {"run_id": run.id})
    await enqueue_run(run.id)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "run_started", "run_id": run.id})
    return run_read(session, run)


@router.post("/tasks/{task_id}/context/refresh", response_model=RunRead, status_code=201)
async def refresh_context(task_id: str, session: Session = Depends(get_session)) -> RunRead:
    task = get_task_or_404(session, task_id)

    from ..models import Association, RepositoryGroup, RepositoryGroupMember, SourceItem

    assocs = session.exec(select(Association).where(Association.task_id == task_id)).all()
    items = []
    for assoc in assocs:
        item = session.get(SourceItem, assoc.item_id)
        if item is not None:
            items.append({"source": item.source, "title": item.title, "url": item.url, "content": item.content})
    worktrees = [
        {"branch": w.branch, "path": w.path}
        for w in session.exec(select(Worktree).where(Worktree.task_id == task_id)).all()
    ]
    task_repo_ids = [
        member.repository_id
        for member in session.exec(
            select(TaskRepository).where(TaskRepository.task_id == task_id).order_by(col(TaskRepository.created_at))
        ).all()
    ]
    repositories = [r.path for r in (session.get(Repository, rid) for rid in task_repo_ids) if r is not None]

    group = None
    if task.group_id:
        group_row = session.get(RepositoryGroup, task.group_id)
        if group_row is not None:
            member_ids = [
                member.repository_id
                for member in session.exec(
                    select(RepositoryGroupMember).where(RepositoryGroupMember.group_id == group_row.id)
                ).all()
            ]
            paths = [r.path for r in (session.get(Repository, rid) for rid in member_ids) if r is not None]
            group = {
                "name": group_row.name,
                "description": group_row.description,
                "repositories": paths,
            }

    task_ctx = {
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority,
        "repositories": repositories,
        "group": group,
        "worktrees": worktrees,
    }
    prompt = build_context_prompt(task_ctx, items)
    cwd = _resolve_cwd(session, task, RunCreate(prompt="context"))
    run = _spawn(session, task, prompt=prompt, kind="refresh_context", harness_id=None, cwd=cwd, worktree_id=None)
    add_timeline(session, task_id, "context_refresh", "Requested context refresh", {"run_id": run.id})
    await enqueue_run(run.id)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "context_refreshing", "run_id": run.id})
    return run_read(session, run)


async def start_slack_summary(session: Session, task: Task, *, thread: str) -> AgentRun:
    """Queue a run that an agent uses to name the task and summarize its Slack thread.

    Called when a task is created from a Slack URL: the thread content fetched by
    ``slackx`` is handed to the agent, and the parsed title and summary are
    written back onto the task when the run finishes. Whether the run names the
    task is decided by the worker from the task's current title.
    """
    cwd = _resolve_cwd(session, task, RunCreate(prompt="summary"))
    prompt = build_summary_prompt(thread)
    run = _spawn(session, task, prompt=prompt, kind="summarize_slack", harness_id=None, cwd=cwd, worktree_id=None)
    add_timeline(
        session,
        task.id,
        "summary_requested",
        "Requested a title and summary for the Slack thread",
        {"run_id": run.id},
    )
    await enqueue_run(run.id)
    return run


def _task_slack_item(session: Session, task_id: str) -> SourceItem | None:
    """The first Slack thread item associated with a task, if any."""
    for assoc in session.exec(select(Association).where(Association.task_id == task_id)).all():
        item = session.get(SourceItem, assoc.item_id)
        if item is not None and item.source == "slack":
            return item
    return None


@router.post("/tasks/{task_id}/summary/refresh", response_model=RunRead, status_code=201)
async def refresh_summary(task_id: str, session: Session = Depends(get_session)) -> RunRead:
    """Re-dispatch the Slack naming and summarizing run for a task.

    Lets an import run that failed or was interrupted be retried without
    recreating the task.
    """
    task = get_task_or_404(session, task_id)
    item = _task_slack_item(session, task_id)
    if item is None:
        raise HTTPException(status_code=400, detail="Task has no associated Slack thread")
    thread = (item.content or "").strip()
    if not thread:
        raise HTTPException(status_code=400, detail="The Slack thread has no content to summarize")
    run = await start_slack_summary(session, task, thread=thread)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "summary_refreshing", "run_id": run.id})
    return run_read(session, run)


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_read(session, run)


@router.get("/runs/{run_id}/events", response_model=list[AgentEventRead])
def get_run_events(run_id: str, session: Session = Depends(get_session)) -> list[AgentEvent]:
    return list(session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(col(AgentEvent.seq))).all())


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    # Aborts the queued/running job; the worker cancels an active turn. A job that
    # never started is aborted here, so record the outcome on the run too.
    await cancel_queued_run(run_id)
    if run.status in (RunStatus.queued, RunStatus.running):
        run.status = RunStatus.cancelled
        run.ended_at = utcnow()
        session.add(run)
        session.commit()
    return run_read(session, run)


def _sse(event: dict) -> dict:
    # Always use the default event name so EventSource.onmessage fires client-side;
    # the real kind travels inside the JSON payload as `type`.
    return {"event": "message", "data": json.dumps(event)}


def _task_signature(session: Session, task_id: str) -> tuple:
    """A cheap value that changes when anything the task page shows changes.

    The worker runs in another process, so its in-process event bus cannot reach
    these streams; the signature lets a stream notice its writes by polling the DB.
    """
    task = session.get(Task, task_id)
    if task is None:
        return ("deleted",)
    runs = session.exec(select(AgentRun).where(AgentRun.task_id == task_id)).all()
    last_event = session.exec(
        select(TimelineEvent.created_at)
        .where(TimelineEvent.task_id == task_id)
        .order_by(col(TimelineEvent.created_at).desc())
    ).first()
    return (
        task.title,
        task.summary,
        task.updated_at.isoformat() if task.updated_at else "",
        tuple(sorted((r.id, str(r.status)) for r in runs)),
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
                await asyncio.sleep(1)

    return EventSourceResponse(generator(), ping=15)

    return EventSourceResponse(generator(), ping=15)


@router.get("/tasks/{task_id}/context", response_model=ContextPreview)
def context_preview(task_id: str, session: Session = Depends(get_session)) -> ContextPreview:
    task = get_task_or_404(session, task_id)
    return ContextPreview(
        task_id=task.id,
        summary=task.summary,
        next_steps=task.next_steps or [],
        context_updated_at=task.context_updated_at,
    )
