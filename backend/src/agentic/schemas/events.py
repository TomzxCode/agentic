"""Pydantic models for the cross-task activity feed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import ORMModel


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
