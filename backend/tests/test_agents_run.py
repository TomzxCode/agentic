"""Run execution: model selection, session acquisition, and the run loop."""

import asyncio
from types import SimpleNamespace

import pytest
from acp import RequestError

from agentic.agents import runner
from agentic.models.agents import Harness


@pytest.mark.asyncio
async def test_apply_model_selects_the_configured_model():
    calls: list[tuple] = []

    class FakeConn:
        async def set_config_option(self, config_id, session_id, value):
            calls.append((config_id, session_id, value))
            return SimpleNamespace()

    assert await runner._apply_model(FakeConn(), "s1", None) == (None, None)
    assert calls == []
    # A response that reports no config options still names the requested model.
    assert await runner._apply_model(FakeConn(), "s1", "zai-coding-plan/glm-5.3") == (
        "zai-coding-plan/glm-5.3",
        None,
    )
    assert calls == [("model", "s1", "zai-coding-plan/glm-5.3")]


@pytest.mark.asyncio
async def test_apply_model_reports_a_harness_that_rejects_it():
    class FakeConn:
        async def set_config_option(self, config_id, session_id, value):
            raise RequestError.method_not_found("session/set_config_option")

    model, message = await runner._apply_model(FakeConn(), "s1", "nope")
    assert model is None
    assert message  # the harness's error is surfaced rather than swallowed


def test_session_model_reads_the_model_config_option():
    def response(options):
        return SimpleNamespace(config_options=options)

    model_option = SimpleNamespace(id="model", category="model", current_value="zai-coding-plan/glm-5.3")
    assert runner._session_model(response([model_option])) == "zai-coding-plan/glm-5.3"
    # A harness that picks another id for it is understood by category.
    renamed = SimpleNamespace(id="engine", category="model", current_value="m2")
    assert runner._session_model(response([renamed])) == "m2"
    # Any other option is not the model, and a harness that reports none is read
    # as saying nothing rather than as naming a default.
    thinking = SimpleNamespace(id="thought_level", category="thought_level", current_value="high")
    assert runner._session_model(response([thinking])) is None
    assert runner._session_model(response([])) is None
    assert runner._session_model(SimpleNamespace(config_options=None)) is None


class _FakeSpawn:
    def __init__(self, conn, process):
        self.conn = conn
        self.process = process

    async def __aenter__(self):
        return self.conn, self.process

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_run_agent_selects_the_model_over_acp_not_a_cli_flag(monkeypatch):
    captured: dict = {}

    class FakeConn:
        async def initialize(self, **kwargs):
            return SimpleNamespace(agent_info=None)

        async def new_session(self, cwd):
            return SimpleNamespace(session_id="sess-1")

        async def set_config_option(self, config_id, session_id, value):
            captured["model"] = (config_id, session_id, value)
            return SimpleNamespace()

        async def prompt(self, session_id, prompt):
            return SimpleNamespace(stop_reason="end_turn", usage=None)

    class FakeProcess:
        returncode = 0

        async def wait(self):
            return 0

        def terminate(self):
            return None

    def fake_spawn(client, command, *args, **kwargs):
        captured["command"] = command
        captured["args"] = args
        return _FakeSpawn(FakeConn(), FakeProcess())

    monkeypatch.setattr(runner, "spawn_agent_process", fake_spawn)

    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    harness = Harness(name="h", command="opencode", args=["acp"], model="zai-coding-plan/glm-5.3")
    result = await runner.run_agent(
        run_id="r1",
        harness=harness,
        cwd=".",
        prompt="hi",
        publish=collect,
        cancel_event=asyncio.Event(),
    )

    # The model is a session config option, never a command-line flag: `opencode acp`
    # rejects `--model` and would fail to start.
    assert captured["command"] == "opencode"
    assert captured["args"] == ("acp",)
    assert captured["model"] == ("model", "sess-1", "zai-coding-plan/glm-5.3")
    assert result["session_id"] == "sess-1"
    # The run names its model up front, so a live transcript can show it before
    # the first token arrives.
    assert result["model"] == "zai-coding-plan/glm-5.3"
    assert [e["type"] for e in events] == ["model"]
    assert events[0]["text"] == "zai-coding-plan/glm-5.3"


@pytest.mark.asyncio
async def test_run_agent_reports_the_model_the_session_already_uses(monkeypatch):
    """A harness that selects no model still says which one answers."""

    class FakeConn:
        async def initialize(self, **kwargs):
            return SimpleNamespace(agent_info=None)

        async def new_session(self, cwd):
            option = SimpleNamespace(id="model", category="model", current_value="opencode/its-own-default")
            return SimpleNamespace(session_id="sess-2", config_options=[option])

        async def prompt(self, session_id, prompt):
            return SimpleNamespace(stop_reason="end_turn", usage=None)

    class FakeProcess:
        returncode = 0

        async def wait(self):
            return 0

        def terminate(self):
            return None

    monkeypatch.setattr(runner, "spawn_agent_process", lambda *a, **k: _FakeSpawn(FakeConn(), FakeProcess()))

    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    harness = Harness(name="h", command="opencode", args=["acp"], model=None)
    result = await runner.run_agent(
        run_id="r2",
        harness=harness,
        cwd=".",
        prompt="hi",
        publish=collect,
        cancel_event=asyncio.Event(),
    )

    assert result["model"] == "opencode/its-own-default"
    assert [(e["type"], e["text"]) for e in events] == [("model", "opencode/its-own-default")]


class _FakeConn:
    """A stand-in ACP connection for ``_acquire_session``."""

    def __init__(self, new_id: str = "ses_new", resume_error: Exception | None = None) -> None:
        self.new_id = new_id
        self.resume_error = resume_error
        self.resumed: list[str] = []
        self.created = 0

    async def resume_session(self, *, session_id: str, cwd: str) -> None:
        if self.resume_error is not None:
            raise self.resume_error
        self.resumed.append(session_id)

    async def new_session(self, *, cwd: str) -> SimpleNamespace:
        self.created += 1
        return SimpleNamespace(session_id=self.new_id)


@pytest.mark.asyncio
async def test_acquire_session_creates_a_new_session_without_a_resume_id():
    conn = _FakeConn(new_id="ses_fresh")
    assert await runner._acquire_session(conn, ".", None) == ("ses_fresh", None)
    assert conn.created == 1 and conn.resumed == []


@pytest.mark.asyncio
async def test_acquire_session_resumes_when_asked():
    conn = _FakeConn()
    assert await runner._acquire_session(conn, ".", "ses_prev") == ("ses_prev", None)
    assert conn.resumed == ["ses_prev"] and conn.created == 0


@pytest.mark.asyncio
async def test_acquire_session_falls_back_when_resume_fails():
    conn = _FakeConn(new_id="ses_fresh", resume_error=RuntimeError("gone"))
    assert await runner._acquire_session(conn, ".", "ses_missing") == ("ses_fresh", None)
    assert conn.created == 1
