"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .tasks import TaskRead


class StackPush(BaseModel):
    """Add a task to the stack: a new one (``title``) or an existing ``task_id``."""

    title: str = ""
    description: str = ""
    task_id: str | None = None
    position: str = "top"


class StackReorder(BaseModel):
    entry_id: str
    position: int


class StackEntryUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class StackEntryRead(BaseModel):
    id: str
    task_id: str
    task: TaskRead | None = None
    position: int
    is_current: bool
    created_at: datetime
    deleted_at: datetime | None = None
    # Session-derived stats: when the entry first became current, when it last
    # was current, total time current, and how many times it became current.
    started_at: datetime | None = None
    last_current: datetime | None = None
    duration: float = 0.0
    execution_count: int = 0
