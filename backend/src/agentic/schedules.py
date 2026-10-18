"""Scheduled shell tasks: a cron-driven runner for user-defined commands.

A scheduled task holds a shell command and a 5-field cron expression. The
scheduler loop (started by the API) wakes every ``AGENTIC_SCHEDULED_TASK_TICK``
seconds, finds the enabled tasks whose ``next_run_at`` has passed, advances
their next occurrence, and runs them in the background. Each execution is
recorded as a :class:`ScheduledTaskRun` with its exit code and output tail.

Commands run in the API process, so a script is not durable across a server
restart the way an agent run on the SAQ queue is: an interrupted run is marked
failed on the next startup. That keeps the feature usable with a plain
``agentic-server serve`` and no worker process.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from croniter import croniter
from sqlalchemy import or_
from sqlmodel import Session, col, select
from tzlocal import get_localzone

from .config import settings
from .db import engine
from .models.base import ScheduledRunStatus, utcnow
from .models.schedules import ScheduledTask, ScheduledTaskRun

log = structlog.get_logger(__name__)


def _server_timezone() -> ZoneInfo:
    """The server's local timezone, falling back to UTC when it cannot be read."""
    try:
        zone = get_localzone()
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")
    # Collapse the common names containers report for UTC, so the UI can compare
    # this with the browser's "UTC" instead of treating them as different.
    utc_aliases = {"Etc/UTC", "Etc/GMT", "Etc/UCT", "GMT", "UTC", "Universal", "Zulu"}
    return ZoneInfo("UTC") if str(zone) in utc_aliases else zone


# Cron carries no timezone, so expressions run against the server's wall clock.
# A named zone (not a fixed offset) keeps 09:00 at 09:00 across DST changes.
SERVER_TIMEZONE = _server_timezone()


# Keep at most this many characters of a run's combined output.
MAX_OUTPUT = 20_000

# The scheduled tasks currently executing, so a slow task is not started twice.
_running: set[str] = set()

# Strong references to the background run tasks. The event loop only keeps weak
# ones, so without this a run can be garbage collected before it finishes.
_tasks: set[asyncio.Task[None]] = set()


def _spawn(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def validate_schedule(expression: str) -> str:
    """Return a trimmed cron expression, or raise ``ValueError`` if it is invalid."""
    text = (expression or "").strip()
    if not text:
        raise ValueError("A schedule is required")
    if len(text.split()) != 5:
        raise ValueError("A schedule needs 5 fields: minute hour day-of-month month day-of-week")
    if not croniter.is_valid(text):
        raise ValueError(f"'{text}' is not a valid cron expression")
    return text


def resolve_timezone(name: str | None) -> ZoneInfo:
    """The zone to evaluate cron in; an empty name means the server's zone."""
    text = (name or "").strip()
    if not text:
        return SERVER_TIMEZONE
    try:
        return ZoneInfo(text)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"Unknown timezone: {text}") from exc


def compute_next_run(expression: str, *, base: datetime | None = None, timezone: str | None = None) -> datetime:
    """The first time the expression fires after ``base``, as a UTC datetime.

    Cron carries no timezone, so the expression is evaluated in ``timezone``
    (the server's zone when none is given) and the result is stored as UTC.
    """
    zone = resolve_timezone(timezone)
    reference = (base or utcnow()).astimezone(zone)
    result = croniter(expression, reference).get_next(datetime)
    if result.tzinfo is None:
        result = result.replace(tzinfo=reference.tzinfo)
    return result.astimezone(UTC)


def upcoming_runs(
    expression: str,
    *,
    first: datetime | None = None,
    count: int = 5,
    timezone: str | None = None,
) -> list[datetime]:
    """The next ``count`` occurrences, starting at ``first`` when it is still ahead.

    ``first`` is the task's stored ``next_run_at``, so the preview matches what
    the scheduler will do. A value that has already passed falls back to the
    next occurrence from now.
    """
    now = utcnow()
    runs: list[datetime] = [first] if first is not None and first > now else []
    if not runs:
        runs.append(compute_next_run(expression, base=now, timezone=timezone))
    while len(runs) < count:
        runs.append(compute_next_run(expression, base=runs[-1], timezone=timezone))
    return runs


def create_run(session: Session, task: ScheduledTask) -> ScheduledTaskRun:
    """Insert a running run row and advance the task's schedule.

    The next occurrence is advanced here, before the command starts, so a slow
    or overrunning task is never triggered again for the same occurrence.
    """
    run = ScheduledTaskRun(scheduled_task_id=task.id)
    session.add(run)
    task.last_run_at = utcnow()
    if task.enabled:
        task.next_run_at = compute_next_run(task.schedule, base=task.last_run_at, timezone=task.timezone)
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    session.refresh(run)
    return run


async def execute_run(run_id: str, task_id: str, command: str, cwd: str | None) -> None:
    """Run one command to completion and finalize its run row."""
    from pathlib import Path

    _running.add(task_id)
    try:
        if cwd and not Path(cwd).is_dir():
            exit_code, output = None, f"Working directory does not exist: {cwd}"
        else:
            exit_code, output = await _run_command(command, cwd)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        exit_code, output = None, f"Failed to start: {exc}"
    finally:
        _running.discard(task_id)

    with Session(engine) as session:
        run = session.get(ScheduledTaskRun, run_id)
        if run is None:
            return
        run.exit_code = exit_code
        run.output = output
        run.status = ScheduledRunStatus.succeeded if exit_code == 0 else ScheduledRunStatus.failed
        run.ended_at = utcnow()
        session.add(run)
        session.commit()


async def _run_command(command: str, cwd: str | None) -> tuple[int | None, str]:
    """Run ``command`` through the shell, returning its exit code and output tail."""
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd or None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    timeout = settings.scheduled_task_timeout
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout or None)
    except TimeoutError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return None, f"Timed out after {timeout}s"
    output = stdout.decode("utf-8", "replace")
    if len(output) > MAX_OUTPUT:
        output = "...(truncated)\n" + output[-MAX_OUTPUT:]
    return proc.returncode, output


async def start_run(task_id: str) -> str:
    """Create a run row and execute it in the background; return the run id."""
    with Session(engine) as session:
        task = session.get(ScheduledTask, task_id)
        if task is None:
            raise ValueError(f"Scheduled task {task_id} not found")
        run = create_run(session, task)
        run_id, command, cwd = run.id, task.command, task.cwd
    _spawn(execute_run(run_id, task_id, command, cwd))
    return run_id


async def run_due_once() -> int:
    """Start every enabled scheduled task whose next occurrence has passed."""
    now = utcnow()
    with Session(engine) as session:
        due = session.exec(
            select(ScheduledTask)
            .where(col(ScheduledTask.enabled) == True)  # noqa: E712
            .where(or_(col(ScheduledTask.next_run_at).is_(None), col(ScheduledTask.next_run_at) <= now))
        ).all()
        ids = [task.id for task in due]
    started = 0
    for task_id in ids:
        if task_id in _running:
            continue
        await start_run(task_id)
        started += 1
    return started


async def scheduler_loop() -> None:
    """Tick on a timer and run the scheduled tasks that are due."""
    tick = settings.scheduled_task_tick
    if tick <= 0:
        return
    while True:
        await asyncio.sleep(tick)
        try:
            started = await run_due_once()
        except Exception as exc:  # noqa: BLE001
            log.warning("scheduled task tick failed", error=str(exc))
            continue
        if started:
            log.info("started scheduled tasks", count=started)


def reconcile_scheduled_runs() -> int:
    """Mark runs left ``running`` by a previous process as failed."""
    with Session(engine) as session:
        stale = session.exec(
            select(ScheduledTaskRun).where(col(ScheduledTaskRun.status) == ScheduledRunStatus.running)
        ).all()
        for run in stale:
            run.status = ScheduledRunStatus.failed
            note = "Interrupted before the server finished it"
            run.output = f"{run.output}\n{note}".strip() if run.output else note
            run.ended_at = utcnow()
            session.add(run)
        if stale:
            session.commit()
    if stale:
        log.info("marked interrupted scheduled runs as failed", count=len(stale))
    return len(stale)
