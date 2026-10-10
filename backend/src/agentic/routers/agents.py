"""Harnesses and agent runs, streamed to the SPA over SSE."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from ..agents import execute_context_refresh, execute_run, get_harness, harness_available, seed_harnesses
from ..config import settings
from ..crud import add_timeline, get_problem_or_404
from ..db import engine, get_session
from ..events import bus, runs
from ..links import run_read
from ..models import AgentEvent, AgentRun, Harness, Problem, Repository, RunStatus, Worktree
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
from ..services import build_context_prompt

router = APIRouter(prefix="/api", tags=["agents"])

# Strong references to in-flight run tasks so they are not garbage-collected
# mid-execution (asyncio only keeps weak references to running tasks).
_run_tasks: set[asyncio.Task] = set()


def _dispatch(coro) -> None:
    task = asyncio.create_task(coro)
    _run_tasks.add(task)
    task.add_done_callback(_run_tasks.discard)


# --- harnesses ------------------------------------------------------------
@router.get("/harnesses", response_model=list[HarnessStatus])
def list_harnesses(session: Session = Depends(get_session)) -> list[HarnessStatus]:
    seed_harnesses(session)
    statuses: list[HarnessStatus] = []
    for harness in session.exec(select(Harness)).all():
        available, detail = harness_available(harness)
        statuses.append(HarnessStatus(id=harness.id, name=harness.name, available=available, detail=detail))
    return statuses


@router.get("/harnesses/full", response_model=list[HarnessRead])
def list_harnesses_full(session: Session = Depends(get_session)) -> list[Harness]:
    seed_harnesses(session)
    return list(session.exec(select(Harness)).all())


@router.post("/harnesses", response_model=HarnessRead, status_code=201)
def create_harness(payload: HarnessCreate, session: Session = Depends(get_session)) -> Harness:
    harness = Harness(**payload.model_dump())
    session.add(harness)
    session.commit()
    session.refresh(harness)
    return harness


@router.patch("/harnesses/{harness_id}", response_model=HarnessRead)
def update_harness(harness_id: str, payload: HarnessUpdate, session: Session = Depends(get_session)) -> Harness:
    harness = session.get(Harness, harness_id)
    if harness is None:
        raise HTTPException(status_code=404, detail="Harness not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
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
    session.execute(sa_update(Problem).where(Problem.harness_id == harness.id).values(harness_id=None))
    session.execute(sa_update(AgentRun).where(AgentRun.harness_id == harness.id).values(harness_id=None))
    session.execute(sa_delete(Harness).where(Harness.id == harness.id))
    session.commit()


# --- runs -----------------------------------------------------------------
def _resolve_cwd(session: Session, problem: Problem, payload: RunCreate) -> str:
    if payload.cwd:
        return str(Path(payload.cwd).expanduser())
    if payload.worktree_id:
        worktree = session.get(Worktree, payload.worktree_id)
        if worktree is None or worktree.problem_id != problem.id:
            raise HTTPException(status_code=404, detail="Worktree not found")
        return worktree.path
    active = session.exec(
        select(Worktree)
        .where(Worktree.problem_id == problem.id, Worktree.status == "active")
        .order_by(Worktree.created_at.desc())
    ).first()
    if active is not None:
        return active.path
    if problem.repository_id:
        repo = session.get(Repository, problem.repository_id)
        if repo is not None:
            return repo.path
    settings.worktree_root.mkdir(parents=True, exist_ok=True)
    return str(settings.worktree_root)


@router.get("/problems/{problem_id}/runs", response_model=list[RunRead])
def list_runs(problem_id: str, session: Session = Depends(get_session)) -> list[RunRead]:
    get_problem_or_404(session, problem_id)
    rows = session.exec(
        select(AgentRun).where(AgentRun.problem_id == problem_id).order_by(AgentRun.created_at.desc())
    ).all()
    return [run_read(session, run) for run in rows]


def _spawn(
    session: Session,
    problem: Problem,
    *,
    prompt: str,
    kind: str,
    harness_id: str | None,
    cwd: str,
    worktree_id: str | None,
) -> AgentRun:
    harness = get_harness(session, harness_id or problem.harness_id)
    run = AgentRun(
        problem_id=problem.id,
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


@router.post("/problems/{problem_id}/runs", response_model=RunRead, status_code=201)
async def create_run(problem_id: str, payload: RunCreate, session: Session = Depends(get_session)) -> RunRead:
    problem = get_problem_or_404(session, problem_id)
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    cwd = _resolve_cwd(session, problem, payload)
    run = _spawn(
        session,
        problem,
        prompt=payload.prompt,
        kind="chat",
        harness_id=payload.harness_id,
        cwd=cwd,
        worktree_id=payload.worktree_id,
    )
    add_timeline(session, problem_id, "run_started", f"Agent run: {payload.prompt[:120]}", {"run_id": run.id})
    cancel_event = runs.register(run.id)
    _dispatch(
        execute_run(run_id=run.id, harness_id=run.harness_id, cwd=cwd, prompt=payload.prompt, cancel_event=cancel_event)
    )
    await bus.publish(f"problem:{problem_id}", {"kind": "problem", "action": "run_started", "run_id": run.id})
    return run_read(session, run)


@router.post("/problems/{problem_id}/context/refresh", response_model=RunRead, status_code=201)
async def refresh_context(problem_id: str, session: Session = Depends(get_session)) -> RunRead:
    problem = get_problem_or_404(session, problem_id)

    from ..models import Association, RepositoryGroup, RepositoryGroupMember, SourceItem

    assocs = session.exec(select(Association).where(Association.problem_id == problem_id)).all()
    items = []
    for assoc in assocs:
        item = session.get(SourceItem, assoc.item_id)
        if item is not None:
            items.append({"source": item.source, "title": item.title, "url": item.url, "content": item.content})
    worktrees = [
        {"branch": w.branch, "path": w.path}
        for w in session.exec(select(Worktree).where(Worktree.problem_id == problem_id)).all()
    ]
    repo = session.get(Repository, problem.repository_id) if problem.repository_id else None

    group = None
    if problem.group_id:
        group_row = session.get(RepositoryGroup, problem.group_id)
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

    problem_ctx = {
        "title": problem.title,
        "description": problem.description,
        "status": problem.status.value,
        "priority": problem.priority,
        "repository": repo.path if repo else None,
        "group": group,
        "worktrees": worktrees,
    }
    prompt = build_context_prompt(problem_ctx, items)
    cwd = _resolve_cwd(session, problem, RunCreate(prompt="context"))
    run = _spawn(session, problem, prompt=prompt, kind="refresh_context", harness_id=None, cwd=cwd, worktree_id=None)
    add_timeline(session, problem_id, "context_refresh", "Requested context refresh", {"run_id": run.id})
    cancel_event = runs.register(run.id)
    ctx = {"title": problem.title, "description": problem.description}
    _dispatch(
        execute_context_refresh(
            run_id=run.id,
            problem_id=problem_id,
            harness_id=run.harness_id,
            cwd=cwd,
            prompt=prompt,
            cancel_event=cancel_event,
            problem_ctx=ctx,
        )
    )
    await bus.publish(f"problem:{problem_id}", {"kind": "problem", "action": "context_refreshing", "run_id": run.id})
    return run_read(session, run)


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_read(session, run)


@router.get("/runs/{run_id}/events", response_model=list[AgentEventRead])
def get_run_events(run_id: str, session: Session = Depends(get_session)) -> list[AgentEvent]:
    return list(session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(AgentEvent.seq)).all())


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    # Must run on the event loop: asyncio.Event.set() is not thread-safe.
    runs.cancel(run_id)
    return run_read(session, run)


def _sse(event: dict) -> dict:
    # Always use the default event name so EventSource.onmessage fires client-side;
    # the real kind travels inside the JSON payload as `type`.
    return {"event": "message", "data": json.dumps(event)}


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> EventSourceResponse:
    async def generator() -> AsyncIterator[dict]:
        # Subscribe before reading state so no event can slip between the replay
        # and the subscription; dedupe replayed events against the live stream.
        async with bus.subscribe(f"run:{run_id}") as queue:
            with Session(engine) as session:
                run = session.get(AgentRun, run_id)
                if run is None:
                    yield {"event": "message", "data": json.dumps({"type": "error", "error": "run not found"})}
                    return
                finished = run.status in (RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled)
                replay = list(
                    session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(AgentEvent.seq)).all()
                )
            last_seq = 0
            for row in replay:
                last_seq = row.seq
                yield _sse({"seq": row.seq, "type": row.type, "text": row.text, "data": row.data_json})
            if finished:
                yield _sse({"type": "run_finished", "data": {"run_id": run_id}})
                return
            while True:
                event = await queue.get()
                if isinstance(event.get("seq"), int) and event["seq"] <= last_seq:
                    continue
                yield _sse(event)
                if event.get("type") == "run_finished":
                    return

    return EventSourceResponse(generator(), ping=15)


@router.get("/problems/{problem_id}/stream")
async def stream_problem(problem_id: str, session: Session = Depends(get_session)) -> EventSourceResponse:
    get_problem_or_404(session, problem_id)

    async def generator() -> AsyncIterator[dict]:
        async with bus.subscribe(f"problem:{problem_id}") as queue:
            while True:
                event = await queue.get()
                yield {"event": "message", "data": json.dumps(event)}

    return EventSourceResponse(generator(), ping=15)


@router.get("/problems/{problem_id}/context", response_model=ContextPreview)
def context_preview(problem_id: str, session: Session = Depends(get_session)) -> ContextPreview:
    problem = get_problem_or_404(session, problem_id)
    return ContextPreview(
        problem_id=problem.id,
        summary=problem.summary,
        next_steps=problem.next_steps or [],
        context_updated_at=problem.context_updated_at,
    )
