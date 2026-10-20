"""Events: the cross-task stream of everything that happens in the system.

A task's timeline is the app's activity record, so the global feed is every
task's timeline read at once.
Each row carries just enough task context (title and status) to read on its
own.
The operations audit log is deliberately not merged in: it records raw mutating
requests, so the same action would appear twice in the stream.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_
from sqlmodel import Session, col, select

from ..db import get_session
from ..models.tasks import Task, TimelineEvent
from ..schemas.events import EventRead

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventRead])
def list_events(
    task_id: str | None = None,
    type: str | None = None,
    actor: str | None = None,
    client: str | None = None,
    q: str | None = None,
    before: datetime | None = None,
    before_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[EventRead]:
    """Newest first, optionally filtered and paged with a ``before`` cursor.

    ``before`` is the ``created_at`` of the last row already seen and
    ``before_id`` its id; the id tie-breaker keeps rows written in the same
    instant from being skipped between pages.
    """
    query = (
        select(TimelineEvent, Task)
        .join(Task, col(TimelineEvent.task_id) == col(Task.id))
        .order_by(col(TimelineEvent.created_at).desc(), col(TimelineEvent.id).desc())
        .limit(limit)
    )
    if task_id:
        query = query.where(TimelineEvent.task_id == task_id)
    if type:
        query = query.where(TimelineEvent.type == type)
    if actor:
        query = query.where(TimelineEvent.actor == actor)
    if client:
        query = query.where(TimelineEvent.client == client)
    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.where(
            or_(func.lower(col(TimelineEvent.message)).like(needle), func.lower(col(Task.title)).like(needle))
        )
    if before is not None:
        if before.tzinfo is None:
            before = before.replace(tzinfo=UTC)
        if before_id:
            query = query.where(
                or_(
                    col(TimelineEvent.created_at) < before,
                    and_(col(TimelineEvent.created_at) == before, col(TimelineEvent.id) < before_id),
                )
            )
        else:
            query = query.where(col(TimelineEvent.created_at) < before)

    rows = session.exec(query).all()
    return [
        EventRead(
            id=event.id,
            task_id=event.task_id,
            task_title=task.title,
            task_status=task.status,
            type=event.type,
            message=event.message,
            data_json=event.data_json,
            client=event.client,
            actor=event.actor,
            created_at=event.created_at,
        )
        for event, task in rows
    ]


__all__ = ["router"]
