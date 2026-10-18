"""Context-refresh and Slack-summary entrypoints."""

import asyncio

import pytest
from _agents_helpers import _create_task_and_run, _delete_task
from sqlmodel import Session, select

from agentic.agents import executions
from agentic.agents.runner import persist_event
from agentic.db import engine
from agentic.models.tasks import Task, TimelineEvent

VALID_CONTEXT = '{"summary": "Do the thing.", "next_steps": [{"text": "One", "done": false}]}'
VALID_SUMMARY = '{"title": "Ship the thing", "summary": "They agreed to ship it."}'


@pytest.mark.asyncio
async def test_context_refresh_parses_the_agent_reply(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "message", "text": VALID_CONTEXT, "data": {}})

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_context_refresh(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None
            assert task.summary == "Do the thing."
            assert task.next_steps == [{"text": "One", "done": False}]
            assert task.context_updated_at is not None
            types = [e.type for e in session.exec(select(TimelineEvent).where(TimelineEvent.task_id == task_id)).all()]
            assert "context_updated" in types
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_context_refresh_falls_back_to_thoughts(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "thought", "text": VALID_CONTEXT, "data": {}})

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_context_refresh(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None and task.summary == "Do the thing."
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_context_refresh_records_failure_when_unparseable(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "message", "text": "no json here", "data": {}})

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_context_refresh(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None and task.summary == ""
            types = [e.type for e in session.exec(select(TimelineEvent).where(TimelineEvent.task_id == task_id)).all()]
            assert "context_refresh_failed" in types
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_slack_summary_writes_the_agent_title_and_summary(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "message", "text": VALID_SUMMARY, "data": {}})

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_slack_summary(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None
            assert task.title == "Ship the thing"
            assert task.summary == "They agreed to ship it."
            assert task.context_updated_at is not None
            types = [e.type for e in session.exec(select(TimelineEvent).where(TimelineEvent.task_id == task_id)).all()]
            assert "summary_updated" in types
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_slack_summary_keeps_a_user_supplied_title(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "message", "text": VALID_SUMMARY, "data": {}})

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_slack_summary(
            run_id=run_id,
            task_id=task_id,
            harness_id=None,
            cwd=".",
            prompt="p",
            cancel_event=asyncio.Event(),
            generate_title=False,
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None
            assert task.title == "run test"  # untouched
            assert task.summary == "They agreed to ship it."
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_slack_summary_falls_back_to_thoughts(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "thought", "text": VALID_SUMMARY, "data": {}})

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_slack_summary(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None and task.title == "Ship the thing"
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_slack_summary_keeps_the_title_when_only_a_summary_is_returned(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(
                    session, run_id, {"seq": 1, "type": "message", "text": '{"summary": "Only a summary."}', "data": {}}
                )

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_slack_summary(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None
            assert task.title == "run test"  # no title in the reply, so it stays
            assert task.summary == "Only a summary."
            types = [e.type for e in session.exec(select(TimelineEvent).where(TimelineEvent.task_id == task_id)).all()]
            assert "summary_updated" in types
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_slack_summary_records_failure_when_unparseable(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "message", "text": "no json here", "data": {}})

        monkeypatch.setattr(executions, "execute_run", fake_execute_run)
        await executions.execute_slack_summary(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None and task.summary == ""
            types = [e.type for e in session.exec(select(TimelineEvent).where(TimelineEvent.task_id == task_id)).all()]
            assert "summary_failed" in types
    finally:
        _delete_task(task_id)
