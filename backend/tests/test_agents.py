"""The ACP layer: harness seeding/selection and the client callbacks.

The ACP transport itself (`spawn_agent_process`) is not exercised here; these
tests cover the pure normalization helpers, the client callbacks, and the run
execution loop with `run_agent` stubbed out.
"""

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from acp import Agent, RequestError
from acp.schema import AllowedOutcome, DeniedOutcome, ElicitationMode, PermissionOption, TextContentBlock
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, SQLModel, col, create_engine, select

from agentic import agents as agents_mod
from agentic.agents import (
    AgenticClient,
    _content_text,
    _dump,
    get_harness,
    harness_available,
    persist_event,
    seed_harnesses,
)
from agentic.config import settings
from agentic.db import create_db_and_tables, engine
from agentic.models import AgentEvent, AgentRun, Harness, RunStatus, Task, TimelineEvent

VALID_CONTEXT = '{"summary": "Do the thing.", "next_steps": [{"text": "One", "done": false}]}'

# Throwaway in-memory engines/sessions built by the pure-helper tests; tracked
# here so they are closed at test teardown instead of leaking pooled SQLite
# connections (ResourceWarning).
_fresh_engines: list = []
_fresh_sessions: list = []


def _fresh_session() -> Session:
    fresh_engine = create_engine("sqlite://")
    _fresh_engines.append(fresh_engine)
    SQLModel.metadata.create_all(fresh_engine)
    session = Session(fresh_engine)
    _fresh_sessions.append(session)
    return session


@pytest.fixture(autouse=True)
def _dispose_fresh_engines():
    yield
    while _fresh_sessions:
        _fresh_sessions.pop().close()
    while _fresh_engines:
        _fresh_engines.pop().dispose()


async def _noop(_event: dict) -> None:
    return None


def _create_task_and_run() -> tuple[str, str]:
    create_db_and_tables()
    with Session(engine) as session:
        seed_harnesses(session)
        task = Task(title="run test")
        session.add(task)
        session.commit()
        session.refresh(task)
        run = AgentRun(task_id=task.id, kind="chat", prompt="p")
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


# --- pure helpers ---------------------------------------------------------
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (SimpleNamespace(type="text", text="hello"), "hello"),
        (SimpleNamespace(type="image"), "[image]"),
        (SimpleNamespace(type="audio"), "[audio]"),
        (SimpleNamespace(type="resource_link", name="spec", uri="file:///spec.md"), "[spec](file:///spec.md)"),
        (SimpleNamespace(type="resource", resource=SimpleNamespace(text="body", uri="u")), "body"),
        (SimpleNamespace(type="resource", resource=SimpleNamespace(uri="u")), "[resource u]"),
        (SimpleNamespace(type="unknown"), ""),
    ],
)
def test_content_text_normalizes_each_kind(content, expected):
    assert _content_text(content) == expected


def test_dump_handles_none_and_models():
    assert _dump(None) == {}
    assert _dump(TextContentBlock(type="text", text="hi")) == {"type": "text", "text": "hi"}


def test_harness_available_reports_missing_and_present_commands():
    missing = Harness(id="m", name="m", command="definitely-not-a-real-command-xyz")
    available, detail = harness_available(missing)
    assert available is False and "not found on PATH" in detail

    shell = Harness(id="s", name="s", command="sh")
    available, detail = harness_available(shell)
    assert available is True and detail


def test_seed_harnesses_populates_presets_with_resume_commands():
    session = _fresh_session()
    seed_harnesses(session)
    harnesses = {h.id: h for h in session.exec(select(Harness)).all()}
    assert set(harnesses) == {"opencode", "pi"}
    assert harnesses["opencode"].resume_command == "opencode --session {session}"
    assert harnesses["opencode"].is_default is True
    assert harnesses["pi"].resume_command == "pi --session {session}"


def test_seed_harnesses_backfills_resume_command_by_id_and_name():
    session = _fresh_session()
    session.add(Harness(id="opencode", name="OpenCode", command="opencode"))
    session.add(Harness(id="weird", name="PI", command="pi-acp"))
    session.add(Harness(id="zed", name="zed", command="zed"))
    session.commit()

    seed_harnesses(session)

    opencode = session.get(Harness, "opencode")
    weird = session.get(Harness, "weird")
    zed = session.get(Harness, "zed")
    assert opencode is not None and weird is not None and zed is not None

    assert opencode.resume_command == "opencode --session {session}"
    # Unknown ids fall back to the name lookup, case-insensitively.
    assert weird.resume_command == "pi --session {session}"
    # Nothing known matches, so the column is left as-is.
    assert zed.resume_command is None


def test_get_harness_prefers_explicit_id_then_default_flag():
    session = _fresh_session()
    session.add(Harness(id="a", name="a", command="a"))
    session.add(Harness(id="b", name="b", command="b", is_default=True))
    session.commit()

    assert get_harness(session, "a").id == "a"
    # An unknown id falls back to the harness flagged default.
    assert get_harness(session, "missing").id == "b"
    assert get_harness(session, None).id == "b"


def test_get_harness_uses_settings_default_name(monkeypatch):
    session = _fresh_session()
    session.add(Harness(id="p", name="pi", command="pi"))
    session.add(Harness(id="o", name="opencode", command="opencode"))
    session.commit()

    monkeypatch.setattr(settings, "default_harness", "pi")
    assert get_harness(session, None).id == "p"


def test_get_harness_falls_back_to_first_and_raises_when_empty():
    session = _fresh_session()
    session.add(Harness(id="only", name="only", command="only"))
    session.commit()
    assert get_harness(session, None).id == "only"

    empty = _fresh_session()
    with pytest.raises(RuntimeError):
        get_harness(empty, None)


# --- AgenticClient callbacks ----------------------------------------------
@pytest.mark.asyncio
async def test_session_update_normalizes_each_kind():
    events: list[dict] = []

    async def publish(event: dict) -> None:
        events.append(event)

    client = AgenticClient(cwd=".", publish=publish)

    def chunk(kind: str, text: str) -> SimpleNamespace:
        return SimpleNamespace(session_update=kind, content=TextContentBlock(type="text", text=text))

    await client.session_update("s", chunk("agent_message_chunk", "hi"))
    await client.session_update("s", chunk("agent_thought_chunk", "th"))
    await client.session_update("s", chunk("user_message_chunk", "me"))
    await client.session_update("s", SimpleNamespace(session_update="tool_call", title="Bash"))
    await client.session_update("s", SimpleNamespace(session_update="tool_call_update", title="Bash done"))
    plan = SimpleNamespace(session_update="plan", entries=[TextContentBlock(type="text", text="step")])
    await client.session_update("s", plan)
    await client.session_update("s", SimpleNamespace(session_update="usage_update"))
    await client.session_update("s", SimpleNamespace(session_update="something_new"))

    assert [e["type"] for e in events] == [
        "message",
        "thought",
        "user",
        "tool_call",
        "tool_update",
        "plan",
        "usage",
        "info",
    ]
    # Sequence numbers are assigned in order for the transcript.
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_request_permission_auto_approves_an_allow_option():
    events: list[dict] = []

    async def publish(event: dict) -> None:
        events.append(event)

    client = AgenticClient(cwd=".", publish=publish, auto_approve=True)
    options = [
        PermissionOption(option_id="reject", name="Reject", kind="reject_once"),
        PermissionOption(option_id="ok", name="Allow", kind="allow_once"),
    ]
    response = await client.request_permission("s", SimpleNamespace(title="Bash"), options)
    assert isinstance(response.outcome, AllowedOutcome)
    assert response.outcome.option_id == "ok"
    assert events[0]["type"] == "permission"


@pytest.mark.asyncio
async def test_request_permission_falls_back_and_denies():
    client = AgenticClient(cwd=".", publish=_noop, auto_approve=True)
    # No allow option: the first option is used.
    only_reject = [PermissionOption(option_id="r", name="Reject", kind="reject_once")]
    allowed = await client.request_permission("s", SimpleNamespace(), only_reject)
    assert isinstance(allowed.outcome, AllowedOutcome) and allowed.outcome.option_id == "r"

    # No options at all with auto-approve on is denied.
    assert isinstance((await client.request_permission("s", SimpleNamespace(), [])).outcome, DeniedOutcome)

    # Auto-approve off is always denied.
    manual = AgenticClient(cwd=".", publish=_noop, auto_approve=False)
    deny = await manual.request_permission("s", SimpleNamespace(title="Bash"), only_reject)
    assert isinstance(deny.outcome, DeniedOutcome)


@pytest.mark.asyncio
async def test_read_and_write_text_files(tmp_path):
    (tmp_path / "f.txt").write_text("a\nb\nc\n")
    client = AgenticClient(cwd=str(tmp_path), publish=_noop)

    assert (await client.read_text_file("s", "f.txt")).content == "a\nb\nc\n"
    sliced = await client.read_text_file("s", "f.txt", line=2, limit=1)
    assert sliced.content == "b\n"

    written = await client.write_text_file("s", "sub/g.txt", "hello")
    assert written is not None
    assert (tmp_path / "sub" / "g.txt").read_text() == "hello"


@pytest.mark.asyncio
async def test_unsupported_methods_raise_method_not_found():
    client = AgenticClient(cwd=".", publish=_noop)
    calls = [
        client.create_terminal("s", "ls"),
        client.terminal_output("s", "t"),
        client.release_terminal("s", "t"),
        client.wait_for_terminal_exit("s", "t"),
        client.kill_terminal("s", "t"),
        client.create_elicitation("m", cast("ElicitationMode", "form")),
        client.ext_method("x", {}),
    ]
    for coro in calls:
        with pytest.raises(RequestError):
            await coro

    assert await client.complete_elicitation("e") is None
    assert client.on_connect(cast("Agent", None)) is None
    assert await client.ext_notification("x", {}) is None


def test_persist_event_writes_a_transcript_row():
    task_id, run_id = _create_task_and_run()
    try:
        with Session(engine) as session:
            row = persist_event(session, run_id, {"seq": 3, "type": "tool_call", "text": "x", "data": {"a": 1}})
            assert row.id is not None
            assert row.seq == 3 and row.type == "tool_call" and row.data_json == {"a": 1}
    finally:
        _delete_task(task_id)


# --- run execution --------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_run_succeeds_and_persists_events(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_run_agent(*, run_id, harness, cwd, prompt, publish, cancel_event):
            await publish({"seq": 1, "type": "message", "text": "hello", "data": {"k": "v"}})
            return {"session_id": "ses_1", "stop_reason": "end_turn"}

        monkeypatch.setattr(agents_mod, "run_agent", fake_run_agent)
        await agents_mod.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())

        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None
            assert run.status == RunStatus.succeeded
            assert run.session_id == "ses_1"
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

        async def fake_run_agent(*, run_id, harness, cwd, prompt, publish, cancel_event):
            return {"session_id": "ses_2", "stop_reason": "cancelled"}

        monkeypatch.setattr(agents_mod, "run_agent", fake_run_agent)
        await agents_mod.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())

        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            assert run is not None and run.status == RunStatus.cancelled
    finally:
        _delete_task(task_id)


@pytest.mark.asyncio
async def test_execute_run_records_failure(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_run_agent(*, run_id, harness, cwd, prompt, publish, cancel_event):
            raise RuntimeError("boom")

        monkeypatch.setattr(agents_mod, "run_agent", fake_run_agent)
        await agents_mod.execute_run(run_id=run_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event())

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
    await agents_mod.execute_run(
        run_id="does-not-exist", harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
    )


@pytest.mark.asyncio
async def test_context_refresh_parses_the_agent_reply(monkeypatch):
    task_id, run_id = _create_task_and_run()
    try:

        async def fake_execute_run(*, run_id, harness_id, cwd, prompt, cancel_event):
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "message", "text": VALID_CONTEXT, "data": {}})

        monkeypatch.setattr(agents_mod, "execute_run", fake_execute_run)
        await agents_mod.execute_context_refresh(
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

        monkeypatch.setattr(agents_mod, "execute_run", fake_execute_run)
        await agents_mod.execute_context_refresh(
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

        monkeypatch.setattr(agents_mod, "execute_run", fake_execute_run)
        await agents_mod.execute_context_refresh(
            run_id=run_id, task_id=task_id, harness_id=None, cwd=".", prompt="p", cancel_event=asyncio.Event()
        )

        with Session(engine) as session:
            task = session.get(Task, task_id)
            assert task is not None and task.summary == ""
            types = [e.type for e in session.exec(select(TimelineEvent).where(TimelineEvent.task_id == task_id)).all()]
            assert "context_refresh_failed" in types
    finally:
        _delete_task(task_id)
