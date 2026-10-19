"""The warm ACP session pool: what it holds and what it answers."""

import asyncio
from types import SimpleNamespace

import pytest

from agentic.agents import pool as pool_module
from agentic.agents.pool import HarnessSessionPool, WarmSession, fingerprint
from agentic.models.agents import Harness


def _model_option(current="m1", values=(("m1", "Model One"), ("m2", "Model Two"))):
    return SimpleNamespace(
        id="model",
        category="model",
        current_value=current,
        options=[SimpleNamespace(value=value, name=name) for value, name in values],
    )


class FakeConn:
    def __init__(self, options=None):
        self.options = options if options is not None else []
        self.initialized = False

    async def initialize(self, **kwargs):
        self.initialized = True
        return SimpleNamespace(agent_info=None)

    async def new_session(self, cwd):
        return SimpleNamespace(session_id="sess-1", config_options=self.options)


class FakeProcess:
    def __init__(self):
        self.returncode = None

    def terminate(self):
        self.returncode = 0


class FakeSpawn:
    """Stand-in for ``spawn_agent_process``: an async context manager."""

    def __init__(self, conn, process):
        self.conn = conn
        self.process = process

    async def __aenter__(self):
        return self.conn, self.process

    async def __aexit__(self, *exc):
        self.process.returncode = 0
        return False


def _spawn_with(conn, process=None):
    def spawn(client, command, *args, **kwargs):
        return FakeSpawn(conn, process or FakeProcess())

    return spawn


def _harness(harness_id="opencode2", **kwargs):
    fields = {"name": "OpenCode v2", "command": "opencode2", "args": ["acp"]}
    fields.update(kwargs)
    return Harness(id=harness_id, **fields)


@pytest.mark.asyncio
async def test_warm_session_reads_the_models_the_harness_offers():
    conn = FakeConn([_model_option()])
    session = WarmSession(_harness(), ".", spawn=_spawn_with(conn))
    await session.open()
    try:
        assert conn.initialized
        assert session.current == "m1"
        assert session.choices == [
            {"value": "m1", "name": "Model One"},
            {"value": "m2", "name": "Model Two"},
        ]
        assert session.alive
    finally:
        await session.close()
    assert not session.alive


@pytest.mark.asyncio
async def test_pool_answers_the_default_harness_from_the_session_it_holds():
    pool = HarnessSessionPool(spawn=_spawn_with(FakeConn([_model_option()])))
    harness = _harness()
    await pool._open(harness)
    try:
        models = await pool.models(harness)
        assert models.live is True
        assert models.current == "m1"
        assert [choice["value"] for choice in models.choices] == ["m1", "m2"]
    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_pool_reads_a_harness_it_does_not_hold_on_demand_and_reuses_it():
    spawned: list[str] = []

    def spawn(client, command, *args, **kwargs):
        spawned.append(command)
        return FakeSpawn(FakeConn([_model_option()]), FakeProcess())

    pool = HarnessSessionPool(spawn=spawn)
    harness = _harness("pi")
    first = await pool.models(harness)
    assert first.live is False
    assert [choice["value"] for choice in first.choices] == ["m1", "m2"]

    # The result is cached, so a second ask does not spawn the harness again.
    second = await pool.models(harness)
    assert second.choices == first.choices
    assert spawned == ["opencode2"]
    await pool.stop()


@pytest.mark.asyncio
async def test_pool_reports_a_harness_that_will_not_start():
    def spawn(*args, **kwargs):
        raise RuntimeError("no such command")

    pool = HarnessSessionPool(spawn=spawn)
    models = await pool.models(_harness("pi"))
    assert models.choices == []
    assert models.live is False
    assert "no such command" in models.error


@pytest.mark.asyncio
async def test_pool_closes_a_harness_that_fails_after_it_starts():
    class BadConn(FakeConn):
        async def initialize(self, **kwargs):
            raise RuntimeError("handshake failed")

    process = FakeProcess()
    pool = HarnessSessionPool(spawn=_spawn_with(BadConn(), process))
    models = await pool.models(_harness("pi"))
    assert "handshake failed" in models.error
    # The spawned process is closed rather than left behind.
    assert process.returncode == 0


@pytest.mark.asyncio
async def test_pool_closes_the_process_when_an_open_is_cancelled():
    class SlowConn(FakeConn):
        async def initialize(self, **kwargs):
            raise asyncio.CancelledError

    process = FakeProcess()
    pool = HarnessSessionPool(spawn=_spawn_with(SlowConn(), process))
    with pytest.raises(asyncio.CancelledError):
        await pool._open(_harness())
    assert process.returncode == 0
    assert pool._session is None


@pytest.mark.asyncio
async def test_pool_keeps_a_session_up_for_the_default_harness(monkeypatch):
    harness = _harness()
    monkeypatch.setattr(pool_module, "_default_harness", lambda: harness)
    monkeypatch.setattr(pool_module, "IDLE_POLL", 0.01)

    pool = HarnessSessionPool(spawn=_spawn_with(FakeConn([_model_option()])))
    pool.start()
    try:
        for _ in range(200):
            if pool._session is not None:
                break
            await asyncio.sleep(0.01)
        assert pool._session is not None
        models = await pool.models(harness)
        assert models.live is True
    finally:
        await pool.stop()
    assert pool._session is None


def test_fingerprint_changes_with_the_harnesss_command_and_model():
    harness = _harness(model="zai/glm")
    same = _harness(model="zai/glm")
    assert fingerprint(harness) == fingerprint(same)
    assert fingerprint(harness) != fingerprint(_harness(model="other/model"))
    assert fingerprint(harness) != fingerprint(_harness(command="opencode"))
