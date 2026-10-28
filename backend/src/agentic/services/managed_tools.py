"""Managed ghx/slackx serve-mode processes.

A tool whose transport is ``managed`` is started by this server and stopped with
it, so its lifecycle is tied to the server's. The tool's serve mode answers both
its web UI and the JSON-RPC endpoint this server calls, so choosing ``managed``
replaces the URL and token a user would otherwise supply for ``rpc`` mode.

The tool's output is reprinted on this server's console, one line at a time with
the tool's name in front, so a line from ghx is never mistaken for a line from
slackx or from the server itself.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import structlog

from ..config import settings

log = structlog.get_logger(__name__)

# The tools this server can run itself, in the order they start.
TOOLS = ("ghx", "slackx")

# The transport value that makes this server run a tool instead of the user.
MANAGED = "managed"

# The interface a managed serve process binds. Every interface, so the web UI is
# reachable from another machine, not only from this one. Both tools refuse a
# non-loopback bind without a token, so the command carries one this server
# generates and sends on its JSON-RPC calls.
SERVE_HOST = "0.0.0.0"

# The port each tool's serve mode prefers. A managed process keeps it when it is
# free, so its JSON-RPC endpoint is <preferred>/rpc; when another process already
# holds it, the server picks a free port instead, since the port is an
# implementation detail of a process this server owns.
SERVE_PORTS = {"ghx": 8080, "slackx": 8280}

# How many ports to try for a tool whose serve process exits while starting. The
# usual cause is another process taking the port between the check and the bind.
START_ATTEMPTS = 3

# How long to wait for a started process to answer on its port. A serve process
# that cannot bind exits at once, so a healthy one answers well inside this.
START_TIMEOUT = 2.0


def _port_available(port: int) -> bool:
    """Whether this process could bind *port* on the managed interface.

    Racy on its own (another process can take the port before the child binds),
    so the start loop retries. SO_REUSEADDR matches what the serve processes do,
    which keeps a port in TIME_WAIT from looking taken on a restart.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((SERVE_HOST, port))
        except OSError:
            return False
    return True


def _free_port(preferred: int, exclude: set[int]) -> int:
    """A port to run a serve process on.

    The preferred port when it is free (and not in *exclude*), otherwise one the
    OS assigns. The check is only a hint: the caller retries on another port if
    the child still exits because it lost the race for it.
    """
    if preferred not in exclude and _port_available(preferred):
        return preferred
    for _ in range(100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((SERVE_HOST, 0))
            port = sock.getsockname()[1]
        if port not in exclude:
            return port
    raise OSError("no free port")


def _answering(port: int) -> bool:
    """Whether something accepts a loopback connection on *port* yet."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
            return True
    except OSError:
        return False


def serve_url(tool: str) -> str:
    """The base URL a managed tool's serve process answers on.

    Its web UI is there and so is its JSON-RPC endpoint, at ``<url>/rpc``. That
    is the port the process actually bound once this server started it, and the
    tool's preferred port before that (a busy preferred port falls back to a free
    one).
    """
    return managed_tools.url(tool)


def _relay(stream: Any, out: Any, prefix: str) -> None:
    """Reprint a tool's output on *out*, one prefixed line at a time.

    Runs in its own thread so a tool that writes slowly never blocks the server
    or its sibling stream. The console going away (or the stream closing under
    us) ends the relay quietly: the server keeps running either way.
    """
    try:
        for line in stream:
            text = line.rstrip("\n")
            out.write(f"{prefix}{text}\n")
            out.flush()
    except (OSError, ValueError):
        pass
    finally:
        with contextlib.suppress(Exception):
            stream.close()


def backend_for(tool: str) -> str:
    """A tool's transport: the Settings page's stored value over the environment's.

    Read per call, so a change on the Settings page takes effect without a
    restart, the same way ``services.shell`` reads the transport. A stored empty
    value is no opinion, so the environment's value still applies.
    """
    key = f"{tool}_backend"
    stored = ""
    try:
        # Late import: the settings store reaches back into the fetchers, which
        # import this module.
        from ..settings_store import get_rpc_overrides

        stored = (get_rpc_overrides().get(key) or "").strip()
    except Exception as exc:  # noqa: BLE001 - the environment value still applies
        log.warning("managed tool settings unreadable", error=str(exc))
    return (stored or str(getattr(settings, key, "cli"))).strip().lower()


class ManagedToolServer:
    """One tool running in its serve mode."""

    def __init__(self, tool: str, spawn: Any = None) -> None:
        self.tool = tool
        self.port = SERVE_PORTS[tool]
        # The tool refuses a non-loopback bind without a token, because its
        # JSON-RPC clients can change the cache and run CLI commands. This
        # server generates one and sends it on every call; it is never put in
        # the URL, so item links stay usable without it.
        self.token = secrets.token_urlsafe(32)
        # Bound on every interface, so the web UI is reachable from another
        # machine; both binaries refuse that without the token above.
        self.command = self._serve_command()
        # Every relayed line carries this, so a viewer can tell the tool's own
        # output from the server's.
        self.prefix = f"[{tool}] "
        self._spawn = spawn
        self.process: Any = None
        self.started_at: float | None = None
        self._readers: list[threading.Thread] = []

    def _serve_command(self) -> list[str]:
        return [
            self.tool,
            "serve",
            "--host",
            SERVE_HOST,
            "--port",
            str(self.port),
            "--rpc-token",
            self.token,
        ]

    @property
    def alive(self) -> bool:
        return self.process is not None and getattr(self.process, "poll", lambda: 1)() is None

    def start(self) -> bool:
        """Start the process, on a free port. Returns whether it is serving.

        The preferred port is used when nothing holds it. A serve process that
        cannot bind exits immediately, so the start loop waits for the port to
        answer and, when the process died first, tries another free port. That
        covers both a port taken before the start and one lost to another
        process between the check and the bind.
        """
        if self.alive:
            return True
        if self._spawn is None and shutil.which(self.tool) is None:
            log.warning("managed tool binary not found", tool=self.tool, binary=self.tool)
            return False
        tried: set[int] = set()
        for attempt in range(1, START_ATTEMPTS + 1):
            try:
                port = _free_port(SERVE_PORTS[self.tool], tried)
            except OSError as exc:
                log.warning("no free port for managed tool", tool=self.tool, error=str(exc))
                return False
            tried.add(port)
            # The port changes the command, so rebuild it for every fresh port.
            # A caller that supplied its own command keeps it when the port did
            # not change (tests drive the output relay that way).
            if port != self.port:
                self.port = port
                self.command = self._serve_command()
            if not self._spawn_process():
                return False
            if self._wait_until_answering():
                self.started_at = time.time()
                log.info("started managed tool", tool=self.tool, cmd=self.command)
                return True
            log.warning(
                "managed tool exited while starting",
                tool=self.tool,
                port=port,
                attempt=attempt,
            )
            self._discard_process()
        # Nothing is listening, so report the tool as not started and keep the
        # endpoint on the port it would normally use.
        self.port = SERVE_PORTS[self.tool]
        self.command = self._serve_command()
        return False

    def _spawn_process(self) -> bool:
        """Spawn the serve process. False when it could not be spawned at all."""
        try:
            if self._spawn is not None:
                self.process = self._spawn(self.command)
            else:
                # The tool's output is piped and reprinted with its name in front,
                # so it lands on the console running this server (`make run-dev`)
                # and stays distinguishable from the server's own logs. stdin
                # stays closed: the tool never reads the terminal.
                self.process = subprocess.Popen(
                    self.command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    # A piped Python tool block-buffers its stdout, which would
                    # hold its startup lines back until it exits.
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
            self._relay_output()
            return True
        except Exception as exc:  # noqa: BLE001 - a tool that cannot start must not stop the server
            log.warning("could not start managed tool", tool=self.tool, error=str(exc))
            self.process = None
            return False

    def _wait_until_answering(self) -> bool:
        """Wait for the process to accept a connection on its port.

        Returns False as soon as the process exits first, which is what a failed
        bind looks like. A process still alive at the deadline counts as started:
        it may only be slow, and killing and retrying would make that worse.
        """
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if not self.alive:
                return False
            if _answering(self.port):
                # Something answers on the port. Give a child that lost the race
                # for it the moment it needs to exit, so a connection served by
                # the process that holds the port is not mistaken for this one.
                time.sleep(0.05)
                return self.alive
            time.sleep(0.02)
        return self.alive

    def _discard_process(self) -> None:
        """Forget a process that exited while starting, draining its output."""
        proc = self.process
        self.process = None
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
        self._drain_readers()

    def _drain_readers(self) -> None:
        for thread in self._readers:
            thread.join(timeout=2)
        self._readers.clear()

    def _relay_output(self) -> None:
        """Reprint the process's stdout and stderr, each on its own thread."""
        proc = self.process
        for name, out in (("stdout", sys.stdout), ("stderr", sys.stderr)):
            stream = getattr(proc, name, None)
            if stream is None:
                continue
            thread = threading.Thread(target=_relay, args=(stream, out, self.prefix), daemon=True)
            thread.start()
            self._readers.append(thread)

    def stop(self) -> None:
        """Stop the process if it is running."""
        proc = self.process
        self.process = None
        if proc is None:
            return
        with contextlib.suppress(Exception):
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 - a wedged process is killed instead
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
        # Drains whatever the tool wrote before it died, so a stopping tool does
        # not drop its last lines (its error message, typically).
        self._drain_readers()
        log.info("stopped managed tool", tool=self.tool)


class ManagedToolManager:
    """Runs the tools whose transport is ``managed``, and supplies their endpoint."""

    def __init__(self, spawn: Any = None) -> None:
        self._spawn = spawn
        self.servers: dict[str, ManagedToolServer] = {}

    def manages(self, tool: str, backend: str | None = None) -> bool:
        """Whether this server runs ``tool`` instead of the user running it.

        An explicit ``rpc`` keeps pointing at the user's own server even when
        the all-tools flag is on, since that flag exists to save a user who runs
        nothing by hand. ``backend`` is the tool's resolved transport when the
        caller already read it.
        """
        if tool not in SERVE_PORTS:
            return False
        if backend is None:
            backend = backend_for(tool)
        if backend == MANAGED:
            return True
        return backend != "rpc" and settings.managed_tools

    def endpoint(self, tool: str, backend: str | None = None) -> tuple[str, str] | None:
        """The (JSON-RPC URL, bearer token) of a managed tool, or None.

        Nothing comes from the settings: this server generated the token its
        serve process requires and bound it on the managed interface, so there
        is no URL or token for the user to configure.
        """
        if not self.manages(tool, backend):
            return None
        server = self.servers.get(tool)
        token = server.token if server is not None else ""
        return f"{self.url(tool)}/rpc", token

    def url(self, tool: str) -> str:
        """The base URL of a tool's serve process.

        The port this manager started it on, or the tool's preferred port when
        this process does not run it (or has not started it yet).
        """
        return f"http://127.0.0.1:{self.port(tool)}"

    def port(self, tool: str) -> int:
        """The port a managed tool answers on (see :meth:`url`)."""
        server = self.servers.get(tool)
        return server.port if server is not None else SERVE_PORTS[tool]

    def link_url(self, tool: str, configured: str = "") -> str:
        """The URL item links use for a managed tool.

        A configured URL supplies the host, since the user may reach this machine
        by name from another device; its port is ignored in favour of the one the
        process actually bound, so links follow a fallback port instead of a
        stale configured one. The scheme and path are kept.
        """
        base = self.url(tool)
        if not configured:
            return base
        parts = urlsplit(configured.strip())
        host = parts.hostname or ""
        if not host:
            return base
        if ":" in host:
            host = f"[{host}]"
        netloc = f"{host}:{self.port(tool)}"
        return urlunsplit((parts.scheme or "http", netloc, parts.path, parts.query, parts.fragment))

    def status(self) -> list[dict[str, Any]]:
        """Where each tool this server runs answers, for the Settings page.

        A tool without a server here is not managed by this process, so it is
        left out: the page shows the URL and port only for tools whose process
        this server owns. ``running`` is false for one that failed to start, and
        ``port`` is then the preferred port it will try next.
        """
        return [
            {"tool": tool, "running": server.alive, "port": server.port, "url": self.url(tool)}
            for tool, server in self.servers.items()
        ]

    def restart(self, tool: str) -> bool | None:
        """Stop and start a managed tool's serve process.

        Returns whether it came back up, or None when this server does not run
        the tool. A process this server never started is started here, so the
        button works even after a failed start.
        """
        if not self.manages(tool):
            return None
        server = self.servers.get(tool)
        if server is None:
            server = ManagedToolServer(tool, self._spawn)
            self.servers[tool] = server
        server.stop()
        return server.start()

    def sync(self) -> None:
        """Start the tools that should run and stop the ones that should not."""
        desired = [tool for tool in TOOLS if self.manages(tool)]
        for tool in list(self.servers):
            if tool not in desired:
                self.servers.pop(tool).stop()
        for tool in desired:
            server = self.servers.get(tool)
            if server is None:
                server = ManagedToolServer(tool, self._spawn)
                self.servers[tool] = server
            server.start()

    def start(self) -> None:
        self.sync()

    def stop(self) -> None:
        for server in self.servers.values():
            server.stop()
        self.servers.clear()


# Global manager used by the server lifespan and the settings page.
managed_tools = ManagedToolManager()
