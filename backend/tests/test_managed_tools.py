"""The managed transport: this server runs the tool and supplies its endpoint."""

import pytest

from agentic.config import settings
from agentic.services import managed_tools


@pytest.fixture(autouse=True)
def _transport_settings(monkeypatch):
    """Stored transport overrides, replaced by a per-test dict.

    The manager resolves the transport the same way ``services.shell`` does:
    the environment value first, the Settings page's stored value over it.
    """
    stored: dict[str, str] = {}
    monkeypatch.setattr("agentic.settings_store.get_rpc_overrides", lambda: dict(stored))
    monkeypatch.setattr(settings, "managed_tools", False)
    yield stored


class _Process:
    """A spawned serve process, without a real one behind it."""

    def __init__(self, command):
        self.command = command
        self.terminated = False
        self.killed = False
        self._poll = None

    def poll(self):
        return self._poll

    def terminate(self):
        self.terminated = True
        self._poll = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


class _Spawn:
    """Records the commands the manager starts, and hands back a process."""

    def __init__(self):
        self.commands = []
        self.processes = []

    def __call__(self, command):
        process = _Process(command)
        self.commands.append(command)
        self.processes.append(process)
        return process


def test_managed_starts_the_serve_process_and_supplies_its_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    # The process is bound on loopback at the port its serve mode defaults to,
    # so its JSON-RPC endpoint is <port>/rpc.
    assert spawn.commands == [["ghx", "serve", "--host", "127.0.0.1", "--port", "8080"]]
    assert manager.endpoint("ghx") == ("http://127.0.0.1:8080/rpc", "")
    # The transport is per tool: slackx stays where it was.
    assert manager.endpoint("slackx") is None
    assert [command[0] for command in spawn.commands] == ["ghx"]


def test_slackx_managed_uses_its_own_port(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "managed")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    assert spawn.commands == [["slackx", "serve", "--host", "127.0.0.1", "--port", "8280"]]
    assert manager.endpoint("slackx") == ("http://127.0.0.1:8280/rpc", "")


def test_cli_and_rpc_transports_start_nothing(monkeypatch):
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)
    for backend in ("cli", "rpc"):
        monkeypatch.setattr(settings, "ghx_backend", backend)
        manager.sync()
        assert manager.endpoint("ghx") is None
    assert spawn.commands == []


def test_a_stored_override_wins_over_the_environment(monkeypatch, _transport_settings):
    monkeypatch.setattr(settings, "ghx_backend", "cli")
    _transport_settings["ghx_backend"] = "managed"
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    assert [command[0] for command in spawn.commands] == ["ghx"]
    assert manager.endpoint("ghx") == ("http://127.0.0.1:8080/rpc", "")


def test_switching_away_from_managed_stops_the_process(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)
    manager.start()

    # A change on the Settings page applies without a restart.
    monkeypatch.setattr(settings, "ghx_backend", "cli")
    manager.sync()

    assert spawn.processes[0].terminated is True
    assert manager.endpoint("ghx") is None
    assert manager.servers == {}


def test_the_all_tools_flag_manages_both(monkeypatch):
    monkeypatch.setattr(settings, "managed_tools", True)
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    assert [command[0] for command in spawn.commands] == ["ghx", "slackx"]
    assert manager.endpoint("slackx") == ("http://127.0.0.1:8280/rpc", "")


def test_an_explicit_rpc_server_is_kept_over_the_flag(monkeypatch):
    monkeypatch.setattr(settings, "managed_tools", True)
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    # The flag fills in for a user who configures nothing; it does not take over
    # a server that is deliberately pointed elsewhere.
    assert manager.endpoint("ghx") is None
    assert [command[0] for command in spawn.commands] == ["slackx"]


def test_a_missing_binary_leaves_the_endpoint_without_a_process(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    monkeypatch.setattr(managed_tools.shutil, "which", lambda name: None)
    manager = managed_tools.ManagedToolManager()

    manager.start()

    # The server must still start; the failed tool shows up as a refused call.
    assert manager.servers["ghx"].process is None
    assert manager.endpoint("ghx") == ("http://127.0.0.1:8080/rpc", "")


def test_tools_this_server_does_not_run_are_never_managed():
    manager = managed_tools.ManagedToolManager()
    assert manager.manages("git") is False
    assert manager.endpoint("git") is None
