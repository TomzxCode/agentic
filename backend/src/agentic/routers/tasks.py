"""Tasks: the unit of work everything else hangs off."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, select

from ..crud import get_task_or_404, normalize_tags
from ..db import get_session
from ..models.base import TaskStatus, utcnow
from ..models.tasks import Task, TimelineEvent
from ..schemas.tasks import (
    TaskDetail,
    TaskRead,
    TimelineRead,
)
from .task_service import _detail, _task_reads

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
def list_tasks(
    status: str | None = None,
    q: str | None = None,
    tag: list[str] = Query(default=[]),
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    query = select(Task).order_by(col(Task.updated_at).desc())
    if status:
        query = query.where(Task.status == status)
    tasks = list(session.exec(query).all())
    # A task matches only when it carries every requested tag (AND).
    wanted = set(normalize_tags(tag))
    if wanted:
        tasks = [p for p in tasks if wanted.issubset(set(p.tags or []))]
    if q:
        needle = q.lower()
        tasks = [
            p
            for p in tasks
            if needle in p.title.lower()
            or needle in (p.description or "").lower()
            or needle in (p.summary or "").lower()
        ]
    return _task_reads(session, tasks)


# Declared before /{task_id} so "deadlines" is not read as a task id.
@router.get("/deadlines", response_model=list[TaskRead])
def list_deadlines(within_days: int = 7, session: Session = Depends(get_session)) -> list[TaskRead]:
    """In-flight tasks with a deadline, soonest first (overdue included).

    A task is included when its deadline is at or before now plus ``within_days``;
    overdue deadlines always match, since those need attention most.
    """
    cutoff = utcnow() + timedelta(days=max(0, within_days))
    tasks = session.exec(
        select(Task)
        .where(col(Task.deadline).is_not(None))
        .where(col(Task.deadline) <= cutoff)
        .order_by(col(Task.deadline))
    ).all()
    closed = (TaskStatus.done, TaskStatus.archived)
    filtered = [task for task in tasks if task.status not in closed]
    return _task_reads(session, filtered)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, session: Session = Depends(get_session)) -> TaskDetail:
    task = get_task_or_404(session, task_id)
    return _detail(session, task)


@router.get("/{task_id}/timeline", response_model=list[TimelineRead])
def get_timeline(task_id: str, session: Session = Depends(get_session)) -> list[TimelineEvent]:
    get_task_or_404(session, task_id)
    return list(
        session.exec(
            select(TimelineEvent).where(TimelineEvent.task_id == task_id).order_by(col(TimelineEvent.created_at).desc())
        ).all()
    )


__all__ = ["router", "_detail"]
