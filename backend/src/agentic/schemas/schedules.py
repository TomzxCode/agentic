"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .base import ORMModel


class ScheduledTaskCreate(BaseModel):
    name: str
    command: str
    schedule: str
    cwd: str | None = None
    # IANA zone for the cron; omitted means the server's own timezone.
    timezone: str | None = None
    enabled: bool = True


class ScheduledTaskUpdate(BaseModel):
    name: str | None = None
    command: str | None = None
    schedule: str | None = None
    cwd: str | None = None
    timezone: str | None = None
    enabled: bool | None = None


class ScheduledTaskRead(ORMModel):
    id: str
    name: str
    command: str
    schedule: str
    cwd: str | None = None
    # The zone the cron is evaluated in, resolved to the server's when unset.
    timezone: str
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # The latest run's outcome, so a list row shows it without a second call.
    last_status: str | None = None
    last_exit_code: int | None = None


class ScheduledTaskPreviewRead(BaseModel):
    """The next occurrences of a cron expression, for the form's live preview."""

    next_runs: list[datetime] = []
    # The zone the cron is evaluated in, so the form can label the times.
    timezone: str


class ScheduledTaskRunRead(ORMModel):
    id: str
    scheduled_task_id: str
    status: str
    exit_code: int | None = None
    output: str = ""
    started_at: datetime
    ended_at: datetime | None = None


class ScheduledTaskExecutionRead(ORMModel):
    """One run in the cross-task execution history, with its task's identity."""

    id: str
    scheduled_task_id: str
    task_name: str
    task_command: str
    status: str
    exit_code: int | None = None
    output: str = ""
    started_at: datetime
    ended_at: datetime | None = None
