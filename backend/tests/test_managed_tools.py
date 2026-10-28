"""The managed transport: this server runs the tool and supplies its endpoint."""

import io
import socket
import subprocess
import sys

import pytest

from agentic.config import settings
from agentic.services import managed_tools

# The real probes, restored by the tests that exercise them: the rest of the
# suite must not touch the machine's ports or wait on a real bind.
REAL_ANSWERING = managed_tools._answering
REAL_PORT_AVAILABLE = managed_tools._port_available


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


@pytest.fixture(autouse=True)
def _fake_network(monkeypatch):
    """Keep the start loop off the machine's real ports.

    The preferred port counts as free and a started process counts as answering,
    unless a test says otherwise. The start loop still checks that the process is
    alive, so a test can drive the retry by handing back a dead process. The
    generated token is fixed so the expected commands are stable.
    """
    monkeypatch.setattr(managed_tools, "_port_available", lambda port: True)
    monkeypatch.setattr(managed_tools, "_answering", lambda port: True)
    monkeypatch.setattr(managed_tools.secrets, "token_urlsafe", lambda n: "t0ken")


def _command(tool: str, port: int) -> list[str]:
    return [tool, "serve", "--host", "0.0.0.0", "--port", str(port), "--rpc-token", "t0ken"]


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
    """Records the commands the manager starts, and hands back a process.

    ``dies`` lists the zero-based starts whose process exits at once, the way a
    serve process that cannot bind does.
    """

    def __init__(self, dies=()):
        self.commands = []
        self.processes = []
        self.dies = set(dies)

    def __call__(self, command):
        process = _Process(command)
        if len(self.commands) in self.dies:
            process._poll = 1
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
    assert spawn.commands == [_command("ghx", 8080)]
    assert manager.endpoint("ghx") == ("http://127.0.0.1:8080/rpc", "t0ken")
    # The transport is per tool: slackx stays where it was.
    assert manager.endpoint("slackx") is None
    assert [command[0] for command in spawn.commands] == ["ghx"]


def test_slackx_managed_uses_its_own_port(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "managed")
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    assert spawn.commands == [_command("slackx", 8280)]
    assert manager.endpoint("slackx") == ("http://127.0.0.1:8280/rpc", "t0ken")


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
    assert command == _command("ghx", 8080)
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

    # Spawn only: the process is not a serve mode, so it exits instead of
    # answering, and start() would rightly call that a failed start and retry.
    assert server._spawn_process() is True
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
    assert manager.endpoint("ghx") == ("http://127.0.0.1:8080/rpc", "t0ken")


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
        _command("ghx", 8080),
        _command("ghx", 8080),
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
    assert manager.endpoint("slackx") == ("http://127.0.0.1:8280/rpc", "t0ken")


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
    assert manager.endpoint("ghx") == ("http://127.0.0.1:8080/rpc", "t0ken")


def test_tools_this_server_does_not_run_are_never_managed():
    manager = managed_tools.ManagedToolManager()
    assert manager.manages("git") is False
    assert manager.endpoint("git") is None


# Ports
#
# A managed process owns a port but not a fixed one: the tool's preferred port
# is used when it is free, and a process that cannot bind is retried on another.


def test_the_preferred_port_is_used_when_it_is_free():
    assert managed_tools._free_port(8080, set()) == 8080


def test_a_port_it_already_tried_is_not_offered_again():
    assert managed_tools._free_port(8080, {8080}) != 8080


def test_a_busy_preferred_port_falls_back_to_a_free_one(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    monkeypatch.setattr(managed_tools, "_port_available", lambda port: False)
    spawn = _Spawn()
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    assert len(spawn.commands) == 1
    port = manager.servers["ghx"].port
    assert port != 8080
    assert manager.endpoint("ghx") == (f"http://127.0.0.1:{port}/rpc", "t0ken")


def test_answering_detects_a_listening_port(monkeypatch):
    monkeypatch.setattr(managed_tools, "_answering", REAL_ANSWERING)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert managed_tools._answering(port) is True
    # Nothing listens there any more, which is what a serve process that died
    # looks like to the start loop.
    assert managed_tools._answering(port) is False


def test_port_available_matches_a_real_bind(monkeypatch):
    monkeypatch.setattr(managed_tools, "_port_available", REAL_PORT_AVAILABLE)
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        assert managed_tools._port_available(port) is False
    assert managed_tools._port_available(port) is True


def test_a_process_that_exits_while_starting_is_retried_on_another_port(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    ports = iter([8080, 18081])
    monkeypatch.setattr(managed_tools, "_free_port", lambda preferred, exclude: next(ports))
    spawn = _Spawn(dies={0})
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    manager.start()

    assert spawn.commands == [
        _command("ghx", 8080),
        _command("ghx", 18081),
    ]
    assert manager.servers["ghx"].alive
    # The endpoint follows the port the surviving process took, so calls do not
    # go to whatever holds the preferred one.
    assert manager.endpoint("ghx") == ("http://127.0.0.1:18081/rpc", "t0ken")


def test_a_tool_that_never_binds_is_reported_as_not_started(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    ports = iter([8080, 18081, 18082])
    monkeypatch.setattr(managed_tools, "_free_port", lambda preferred, exclude: next(ports))
    spawn = _Spawn(dies={0, 1, 2})
    manager = managed_tools.ManagedToolManager(spawn=spawn)

    assert manager.restart("ghx") is False

    assert len(spawn.commands) == managed_tools.START_ATTEMPTS
    server = manager.servers["ghx"]
    assert server.process is None
    # With nothing listening, the endpoint stays on the tool's preferred port.
    assert manager.endpoint("ghx") == ("http://127.0.0.1:8080/rpc", "t0ken")


def test_the_web_ui_url_follows_the_port_the_process_bound(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    monkeypatch.setattr(managed_tools, "_free_port", lambda preferred, exclude: 18081)
    manager = managed_tools.ManagedToolManager(spawn=_Spawn())
    manager.start()
    monkeypatch.setattr(managed_tools, "managed_tools", manager)

    assert managed_tools.serve_url("ghx") == "http://127.0.0.1:18081"


def test_link_url_keeps_the_configured_host_and_takes_the_bound_port(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    monkeypatch.setattr(managed_tools, "_free_port", lambda preferred, exclude: 18081)
    manager = managed_tools.ManagedToolManager(spawn=_Spawn())
    manager.start()

    # The host is how the user reaches this machine; the port is the one the
    # process bound, so a stale configured port never ends up in a link.
    assert manager.link_url("ghx", "http://squirtle:8010") == "http://squirtle:18081"
    # Scheme and path are kept, and a URL without a port gains one.
    assert manager.link_url("ghx", "https://ghx.local/") == "https://ghx.local:18081/"
    # Nothing configured means the loopback URL.
    assert manager.link_url("ghx", "") == "http://127.0.0.1:18081"


def test_status_reports_the_port_links_use(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    monkeypatch.setattr(managed_tools, "_free_port", lambda preferred, exclude: 18081)
    manager = managed_tools.ManagedToolManager(spawn=_Spawn())
    manager.start()

    assert manager.status() == [
        {
            "tool": "ghx",
            "running": True,
            "port": 18081,
            "url": "http://127.0.0.1:18081",
        }
    ]


def test_status_reports_a_tool_that_did_not_start(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    spawn = _Spawn(dies={0, 1, 2})
    manager = managed_tools.ManagedToolManager(spawn=spawn)
    manager.start()

    # Nothing answers, so the port shown is the preferred one it will try next.
    assert manager.status() == [
        {
            "tool": "ghx",
            "running": False,
            "port": 8080,
            "url": "http://127.0.0.1:8080",
        }
    ]
