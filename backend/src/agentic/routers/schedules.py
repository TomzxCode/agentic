"""Scheduled shell tasks: the app's own cron-driven commands.

Each scheduled task holds a shell command and a cron expression. This router is
the CRUD surface plus "run now" and the run history; the scheduler that fires
them lives in ``agentic.schedules``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from .. import schedules
from ..crud import get_or_404
from ..db import get_session
from ..models.base import utcnow
from ..models.schedules import ScheduledTask, ScheduledTaskRun
from ..schemas.schedules import (
    ScheduledTaskCreate,
    ScheduledTaskExecutionRead,
    ScheduledTaskPreviewRead,
    ScheduledTaskRead,
    ScheduledTaskRunRead,
    ScheduledTaskUpdate,
)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _read(session: Session, task: ScheduledTask) -> ScheduledTaskRead:
    last = session.exec(
        select(ScheduledTaskRun)
        .where(col(ScheduledTaskRun.scheduled_task_id) == task.id)
        .order_by(col(ScheduledTaskRun.started_at).desc())
    ).first()
    return ScheduledTaskRead(
        id=task.id,
        name=task.name,
        command=task.command,
        schedule=task.schedule,
        cwd=task.cwd,
        timezone=str(schedules.resolve_timezone(task.timezone)),
        enabled=task.enabled,
        last_run_at=task.last_run_at,
        next_run_at=task.next_run_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        last_status=last.status if last else None,
        last_exit_code=last.exit_code if last else None,
    )


def _validate_timezone(value: str | None) -> str | None:
    """Return a canonical zone name, or None to follow the server's timezone."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return str(schedules.resolve_timezone(text))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate(name: str, command: str) -> tuple[str, str]:
    name = (name or "").strip()
    command = (command or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not command:
        raise HTTPException(status_code=400, detail="Command is required")
    return name, command


@router.get("", response_model=list[ScheduledTaskRead])
def list_schedules(session: Session = Depends(get_session)) -> list[ScheduledTaskRead]:
    """List scheduled tasks, enabled ones first, soonest next run first."""
    tasks = session.exec(
        select(ScheduledTask).order_by(
            col(ScheduledTask.enabled).desc(),
            col(ScheduledTask.next_run_at).asc(),
            col(ScheduledTask.created_at).desc(),
        )
    ).all()
    return [_read(session, task) for task in tasks]


@router.post("", response_model=ScheduledTaskRead, status_code=201)
def create_schedule(payload: ScheduledTaskCreate, session: Session = Depends(get_session)) -> ScheduledTaskRead:
    name, command = _validate(payload.name, payload.command)
    try:
        expression = schedules.validate_schedule(payload.schedule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task = ScheduledTask(
        name=name,
        command=command,
        schedule=expression,
        cwd=payload.cwd,
        timezone=_validate_timezone(payload.timezone),
        enabled=payload.enabled,
    )
    if task.enabled:
        task.next_run_at = schedules.compute_next_run(expression, timezone=task.timezone)
    session.add(task)
    session.commit()
    session.refresh(task)
    return _read(session, task)


@router.get("/preview", response_model=ScheduledTaskPreviewRead)
def preview_schedule(
    schedule: str,
    timezone: str | None = None,
    count: int = Query(default=5, ge=1, le=20),
) -> ScheduledTaskPreviewRead:
    """Validate a cron expression and return its next occurrences in a timezone."""
    try:
        expression = schedules.validate_schedule(schedule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        zone = schedules.resolve_timezone(timezone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScheduledTaskPreviewRead(
        next_runs=schedules.upcoming_runs(expression, count=count, timezone=timezone),
        timezone=str(zone),
    )


@router.get("/runs", response_model=list[ScheduledTaskExecutionRead])
def list_executions(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[ScheduledTaskExecutionRead]:
    """Every run across all scheduled tasks, newest first."""
    rows = session.exec(
        select(ScheduledTaskRun, ScheduledTask)
        .join(ScheduledTask, col(ScheduledTaskRun.scheduled_task_id) == col(ScheduledTask.id))
        .order_by(col(ScheduledTaskRun.started_at).desc())
        .limit(limit)
    ).all()
    return [
        ScheduledTaskExecutionRead(
            id=run.id,
            scheduled_task_id=run.scheduled_task_id,
            task_name=task.name,
            task_command=task.command,
            status=run.status,
            exit_code=run.exit_code,
            output=run.output,
            started_at=run.started_at,
            ended_at=run.ended_at,
        )
        for run, task in rows
    ]


@router.get("/runs/{run_id}", response_model=ScheduledTaskRunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> ScheduledTaskRun:
    run = get_or_404(session, ScheduledTaskRun, run_id, "Run not found")
    return run


@router.get("/{task_id}", response_model=ScheduledTaskRead)
def get_schedule(task_id: str, session: Session = Depends(get_session)) -> ScheduledTaskRead:
    task = get_or_404(session, ScheduledTask, task_id, "Scheduled task not found")
    return _read(session, task)


@router.patch("/{task_id}", response_model=ScheduledTaskRead)
def update_schedule(
    task_id: str, payload: ScheduledTaskUpdate, session: Session = Depends(get_session)
) -> ScheduledTaskRead:
    task = get_or_404(session, ScheduledTask, task_id, "Scheduled task not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        task.name = data["name"].strip() or task.name
    if data.get("command") is not None:
        task.command = data["command"].strip() or task.command
    if "cwd" in data:
        task.cwd = data["cwd"]
    if data.get("enabled") is not None:
        task.enabled = data["enabled"]
    if data.get("schedule") is not None:
        try:
            task.schedule = schedules.validate_schedule(data["schedule"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    timezone_changed = "timezone" in data
    if timezone_changed:
        task.timezone = _validate_timezone(data["timezone"])

    # Recompute the next occurrence only when it is actually affected, so editing
    # a name does not push a pending run further out.
    if not task.enabled:
        task.next_run_at = None
    elif "schedule" in data or "enabled" in data or timezone_changed or task.next_run_at is None:
        task.next_run_at = schedules.compute_next_run(task.schedule, timezone=task.timezone)

    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return _read(session, task)


@router.delete("/{task_id}", status_code=204)
def delete_schedule(task_id: str, session: Session = Depends(get_session)) -> None:
    get_or_404(session, ScheduledTask, task_id, "Scheduled task not found")
    session.exec(sa_delete(ScheduledTaskRun).where(col(ScheduledTaskRun.scheduled_task_id) == task_id))
    session.exec(sa_delete(ScheduledTask).where(col(ScheduledTask.id) == task_id))
    session.commit()


@router.post("/{task_id}/run", response_model=ScheduledTaskRunRead, status_code=201)
async def run_schedule_now(task_id: str, session: Session = Depends(get_session)) -> ScheduledTaskRun:
    """Start a run immediately, in the background, and return its row."""
    get_or_404(session, ScheduledTask, task_id, "Scheduled task not found")
    run_id = await schedules.start_run(task_id)
    run = session.get(ScheduledTaskRun, run_id)
    if run is None:  # pragma: no cover - the row was just created
        raise HTTPException(status_code=500, detail="Run was not recorded")
    return run


@router.get("/{task_id}/runs", response_model=list[ScheduledTaskRunRead])
def list_runs(
    task_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ScheduledTaskRun]:
    get_or_404(session, ScheduledTask, task_id, "Scheduled task not found")
    return list(
        session.exec(
            select(ScheduledTaskRun)
            .where(col(ScheduledTaskRun.scheduled_task_id) == task_id)
            .order_by(col(ScheduledTaskRun.started_at).desc())
            .limit(limit)
        ).all()
    )


__all__ = ["router"]
