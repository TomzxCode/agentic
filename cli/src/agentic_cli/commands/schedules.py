"""CLI commands."""

from __future__ import annotations

from typing import Any

from cyclopts import App

from .. import runtime
from ..render import (
    _join,
    _schedule_line,
    _schedule_run_text,
    _schedule_text,
)
from ..runtime import (
    emit,
    safe,
)

schedule_app = App(name="schedule", help="Create and manage scheduled shell tasks.")


def register(app: App) -> None:
    app.command(schedule_app)


@schedule_app.command(name="list")
@safe
def schedule_list() -> str:
    """List scheduled tasks, soonest next run first."""
    with runtime._client() as client:
        tasks = client.list_schedules()
    return emit(tasks, _join(tasks, _schedule_line))


@schedule_app.command(name="get")
@safe
def schedule_get(schedule_id: str) -> str:
    """Show one scheduled task.

    Parameters
    ----------
    schedule_id
        The task id, as shown by ``schedule list``.
    """
    with runtime._client() as client:
        task = client.get_schedule(schedule_id)
    return emit(task, _schedule_text(task))


@schedule_app.command(name="create")
@safe
def schedule_create(
    name: str,
    command: str,
    schedule: str,
    cwd: str | None = None,
    timezone: str | None = None,
    disabled: bool = False,
) -> str:
    """Create a scheduled task. SCHEDULE is a 5-field cron expression.

    Parameters
    ----------
    name
        A label for the task.
    command
        The shell command to run.
    schedule
        A 5-field cron expression, ``minute hour day-of-month month day-of-week``.
    cwd
        Directory to run the command in. Defaults to the server's own directory.
    timezone
        IANA zone the cron is read in, for example ``Europe/Paris``. Defaults to the server's zone.
    disabled
        Create the task paused instead of enabled.
    """
    with runtime._client() as client:
        task = client.create_schedule(name, command, schedule, cwd=cwd, timezone=timezone, enabled=not disabled)
    return emit(task, f"created {_schedule_line(task)}")


@schedule_app.command(name="update")
@safe
def schedule_update(
    schedule_id: str,
    *,
    name: str | None = None,
    command: str | None = None,
    schedule: str | None = None,
    cwd: str | None = None,
    timezone: str | None = None,
    enable: bool = False,
    disable: bool = False,
) -> str:
    """Update a scheduled task's fields, or enable/disable it.

    Parameters
    ----------
    schedule_id
        The task id, as shown by ``schedule list``.
    name
        New label.
    command
        New shell command.
    schedule
        New 5-field cron expression.
    cwd
        New working directory.
    timezone
        New IANA zone the cron is read in.
    enable
        Turn the task's schedule on.
    disable
        Turn the task's schedule off.
    """
    fields: dict[str, Any] = {
        "name": name,
        "command": command,
        "schedule": schedule,
        "cwd": cwd,
        "timezone": timezone,
    }
    if enable:
        fields["enabled"] = True
    if disable:
        fields["enabled"] = False
    with runtime._client() as client:
        task = client.update_schedule(schedule_id, **fields)
    return emit(task, _schedule_text(task))


@schedule_app.command(name="delete")
@safe
def schedule_delete(schedule_id: str) -> str:
    """Delete a scheduled task and its run history.

    Parameters
    ----------
    schedule_id
        The task id, as shown by ``schedule list``.
    """
    with runtime._client() as client:
        client.delete_schedule(schedule_id)
    return emit({"deleted": schedule_id}, f"deleted {schedule_id}")


@schedule_app.command(name="run")
@safe
def schedule_run(schedule_id: str) -> str:
    """Run a scheduled task now, in the background.

    Parameters
    ----------
    schedule_id
        The task id, as shown by ``schedule list``.
    """
    with runtime._client() as client:
        run = client.run_schedule(schedule_id)
    return emit(run, f"started run {run['id']}")


@schedule_app.command(name="runs")
@safe
def schedule_runs(schedule_id: str | None = None, limit: int = 20) -> str:
    """Show run history: one task's, or every task's when no id is given.

    Parameters
    ----------
    schedule_id
        Limit the history to this task. Omit it for every task's runs, newest first.
    limit
        Maximum number of runs to show.
    """
    with runtime._client() as client:
        if schedule_id:
            runs = client.schedule_runs(schedule_id, limit=limit)
        else:
            runs = client.schedule_executions(limit=limit)
    return emit(runs, _join(runs, _schedule_run_text))
