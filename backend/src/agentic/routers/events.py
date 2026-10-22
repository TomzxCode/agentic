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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlmodel import Session, col, select

from ..crud import get_or_404
from ..db import get_session
from ..models.tasks import Task, TimelineEvent
from ..routers.people_service import person_aliases, person_for_alias
from ..schemas.events import EventRead, SlackEventSend
from ..services import slack
from ..services.slack import SlackError
from ..settings_store import get_settings

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


def _event_recipient(session: Session, payload: SlackEventSend | None, query_user_id: str | None = None, query_channel: str | None = None) -> str | None:
    if payload is not None:
        for value in (payload.user_id, payload.slack_user_id, payload.channel, payload.recipient, payload.to):
            if value:
                return str(value).strip()
        if payload.login:
            person = person_for_alias(session, payload.login)
            if person is not None:
                return slack.resolve_slack_user_id(person_aliases(session, person.id))
    for value in (query_user_id, query_channel):
        if value:
            return str(value).strip()
    effective = get_settings(session)
    for key in ("slack_events_user_id", "slack_event_user_id", "slack_notify_user_id", "slack_user_id", "slack_events_channel"):
        value = effective.get(key)
        if value:
            return str(value).strip()
    from ..config import settings as app_settings

    for attr in ("slack_events_user_id", "slack_event_user_id", "slack_notify_user_id", "slack_user_id", "slack_events_channel"):
        value = getattr(app_settings, attr, "")
        if value:
            return str(value).strip()
    return None


def _send_one_event(session: Session, event_id: str, payload: SlackEventSend | None = None, query_user_id: str | None = None, query_channel: str | None = None) -> dict[str, Any]:
    event = get_or_404(session, TimelineEvent, event_id, "Event not found")
    task = session.get(Task, event.task_id)
    task_title = None
    if payload is not None and payload.task_title:
        task_title = payload.task_title
    elif task is not None:
        task_title = task.title
    recipient = _event_recipient(session, payload, query_user_id, query_channel)
    try:
        sent = slack.slack_send_event(recipient, event, task_title=task_title)
    except SlackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": bool(sent.get("ok", True)),
        "event_id": event.id,
        "task_id": event.task_id,
        "slack_user_id": recipient,
        "ts": sent.get("ts"),
    }


def _send_events(session: Session, payload: SlackEventSend | None = None, query_user_id: str | None = None, query_channel: str | None = None) -> dict[str, Any]:
    recipient = _event_recipient(session, payload, query_user_id, query_channel)
    task_title = payload.task_title if payload is not None else None
    event_ids = None
    task_id = None
    if payload is not None:
        event_ids = payload.event_ids
        if payload.event_id:
            event_ids = [payload.event_id]
        task_id = payload.task_id
    if event_ids:
        events = [session.get(TimelineEvent, eid) for eid in event_ids]
        events = [e for e in events if e is not None]
    elif task_id:
        statement = select(TimelineEvent).where(TimelineEvent.task_id == task_id).order_by(col(TimelineEvent.created_at).desc()).limit(50)
        events = list(session.exec(statement).all())
    else:
        statement = select(TimelineEvent).order_by(col(TimelineEvent.created_at).desc()).limit(50)
        events = list(session.exec(statement).all())
    if not events:
        raise HTTPException(status_code=404, detail="No events to send")
    if task_title is None and len(events) == 1:
        task = session.get(Task, events[0].task_id)
        task_title = task.title if task is not None else None
    try:
        sent = slack.slack_send_events(recipient, events, task_title=task_title)
    except SlackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": bool(sent.get("ok", True)),
        "count": len(events),
        "event_ids": [e.id for e in events],
        "slack_user_id": recipient,
        "ts": sent.get("ts"),
    }


# Single-event endpoints.
@router.post("/{event_id}/slack")
def send_event_to_slack(event_id: str, payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _send_one_event(session, event_id, payload, user_id, channel)


@router.post("/{event_id}/send")
def send_event(event_id: str, payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _send_one_event(session, event_id, payload, user_id, channel)


@router.post("/{event_id}/send-to-slack")
def send_event_to_slack_alias(event_id: str, payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _send_one_event(session, event_id, payload, user_id, channel)


# Multi-event endpoints.
@router.post("/slack")
def send_events_to_slack(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _send_events(session, payload, user_id, channel)


@router.post("/send")
def send_events(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _send_events(session, payload, user_id, channel)


@router.post("/send-to-slack")
def send_events_to_slack_alias(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _send_events(session, payload, user_id, channel)


__all__ = ["router"]
