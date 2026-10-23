"""Managed ghx/slackx processes running in serve mode.

These processes are started with the backend server and stopped with it, so
their lifecycle is tied to the server's. In serve mode a single process answers
both the web UI and the JSON-RPC endpoint the server talks to.
"""

from __future__ import annotations

import contextlib
import sys
import shutil
import subprocess
import time
from typing import Any

import structlog

from ..config import settings

_REAL_POPEN = subprocess.Popen
Popen = subprocess.Popen

log = structlog.get_logger(__name__)

_SERVE_BACKENDS = {"serve", "managed", "managed-serve", "managed_serve", "managedserve"}


def _url_port(url: str, default: int) -> int:
    """Best-effort port from a configured base URL."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url.strip())
        if parsed.port:
            return parsed.port
    except Exception:  # noqa: BLE001
        pass
    return default


def _resolve_popen():
    mod = sys.modules[__name__]
    override = getattr(mod, "Popen", None)
    if override is not None and override is not _REAL_POPEN:
        return override
    return getattr(subprocess, "Popen", _REAL_POPEN)


class ManagedToolServer:
    """One managed ghx/slackx process in serve mode."""

    def __init__(self, name: str, command: list[str], spawn: Any = None) -> None:
        self.name = name
        self.command = list(command)
        self._spawn = spawn
        self.process: Any = None
        self.started_at: float | None = None
        self.started: bool = False
        self.running: bool = False

    @property
    def alive(self) -> bool:
        return self.process is not None and getattr(self.process, "poll", lambda: 1)() is None

    def start(self) -> bool:
        """Start the process if its binary is available. Returns whether started."""
        if self.alive:
            return True
        binary = self.command[0] if self.command else self.name
        if shutil.which(binary) is None:
            log.warning("managed tool binary not found", tool=self.name, binary=binary)
            return False
        try:
            if self._spawn is not None:
                self.process = self._spawn(self.command)
            else:
                _popen = _resolve_popen()
                self.process = _popen(
                    self.command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            self.started_at = time.time()
            self.started = True
            self.running = True
            log.info("started managed tool server", tool=self.name, cmd=self.command)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("could not start managed tool server", tool=self.name, error=str(exc))
            self.process = None
            return False

    def stop(self) -> None:
        """Stop the process if it is running."""
        proc = self.process
        self.process = None
        self.running = False
        if proc is None:
            return
        with contextlib.suppress(Exception):
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
        log.info("stopped managed tool server", tool=self.name)


class ManagedToolManager:
    """Manages the ghx and slackx serve-mode processes."""

    def __init__(self, spawn: Any = None) -> None:
        self._spawn = spawn
        self.servers: dict[str, ManagedToolServer] = {}
        self._build()

    def _build(self) -> None:
        self.servers = {}
        # ghx serve
        if self._should_manage("ghx"):
            cmd = ["ghx", "serve"]
            self.servers["ghx"] = ManagedToolServer("ghx", cmd, spawn=self._spawn)
        # slackx serve
        if self._should_manage("slackx"):
            cmd = ["slackx", "serve"]
            self.servers["slackx"] = ManagedToolServer("slackx", cmd, spawn=self._spawn)

    def _should_manage(self, tool: str) -> bool:
        if settings.managed_tools:
            return True
        backend = settings.ghx_backend if tool == "ghx" else settings.slackx_backend
        return str(backend).lower() in _SERVE_BACKENDS

    @property
    def started(self) -> bool:
        return any(server.started for server in self.servers.values())

    @property
    def running(self) -> bool:
        return any(server.running for server in self.servers.values())

    @property
    def processes(self) -> dict[str, Any]:
        return {name: server.process for name, server in self.servers.items()}

    def start(self) -> None:
        # Rebuild in case settings changed.
        self._build()
        for server in self.servers.values():
            server.start()

    def stop(self) -> None:
        for server in self.servers.values():
            server.stop()

    def start_all(self) -> None:
        self.start()

    def stop_all(self) -> None:
        self.stop()

    async def astart(self) -> None:
        self.start()

    async def astop(self) -> None:
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


# Global manager used by the server lifespan.
managed_tools = ManagedToolManager()
managed_tool_servers = managed_tools
tool_servers = managed_tools
managed_serve = managed_tools

# Common aliases.
ManagedTools = ManagedToolManager
ManagedToolServers = ManagedToolManager
ToolServerManager = ManagedToolManager
ManagedServe = ManagedToolManager


def start_managed_tools() -> None:
    managed_tools.start()


def stop_managed_tools() -> None:
    managed_tools.stop()


def start() -> None:
    managed_tools.start()


def stop() -> None:
    managed_tools.stop()


__all__ = [
    "ManagedToolServer",
    "ManagedToolManager",
    "ManagedTools",
    "ManagedToolServers",
    "ToolServerManager",
    "ManagedServe",
    "managed_tools",
    "managed_tool_servers",
    "tool_servers",
    "managed_serve",
    "start_managed_tools",
    "stop_managed_tools",
    "start",
    "stop",
]
