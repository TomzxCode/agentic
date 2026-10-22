"""Pydantic models for the cross-task activity feed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .base import ORMModel


class SlackEventSend(BaseModel):
    """Ask the API to send one or more events through Slack."""

    user_id: str | None = None
    slack_user_id: str | None = None
    channel: str | None = None
    recipient: str | None = None
    to: str | None = None
    login: str | None = None
    event_id: str | None = None
    event_ids: list[str] | None = None
    task_id: str | None = None
    task_title: str | None = None
    text: str | None = None


class EventRead(ORMModel):
    """One timeline event with enough task context to stand on its own."""

    id: str
    task_id: str
    task_title: str
    task_status: str
    type: str
    message: str
    data_json: dict[str, Any]
    client: str
    actor: str
    created_at: datetime
