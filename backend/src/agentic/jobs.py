"""Durable agent-run queue and worker, backed by SAQ.

Agent runs are enqueued as SAQ jobs instead of in-process asyncio tasks, so a
run survives an API restart and is executed by a worker process
(``agentic-server worker``). The default backend is a SQLite queue next to the
application database; SAQ also accepts ``redis://`` and ``postgres://`` URLs.

The job key is the ``AgentRun`` id, so a task points at exactly one job and a
run can be cancelled or reconciled without a side table.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, cast

import structlog
from saq import Job, Queue, Status, Worker
from saq.types import PartialTimersDict

from .config import settings

log = structlog.get_logger(__name__)

# The name the worker registers and the API enqueues.
PROCESS_RUN = "process_run"

ACTIVE_STATUSES = {Status.NEW, Status.QUEUED, Status.ACTIVE, Status.ABORTING}

_queue: Queue | None = None


async def get_queue() -> Queue:
    """The process-wide queue, connected on first use."""
    global _queue
    if _queue is None:
        queue = Queue.from_url(settings.queue_dsn)
        await queue.connect()
        _queue = queue
    return _queue


async def close_queue() -> None:
    global _queue
    if _queue is not None:
        with contextlib.suppress(Exception):
            await _queue.disconnect()
        _queue = None


async def enqueue_run(run_id: str) -> Job | None:
    """Queue a run for a worker. The job key is the run id, so enqueue is idempotent."""
    queue = await get_queue()
    return await queue.enqueue(
        Job(
            function=PROCESS_RUN,
            key=run_id,
            kwargs={"run_id": run_id},
            timeout=settings.job_timeout,
            heartbeat=settings.job_heartbeat,
            retries=settings.job_retries,
        )
    )


async def cancel_run(run_id: str) -> bool:
    """Abort a queued or running job. True when a live job was aborted."""
    queue = await get_queue()
    job = await queue.job(run_id)
    if job is None or job.status not in ACTIVE_STATUSES:
        return False
    await queue.abort(job, error="Cancelled by user")
    return True


def _slack_generate_title(task_id: str) -> bool:
    """Name an untitled task, or one still holding the import placeholder."""
    from sqlmodel import Session

    from .db import engine
    from .models.tasks import Task
    from .services.prompts import SLACK_PLACEHOLDER_TITLE

    with Session(engine) as session:
        task = session.get(Task, task_id)
    return task is None or not task.title.strip() or task.title == SLACK_PLACEHOLDER_TITLE


async def _heartbeat(job: Job) -> None:
    """Touch the job while it runs so a dead worker's job is swept and retried."""
    while True:
        await asyncio.sleep(settings.job_heartbeat)
        with contextlib.suppress(Exception):
            await job.update()


async def process_run(ctx: dict[str, Any], run_id: str) -> None:
    """SAQ entrypoint: execute one AgentRun to completion."""
    from sqlmodel import Session

    from .agents import runner
    from .db import engine
    from .models.agents import AgentRun
    from .models.base import RunStatus, utcnow

    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            log.warning("queued run no longer exists", run_id=run_id)
            return
        run.status = RunStatus.running
        run.started_at = utcnow()
        session.add(run)
        session.commit()
        kind = run.kind
        harness_id = run.harness_id
        cwd = run.cwd or str(settings.worktree_root)
        prompt = run.prompt
        task_id = run.task_id

    cancel_event = asyncio.Event()
    job = ctx.get("job")
    heartbeat = asyncio.create_task(_heartbeat(job)) if job is not None and settings.job_heartbeat else None
    try:
        if kind == "refresh_context":
            await runner.execute_context_refresh(
                run_id=run_id,
                task_id=task_id,
                harness_id=harness_id,
                cwd=cwd,
                prompt=prompt,
                cancel_event=cancel_event,
            )
        elif kind == "summarize_slack":
            await runner.execute_slack_summary(
                run_id=run_id,
                task_id=task_id,
                harness_id=harness_id,
                cwd=cwd,
                prompt=prompt,
                cancel_event=cancel_event,
                generate_title=_slack_generate_title(task_id),
            )
        else:
            await runner.execute_run(
                run_id=run_id, harness_id=harness_id, cwd=cwd, prompt=prompt, cancel_event=cancel_event
            )
    finally:
        # A CancelledError is left to propagate: SAQ either marks the job aborted
        # (a user cancel, which the API already recorded on the run) or retries it
        # (a worker shutdown), and a retry resumes the session.
        if heartbeat is not None:
            heartbeat.cancel()


async def reconcile_runs() -> int:
    """Fail queued/running rows whose job is gone or already terminal.

    Runs left behind by an API or worker restart stay ``running`` otherwise. A
    row whose job is still active belongs to a live worker and is left alone.
    """
    from sqlmodel import Session, col, select

    from .db import engine
    from .models.agents import AgentRun
    from .models.base import RunStatus, utcnow

    queue = await get_queue()
    recovered = 0
    with Session(engine) as session:
        stale = session.exec(
            select(AgentRun).where(col(AgentRun.status).in_([RunStatus.queued, RunStatus.running]))
        ).all()
        for run in stale:
            job = await queue.job(run.id)
            if job is not None and job.status in ACTIVE_STATUSES:
                continue
            run.status = RunStatus.failed
            run.error = "Interrupted before a worker finished it"
            run.ended_at = utcnow()
            session.add(run)
            recovered += 1
        if recovered:
            session.commit()
    if recovered:
        log.info("marked interrupted runs as failed", count=recovered)
    return recovered


def create_worker(queue: Queue, concurrency: int | None = None) -> Worker:
    """A SAQ worker that processes agent runs."""
    # SAQ's PartialTimersDict inherit-the-required-keys typing quirk requires a cast.
    timers = cast("PartialTimersDict", {"sweep": settings.worker_sweep})
    return Worker(
        queue=queue,
        functions=[process_run],
        concurrency=concurrency or settings.worker_concurrency,
        timers=timers,
    )


async def run_worker(concurrency: int | None = None) -> None:
    """Prepare the database and run a worker until interrupted."""
    from sqlmodel import Session

    from .agents.harnesses import seed_harnesses
    from .db import create_db_and_tables, engine

    create_db_and_tables()
    with Session(engine) as session:
        seed_harnesses(session)
    queue = await get_queue()
    worker = create_worker(queue, concurrency=concurrency)
    try:
        await worker.start()
    finally:
        await close_queue()
