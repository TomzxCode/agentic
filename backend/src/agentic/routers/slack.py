"""Slack: name the workspace users slackx caches, and send events through Slack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlmodel import Session

from ..db import get_session
from ..routers.events import _event_recipient, _send_events, _send_one_event
from ..schemas.events import SlackEventSend
from ..schemas.slack import SlackUsers
from ..services import slack
from ..services.slack import SlackError, resolve_slack_user_ids

router = APIRouter(prefix="/api/slack", tags=["slack"])


@router.get("/users", response_model=SlackUsers)
def list_users(ids: list[str] = Query(default=[])) -> SlackUsers:
    """Name the given Slack user ids through slackx.

    The caller passes the values it is about to display, and only the ones that
    look like a Slack user id are looked up. A cached user is named from one
    bulk read; an uncached one is fetched from Slack on its own. Ids that cannot
    be named are left out, and an empty result is not an error: slackx may be
    missing, or a value may be a handle rather than an id.
    """
    return SlackUsers(names=resolve_slack_user_ids(ids))


# Send one event (identified in the path or in the body).
@router.post("/events/{event_id}")
def send_slack_event(event_id: str, payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)):
    return _send_one_event(session, event_id, payload, user_id, channel)


@router.post("/event/{event_id}")
def send_slack_event_alias(event_id: str, payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)):
    return _send_one_event(session, event_id, payload, user_id, channel)


# Send several / recent events.
@router.post("/events")
def send_slack_events(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)):
    return _send_events(session, payload, user_id, channel)


@router.post("/event")
def send_slack_event_multi(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)):
    return _send_events(session, payload, user_id, channel)


@router.post("/send")
def slack_send(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)):
    # If a single event_id is given, send that one; otherwise send many.
    if payload is not None and (payload.event_id and not payload.event_ids and not payload.task_id):
        return _send_one_event(session, payload.event_id, payload, user_id, channel)
    return _send_events(session, payload, user_id, channel)


@router.post("/send-event")
def slack_send_event_endpoint(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)):
    if payload is not None and (payload.event_id and not payload.event_ids and not payload.task_id):
        return _send_one_event(session, payload.event_id, payload, user_id, channel)
    return _send_events(session, payload, user_id, channel)


@router.post("/send-events")
def slack_send_events_endpoint(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), session: Session = Depends(get_session)):
    return _send_events(session, payload, user_id, channel)


def _send_test(session: Session, payload: SlackEventSend | None = None, user_id: str | None = None, channel: str | None = None, text: str | None = None) -> dict[str, Any]:
    recipient = _event_recipient(session, payload, user_id, channel)
    message = text or "Agentic test notification"
    try:
        sent = slack.slack_send_bot_dm(recipient, message)
    except SlackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": bool(sent.get("ok", True)), "slack_user_id": recipient, "ts": sent.get("ts"), "text": message}


@router.post("/test")
def slack_test(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), text: str | None = Query(default=None), session: Session = Depends(get_session)):
    return _send_test(session, payload, user_id, channel, text)


@router.post("/test-notification")
def slack_test_notification(payload: SlackEventSend | None = Body(default=None), user_id: str | None = Query(default=None), channel: str | None = Query(default=None), text: str | None = Query(default=None), session: Session = Depends(get_session)):
    return _send_test(session, payload, user_id, channel, text)