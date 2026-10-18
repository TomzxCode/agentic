"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..models.base import TaskStatus
from .tasks import TimelineRead


class GanttTask(BaseModel):
    """A task as a Gantt row: its span, plus one marker per timeline event."""

    id: str
    title: str
    status: TaskStatus
    priority: int
    created_at: datetime
    updated_at: datetime
    markers: list[TimelineRead] = []
