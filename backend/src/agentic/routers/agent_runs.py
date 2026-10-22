"""Agent runs, streamed to the SPA over SSE.

Mounted under ``/api``; the harness CRUD endpoints live in ``harnesses.py``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from ..agents.harnesses import get_harness
from ..config import settings
from ..crud import add_timeline, get_or_404, get_task_or_404
from ..db import get_session
from ..events import bus
from ..jobs import cancel_run as cancel_queued_run
from ..jobs import enqueue_run
from ..links import run_read
from ..models.agents import AgentEvent, AgentRun
from ..models.base import RunStatus, utcnow
from ..models.items import Association, SourceItem
from ..models.repositories import Repository, TaskRepository, Worktree
from ..models.tasks import Task
from ..schemas.runs import AgentEventRead, ContextPreview, RunCreate, RunRead
from ..services.prompts import build_context_prompt, build_summary_prompt

router = APIRouter(prefix="/api", tags=["agents"])

# Runs are processed by SAQ workers (see `agentic.jobs`); the API only enqueues.


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
    model: str | None = None,
) -> AgentRun:
    harness = get_harness(session, harness_id or task.harness_id)
    run = AgentRun(
        task_id=task.id,
        harness_id=harness.id,
        cwd=cwd,
        worktree_id=worktree_id,
        prompt=prompt,
        kind=kind,
        requested_model=(model or "").strip() or None,
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
        model=payload.model,
    )
    add_timeline(session, task_id, "run_started", f"Agent run: {payload.prompt[:120]}", {"run_id": run.id})
    await enqueue_run(run.id)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "run_started", "run_id": run.id})
    return run_read(session, run)


@router.post("/tasks/{task_id}/context/refresh", response_model=RunRead, status_code=201)
async def refresh_context(task_id: str, session: Session = Depends(get_session)) -> RunRead:
    task = get_task_or_404(session, task_id)

    from ..models.items import Association, SourceItem
    from ..models.repositories import RepositoryGroup, RepositoryGroupMember

    assocs = session.exec(select(Association).where(Association.task_id == task_id)).all()
    items = []
    for assoc in assocs:
        item = session.get(SourceItem, assoc.item_id)
        if item is not None:
            items.append(
                {
                    "source": item.source,
                    "title": item.title,
                    "url": item.url,
                    "path": (item.metadata_json or {}).get("path"),
                    "content": item.content,
                }
            )
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
    run = get_or_404(session, AgentRun, run_id, "Run not found")
    return run_read(session, run)


@router.get("/runs/{run_id}/events", response_model=list[AgentEventRead])
def get_run_events(run_id: str, session: Session = Depends(get_session)) -> list[AgentEvent]:
    return list(session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(col(AgentEvent.seq))).all())


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = get_or_404(session, AgentRun, run_id, "Run not found")
    # Aborts the queued/running job; the worker cancels an active turn. A job that
    # never started is aborted here, so record the outcome on the run too.
    await cancel_queued_run(run_id)
    if run.status in (RunStatus.queued, RunStatus.running):
        run.status = RunStatus.cancelled
        run.ended_at = utcnow()
        session.add(run)
        session.commit()
    return run_read(session, run)


@router.get("/tasks/{task_id}/context", response_model=ContextPreview)
def context_preview(task_id: str, session: Session = Depends(get_session)) -> ContextPreview:
    task = get_task_or_404(session, task_id)
    return ContextPreview(
        task_id=task.id,
        summary=task.summary,
        next_steps=task.next_steps or [],
        context_updated_at=task.context_updated_at,
    )


__all__ = ["router", "start_slack_summary"]
