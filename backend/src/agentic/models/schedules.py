"""SQLModel tables for schedules."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from .base import (
    ScheduledRunStatus,
    new_id,
    utcnow,
)


class ScheduledTask(SQLModel, table=True):
    """A user-defined shell command the app runs on a cron schedule.

    A scheduled task is the app's own periodic work, kept apart from a ``Task``
    (a unit of tracked work) and from an agent run: it holds a shell command, a
    cron expression, and whether it is enabled. The scheduler in the API process
    executes it when its ``next_run_at`` falls due.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    # Run with the shell, so pipes, redirects, and ``&&`` work as written.
    command: str
    # Working directory for the command; None runs in the server's own directory.
    cwd: str | None = None
    # A 5-field cron expression: minute hour day-of-month month day-of-week.
    schedule: str
    # The IANA zone the cron is read in; None uses the server's own timezone.
    timezone: str | None = None
    enabled: bool = True
    last_run_at: datetime | None = None
    # Recomputed whenever the task is created, edited, or run, so the scheduler
    # never fires the same occurrence twice.
    next_run_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ScheduledTaskRun(SQLModel, table=True):
    """One execution of a scheduled task, with its captured output.

    A run is created before the command starts (``running``) and finalized when
    it ends, so an interrupted run is visible rather than silently missing.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    scheduled_task_id: str = Field(foreign_key="scheduledtask.id", index=True)
    status: ScheduledRunStatus = ScheduledRunStatus.running
    exit_code: int | None = None
    # Combined stdout and stderr, truncated to a readable tail.
    output: str = ""
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
