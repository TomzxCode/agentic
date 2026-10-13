"""The SAQ-backed run queue: enqueue, process, cancel, and reconcile."""

import asyncio

import pytest
from saq import Status
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from agentic import agents as agents_mod
from agentic import jobs
from agentic.db import create_db_and_tables, engine
from agentic.models import AgentEvent, AgentRun, RunStatus, Task, TimelineEvent, utcnow


def _make_run(
    *,
    status: RunStatus = RunStatus.queued,
    kind: str = "chat",
    prompt: str = "p",
    cwd: str = "/tmp/opencode",
) -> tuple[str, str]:
    create_db_and_tables()
    with Session(engine) as session:
        task = Task(title="queue test")
        session.add(task)
        session.commit()
        session.refresh(task)
        run = AgentRun(task_id=task.id, kind=kind, prompt=prompt, cwd=cwd, status=status)
        session.add(run)
        session.commit()
        session.refresh(run)
        return task.id, run.id


def _delete_task(task_id: str) -> None:
    with Session(engine) as session:
        run_ids = [r.id for r in session.exec(select(AgentRun).where(AgentRun.task_id == task_id)).all()]
        if run_ids:
            session.exec(sa_delete(AgentEvent).where(col(AgentEvent.run_id).in_(run_ids)))
        session.exec(sa_delete(AgentRun).where(col(AgentRun.task_id) == task_id))
        session.exec(sa_delete(TimelineEvent).where(col(TimelineEvent.task_id) == task_id))
        session.exec(sa_delete(Task).where(col(Task.id) == task_id))
        session.commit()


def test_slack_generate_title_only_for_untitled_or_placeholder():
    create_db_and_tables()
    with Session(engine) as session:
        task = Task(title="Slack thread")
        session.add(task)
        session.commit()
        session.refresh(task)
        assert jobs._slack_generate_title(task.id) is True
        task.title = "My title"
        session.add(task)
        session.commit()
        task_id = task.id
    assert jobs._slack_generate_title(task_id) is False
    # A missing task is treated as untitled.
    assert jobs._slack_generate_title("does-not-exist") is True
    _delete_task(task_id)


@pytest.mark.asyncio
async def test_enqueue_run_creates_a_queued_job():
    task_id, run_id = _make_run()
    try:
        await jobs.enqueue_run(run_id)
        queue = await jobs.get_queue()
        job = await queue.job(run_id)
        assert job is not None and job.status == Status.QUEUED
        assert job.function == jobs.PROCESS_RUN
        assert await jobs.cancel_run(run_id) is True
        aborted = await queue.job(run_id)
        assert aborted is not None and aborted.status == Status.ABORTED
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_cancel_run_without_a_job_is_false():
    assert await jobs.cancel_run("no-such-run") is False


@pytest.mark.asyncio
async def test_process_run_executes_the_agent(monkeypatch):
    task_id, run_id = _make_run(kind="chat", prompt="do it", cwd="/tmp/opencode")
    calls: list = []

    async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
        calls.append((run_id, cwd, prompt))
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None and run.status == RunStatus.running
            run.status = RunStatus.succeeded
            run.ended_at = utcnow()
            session.add(run)
            session.commit()

    monkeypatch.setattr(agents_mod, "execute_run", fake_execute_run)
    try:
        await jobs.process_run({}, run_id)
        assert calls == [(run_id, "/tmp/opencode", "do it")]
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_process_run_summarizes_a_slack_run(monkeypatch):
    task_id, run_id = _make_run(kind="summarize_slack", prompt="summarize")
    seen: dict = {}

    async def fake_summary(*, run_id, task_id, harness_id, cwd, prompt, cancel_event, generate_title):
        seen["generate_title"] = generate_title

    monkeypatch.setattr(agents_mod, "execute_slack_summary", fake_summary)
    try:
        # The task is titled "queue test" (not the placeholder), so no rename.
        await jobs.process_run({}, run_id)
        assert seen == {"generate_title": False}
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_process_run_refreshes_context(monkeypatch):
    task_id, run_id = _make_run(kind="refresh_context", prompt="refresh")
    seen: dict = {}

    async def fake_refresh(*, run_id, task_id, harness_id, cwd, prompt, cancel_event):
        seen["task_id"] = task_id

    monkeypatch.setattr(agents_mod, "execute_context_refresh", fake_refresh)
    try:
        await jobs.process_run({}, run_id)
        assert seen == {"task_id": task_id}
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_process_run_leaves_status_on_cancellation(monkeypatch):
    # A CancelledError is SAQ's signal to abort or retry the job; the run status is
    # the API's to set on a user cancel, so the worker does not touch it.
    task_id, run_id = _make_run(kind="chat")

    async def cancelled(*, run_id, harness_id, cwd, prompt, cancel_event):
        raise asyncio.CancelledError

    monkeypatch.setattr(agents_mod, "execute_run", cancelled)
    try:
        with pytest.raises(asyncio.CancelledError):
            await jobs.process_run({}, run_id)
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None and run.status == RunStatus.running
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_worker_processes_an_enqueued_run(monkeypatch):
    task_id, run_id = _make_run(kind="chat", prompt="hello")

    async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None
            run.status = RunStatus.succeeded
            run.ended_at = utcnow()
            session.add(run)
            session.commit()

    monkeypatch.setattr(agents_mod, "execute_run", fake_execute_run)
    queue = await jobs.get_queue()
    await jobs.enqueue_run(run_id)
    worker = jobs.create_worker(queue, concurrency=1)
    worker.burst = True
    worker.max_burst_jobs = 1
    worker.dequeue_timeout = 0.5
    try:
        await worker.start()
    finally:
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None and run.status == RunStatus.succeeded
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_reconcile_runs_fails_orphans_and_keeps_live_jobs():
    orphan_task, orphan_run = _make_run(status=RunStatus.running)
    live_task, live_run = _make_run(status=RunStatus.queued)
    try:
        await jobs.enqueue_run(live_run)
        assert await jobs.reconcile_runs() >= 1

        with Session(engine) as session:
            orphan = session.get(AgentRun, orphan_run)
            live = session.get(AgentRun, live_run)
            assert orphan is not None and orphan.status == RunStatus.failed
            assert orphan.error == "Interrupted before a worker finished it"
            # The queued job belongs to a live worker slot, so it is untouched.
            assert live is not None and live.status == RunStatus.queued
    finally:
        await jobs.cancel_run(live_run)
        _delete_task(orphan_task)
        _delete_task(live_task)
