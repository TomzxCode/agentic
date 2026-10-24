"""Managed ghx/slackx serve-mode processes.

A tool whose transport is ``managed`` is started by this server and stopped with
it, so its lifecycle is tied to the server's. The tool's serve mode answers both
its web UI and the JSON-RPC endpoint this server calls, so choosing ``managed``
replaces the URL and token a user would otherwise supply for ``rpc`` mode.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import time
from typing import Any

import structlog

from ..config import settings

log = structlog.get_logger(__name__)

# The tools this server can run itself, in the order they start.
TOOLS = ("ghx", "slackx")

# The transport value that makes this server run a tool instead of the user.
MANAGED = "managed"

# The port each tool's serve mode binds on loopback. A managed process is
# started on it, so its JSON-RPC endpoint is <base>/rpc on that port.
SERVE_PORTS = {"ghx": 8080, "slackx": 8280}


def serve_url(tool: str) -> str:
    """The base URL a managed tool's serve process answers on.

    Its web UI is there and so is its JSON-RPC endpoint, at ``<url>/rpc``.
    """
    return f"http://127.0.0.1:{SERVE_PORTS[tool]}"


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
        port = SERVE_PORTS[tool]
        # Loopback only: the endpoint needs no token, and both binaries refuse
        # a non-loopback bind without one anyway.
        self.command = [tool, "serve", "--host", "127.0.0.1", "--port", str(port)]
        self._spawn = spawn
        self.process: Any = None
        self.started_at: float | None = None

    @property
    def alive(self) -> bool:
        return self.process is not None and getattr(self.process, "poll", lambda: 1)() is None

    def start(self) -> bool:
        """Start the process if its binary is available. Returns whether started."""
        if self.alive:
            return True
        if self._spawn is None and shutil.which(self.tool) is None:
            log.warning("managed tool binary not found", tool=self.tool, binary=self.tool)
            return False
        try:
            if self._spawn is not None:
                self.process = self._spawn(self.command)
            else:
                self.process = subprocess.Popen(
                    self.command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            self.started_at = time.time()
            log.info("started managed tool", tool=self.tool, cmd=self.command)
            return True
        except Exception as exc:  # noqa: BLE001 - a tool that cannot start must not stop the server
            log.warning("could not start managed tool", tool=self.tool, error=str(exc))
            self.process = None
            return False

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
        """The (JSON-RPC URL, token) of a managed tool, or None when it is not managed.

        Nothing comes from the settings: the process this server started is
        bound on loopback, so there is no URL to configure and no token to send.
        """
        if not self.manages(tool, backend):
            return None
        return f"{serve_url(tool)}/rpc", ""

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
