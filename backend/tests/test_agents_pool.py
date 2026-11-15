"""The warm ACP session pool: what it holds and what it answers."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col

from agentic.agents import pool as pool_module
from agentic.agents.pool import (
    HarnessSessionPool,
    StoredSession,
    WarmSession,
    fingerprint,
    store_session,
    stored_session,
)
from agentic.db import create_db_and_tables, engine
from agentic.models.agents import Harness
from agentic.models.system import Setting


@pytest.fixture(autouse=True)
def _clean_warm_sessions():
    """Give the session bookkeeping a schema and leave no row behind."""
    create_db_and_tables()
    yield
    with Session(engine) as session:
        session.exec(sa_delete(Setting).where(col(Setting.key).startswith(pool_module.WARM_SESSION_PREFIX)))
        session.commit()


def _model_option(current="m1", values=(("m1", "Model One"), ("m2", "Model Two"))):
    return SimpleNamespace(
        id="model",
        category="model",
        current_value=current,
        options=[SimpleNamespace(value=value, name=name) for value, name in values],
    )


class FakeConn:
    def __init__(self, options=None, *, resumable=True, loadable=True):
        self.options = options if options is not None else []
        self.resumable = resumable
        self.loadable = loadable
        self.initialized = False
        self.opened = 0
        self.resumed: list[str] = []
        self.loaded: list[str] = []

    async def initialize(self, **kwargs):
        self.initialized = True
        return SimpleNamespace(agent_info=None)

    async def new_session(self, cwd):
        self.opened += 1
        return SimpleNamespace(session_id=f"sess-{self.opened}", config_options=self.options)

    async def resume_session(self, session_id, cwd):
        self.resumed.append(session_id)
        if not self.resumable:
            raise RuntimeError("session/resume not supported")
        return SimpleNamespace(session_id=session_id, config_options=self.options)

    async def load_session(self, cwd, session_id):
        self.loaded.append(session_id)
        if not self.loadable:
            raise RuntimeError("session not found")
        return SimpleNamespace(config_options=self.options)


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
    fields: dict[str, Any] = {"name": "OpenCode v2", "command": "opencode2", "args": ["acp"]}
    fields.update(kwargs)
    return Harness(id=harness_id, **fields)


def _cwd():
    """The directory the pool spawns a harness in."""
    from agentic.config import settings

    return settings.worktree_root


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
async def test_pool_holds_the_session_it_opens_and_reuses_it():
    spawned: list[str] = []

    def spawn(client, command, *args, **kwargs):
        spawned.append(command)
        return FakeSpawn(FakeConn([_model_option()]), FakeProcess())

    pool = HarnessSessionPool(spawn=spawn)
    harness = _harness("pi")
    first = await pool.models(harness)
    assert first.live is True
    assert [choice["value"] for choice in first.choices] == ["m1", "m2"]

    # The session is held open, so a second ask spawns the harness again only
    # when the harness changed.
    second = await pool.models(harness)
    assert second.choices == first.choices
    assert spawned == ["opencode2"]
    await pool.stop()


@pytest.mark.asyncio
async def test_a_restarted_process_reuses_the_recorded_session():
    harness = _harness()
    first = FakeConn([_model_option()])
    await HarnessSessionPool(spawn=_spawn_with(first)).models(harness)
    assert first.opened == 1
    recorded = stored_session(harness.id)
    assert recorded is not None and recorded.session_id == "sess-1"

    # A new process (the API restarted) spawns the harness again but resumes the
    # session instead of asking for another one.
    second = FakeConn([_model_option()])
    models = await HarnessSessionPool(spawn=_spawn_with(second)).models(harness)
    assert second.resumed == ["sess-1"]
    assert second.opened == 0
    assert models.live is True
    assert [choice["value"] for choice in models.choices] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_a_changed_harness_opens_a_new_session_and_records_it():
    harness = _harness()
    store_session(harness.id, StoredSession("sess-recorded", fingerprint(harness), str(_cwd())))
    changed = _harness(model="zai/glm")
    conn = FakeConn([_model_option()])
    await HarnessSessionPool(spawn=_spawn_with(conn)).models(changed)
    assert conn.resumed == []
    assert conn.opened == 1
    recorded = stored_session(changed.id)
    assert recorded is not None and recorded.session_id == "sess-1"


@pytest.mark.asyncio
async def test_a_harness_without_session_resume_reuses_its_session_through_load():
    harness = _harness("pi")
    store_session(harness.id, StoredSession("sess-recorded", fingerprint(harness), str(_cwd())))
    conn = FakeConn([_model_option()], resumable=False)
    models = await HarnessSessionPool(spawn=_spawn_with(conn)).models(harness)
    assert conn.resumed == ["sess-recorded"]
    assert conn.loaded == ["sess-recorded"]
    assert conn.opened == 0
    assert models.live is True
    assert [choice["value"] for choice in models.choices] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_a_session_the_harness_no_longer_has_is_replaced_and_recorded():
    harness = _harness()
    store_session(harness.id, StoredSession("sess-gone", fingerprint(harness), str(_cwd())))
    conn = FakeConn([_model_option()], resumable=False, loadable=False)
    models = await HarnessSessionPool(spawn=_spawn_with(conn)).models(harness)
    assert conn.resumed == ["sess-gone"]
    assert conn.loaded == ["sess-gone"]
    assert conn.opened == 1
    assert models.live is True
    recorded = stored_session(harness.id)
    assert recorded is not None and recorded.session_id == "sess-1"


@pytest.mark.asyncio
async def test_pool_reopens_when_the_harness_changes_and_closes_the_old_session():
    processes: list[FakeProcess] = []

    def spawn(client, command, *args, **kwargs):
        process = FakeProcess()
        processes.append(process)
        return FakeSpawn(FakeConn([_model_option()]), process)

    pool = HarnessSessionPool(spawn=spawn)
    harness = _harness("pi")
    await pool.models(harness)
    changed = _harness("pi", model="zai/glm")
    models = await pool.models(changed)
    assert models.live is True
    assert len(processes) == 2
    assert pool._sessions["pi"].fingerprint == fingerprint(changed)
    await pool.stop()
    # The replaced session's process was closed, not left behind.
    assert processes[0].returncode == 0


@pytest.mark.asyncio
async def test_pool_reports_a_harness_that_will_not_start():
    def spawn(*args, **kwargs):
        raise RuntimeError("no such command")

    pool = HarnessSessionPool(spawn=spawn)
    models = await pool.models(_harness("pi"))
    assert models.choices == []
    assert models.live is False
    assert models.error is not None and "no such command" in models.error


@pytest.mark.asyncio
async def test_pool_closes_a_harness_that_fails_after_it_starts():
    class BadConn(FakeConn):
        async def initialize(self, **kwargs):
            raise RuntimeError("handshake failed")

    process = FakeProcess()
    pool = HarnessSessionPool(spawn=_spawn_with(BadConn(), process))
    models = await pool.models(_harness("pi"))
    assert models.error is not None and "handshake failed" in models.error
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
    assert pool._sessions == {}


@pytest.mark.asyncio
async def test_pool_keeps_a_session_up_for_the_default_harness(monkeypatch):
    harness = _harness()
    monkeypatch.setattr(pool_module, "_default_harness", lambda: harness)
    monkeypatch.setattr(pool_module, "IDLE_POLL", 0.01)

    pool = HarnessSessionPool(spawn=_spawn_with(FakeConn([_model_option()])))
    pool.start()
    try:
        for _ in range(200):
            if harness.id in pool._sessions:
                break
            await asyncio.sleep(0.01)
        assert harness.id in pool._sessions
        models = await pool.models(harness)
        assert models.live is True
    finally:
        await pool.stop()
    assert pool._sessions == {}


def test_forget_session_drops_the_record() -> None:
    harness = _harness()
    store_session(harness.id, StoredSession("sess-1", fingerprint(harness), str(_cwd())))
    assert stored_session(harness.id) is not None
    pool_module.forget_session(harness.id)
    assert stored_session(harness.id) is None


def test_fingerprint_changes_with_the_harnesss_command_and_model():
    harness = _harness(model="zai/glm")
    same = _harness(model="zai/glm")
    assert fingerprint(harness) == fingerprint(same)
    assert fingerprint(harness) != fingerprint(_harness(model="other/model"))
    assert fingerprint(harness) != fingerprint(_harness(command="opencode"))
