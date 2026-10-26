"""The managed transport: this server runs the tool and supplies its endpoint."""

import io
import subprocess
import sys

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


def test_the_tool_writes_to_the_console_running_the_server(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    monkeypatch.setattr(managed_tools.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    calls: list[tuple[list[str], dict]] = []

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return _Process(command)

    monkeypatch.setattr(managed_tools.subprocess, "Popen", fake_popen)
    manager = managed_tools.ManagedToolManager()

    manager.start()

    ((command, kwargs),) = calls
    assert command == ["ghx", "serve", "--host", "127.0.0.1", "--port", "8080"]
    # Piped streams, so the lines can be reprinted on the console that runs the
    # server with the tool's name in front; stdin stays closed so the tool never
    # reads the terminal.
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE
    assert kwargs["stdin"] is subprocess.DEVNULL
    # Without this, a Python tool would block-buffer the output we just piped.
    assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"


def test_relayed_lines_name_the_tool_they_came_from():
    stream = io.StringIO("Serving ghx cache at http://127.0.0.1:8080\nno newline at end")
    out = io.StringIO()

    managed_tools._relay(stream, out, "[ghx] ")

    assert out.getvalue() == ("[ghx] Serving ghx cache at http://127.0.0.1:8080\n[ghx] no newline at end\n")


def test_a_tool_that_dies_has_its_last_lines_relayed(monkeypatch, capsys):
    """End to end over a real process: both streams, prefixed, nothing dropped."""
    monkeypatch.setattr(managed_tools.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    server = managed_tools.ManagedToolServer("ghx")
    server.command = [
        sys.executable,
        "-c",
        "import sys; print('out line'); print('err line', file=sys.stderr)",
    ]

    assert server.start() is True
    # Let the process run to completion first; stopping then drains whatever it
    # wrote before it went away.
    server.process.wait(timeout=10)
    server.stop()

    captured = capsys.readouterr()
    assert "[ghx] out line" in captured.out
    assert "[ghx] err line" in captured.err


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


def test_restart_replaces_the_running_process(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)
    manager.start()

    assert manager.restart("ghx") is True

    # The old process is stopped and the same command is started again, so a
    # new binary or the tool's own config is picked up.
    assert spawn.processes[0].terminated is True
    assert spawn.commands == [
        ["ghx", "serve", "--host", "127.0.0.1", "--port", "8080"],
        ["ghx", "serve", "--host", "127.0.0.1", "--port", "8080"],
    ]
    assert manager.servers["ghx"].alive


def test_restart_starts_a_tool_that_never_came_up(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    # Nothing was started yet, so there is no process to stop first.
    assert manager.restart("ghx") is True
    assert len(spawn.commands) == 1


def test_restart_leaves_a_tool_this_server_does_not_run(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "cli")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    assert manager.restart("ghx") is None
    assert spawn.commands == []


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
