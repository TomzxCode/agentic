"""Gantt view: tasks in flight as rows, with one marker per timeline event.

The page that consumes this shows a bar per task (created to last update) with
a marker at every timeline event, so progress and activity are visible together.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from ..db import get_session
from ..models.base import TaskStatus
from ..models.tasks import Task, TimelineEvent
from ..schemas.gantt import GanttTask
from ..schemas.tasks import TimelineRead

router = APIRouter(prefix="/api/gantt", tags=["gantt"])

# Tasks whose work is still in flight are shown by default.
CLOSED_STATUSES = (TaskStatus.done, TaskStatus.archived)


@router.get("", response_model=list[GanttTask])
def get_gantt(include_done: bool = False, session: Session = Depends(get_session)) -> list[GanttTask]:
    """Return tasks (oldest first) with the timeline markers on each row."""
    tasks = list(session.exec(select(Task).order_by(col(Task.created_at))).all())
    if not include_done:
        tasks = [task for task in tasks if task.status not in CLOSED_STATUSES]

    rows: list[GanttTask] = []
    for task in tasks:
        events = session.exec(
            select(TimelineEvent).where(TimelineEvent.task_id == task.id).order_by(col(TimelineEvent.created_at))
        ).all()
        rows.append(
            GanttTask(
                id=task.id,
                title=task.title,
                status=task.status,
                priority=task.priority,
                created_at=task.created_at,
                updated_at=task.updated_at,
                markers=[TimelineRead.model_validate(event) for event in events],
            )
        )
    return rows


__all__ = ["router"]
