"""The execute_run loop and event persistence."""

import asyncio

import pytest
from _agents_helpers import _create_task_and_run, _delete_task
from sqlmodel import Session, select

from agentic.agents import runner
from agentic.agents.runner import persist_event
from agentic.db import engine
from agentic.models.agents import AgentEvent, AgentRun
from agentic.models.base import RunStatus


def test_persist_event_writes_a_transcript_row():
    task_id, run_id = _create_task_and_run()
    try:
        with Session(engine) as session:
            row = persist_event(session, run_id, {"seq": 3, "type": "tool_call", "text": "x", "data": {"a": 1}})
            assert row.id is not None
            assert row.seq == 3 and row.type == "tool_call" and row.data_json == {"a": 1}
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_execute_run_succeeds_and_persists_events(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_run_agent(*, run_id, harness, cwd, prompt, publish, cancel_event, **kwargs):
            await publish({"seq": 1, "type": "message", "text": "hello", "data": {"k": "v"}})
            return {"session_id": "ses_1", "stop_reason": "end_turn", "model": "zai-coding-plan/glm-5.3"}

        monkeypatch.setattr(runner, "run_agent", fake_run_agent)
        await runner.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())

        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None
            assert run.status == RunStatus.succeeded
            assert run.session_id == "ses_1"
            assert run.model == "zai-coding-plan/glm-5.3"
            assert run.stop_reason == "end_turn"
            assert run.started_at is not None and run.ended_at is not None
            events = session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id)).all()
            assert [(e.type, e.text) for e in events] == [("message", "hello")]
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_execute_run_marks_cancelled(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_run_agent(*, run_id, harness, cwd, prompt, publish, cancel_event, **kwargs):
            return {"session_id": "ses_2", "stop_reason": "cancelled"}

        monkeypatch.setattr(runner, "run_agent", fake_run_agent)
        await runner.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())

        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None and run.status == RunStatus.cancelled
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_execute_run_records_failure(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_run_agent(*, run_id, harness, cwd, prompt, publish, cancel_event, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(runner, "run_agent", fake_run_agent)
        await runner.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())

        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None
            assert run.status == RunStatus.failed
            assert run.error == "boom"
            types = [e.type for e in session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id)).all()]
            assert "error" in types
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_execute_run_with_unknown_run_is_a_noop():
    # No such run: the entrypoint returns quietly (the finally still notifies).
    await runner.execute_run(
        run_id="does-not-exist", harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
    )


@pytest.mark.asyncio
async def test_execute_run_records_the_session_before_the_turn_finishes(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_run_agent(
            *, run_id, harness, cwd, prompt, publish, cancel_event, resume_session_id=None, on_session=None
        ):
            assert on_session is not None
            await on_session("ses_early")
            # The handle is on the row before the harness turn returns.
            with Session(engine) as session:
                row = session.get(AgentRun, run_id)
                assert row is not None and row.session_id == "ses_early"
            return {"session_id": "ses_early", "stop_reason": "end_turn"}

        monkeypatch.setattr(runner, "run_agent", fake_run_agent)
        await runner.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())

        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None and run.session_id == "ses_early" and run.status == RunStatus.succeeded
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_execute_run_resumes_an_existing_session(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None
            run.session_id = "ses_prev"
            session.add(run)
            session.commit()

        seen: dict = {}

        async def fake_run_agent(
            *, run_id, harness, cwd, prompt, publish, cancel_event, resume_session_id=None, on_session=None
        ):
            seen["resume"] = resume_session_id
            return {"session_id": resume_session_id or "ses_new", "stop_reason": "end_turn"}

        monkeypatch.setattr(runner, "run_agent", fake_run_agent)
        await runner.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())
        assert seen == {"resume": "ses_prev"}
    finally:
        _delete_task(task_id)
