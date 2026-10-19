#!/usr/bin/env python
"""Run the Agentic dev stack, picking free ports when the defaults are taken.

`make run` / `make run-dev` start the API, the agent-run worker, the Vite dev
server, and the tray. Running that set from several checkouts (one per worktree,
say) would otherwise collide on the fixed defaults, so each service takes the
first free port at or above its default and the pieces are wired to each other:
the Vite proxy targets the chosen API port and the tray opens the chosen
frontend port.

    python scripts/dev.py              # like `make run`
    python scripts/dev.py --reload     # like `make run-dev`
    python scripts/dev.py --api-port 8600 --frontend-port 5173   # pin both

Passing an explicit port disables the search: the process fails to start if that
port is already taken.

The API and the dev server are essential: if either exits, the whole stack is
torn down. The worker and the tray are not, so a tray that cannot start (no
display) leaves the API and dev server running.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"

DEFAULT_API_PORT = 8600
DEFAULT_FRONTEND_PORT = 5173


@dataclass
class Service:
    """One process of the dev stack."""

    name: str
    cmd: list[str]
    cwd: Path
    essential: bool = True
    env: dict[str, str] = field(default_factory=dict)


def find_free_port(start: int, attempts: int = 100) -> int:
    """Return the first port at or above *start* that nothing is listening on."""
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # SO_REUSEADDR lets a port in TIME_WAIT count as free, the same way
            # uvicorn and Node treat it; a live listener still makes bind fail.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                continue
        return port
    raise SystemExit(f"no free port between {start} and {start + attempts - 1}")


def console_script(name: str) -> str:
    """Resolve a console script from the running virtualenv when possible."""
    candidate = Path(sys.executable).parent / name
    return str(candidate) if candidate.exists() else name


def has_display() -> bool:
    """Whether this session can host the tray's GUI (macOS, or an X/Wayland session)."""
    if sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _raise_keyboard_interrupt(signum: int, frame: object) -> None:
    """Turn SIGTERM into the same teardown path as Ctrl+C."""
    raise KeyboardInterrupt


def build_services(args: argparse.Namespace, api_port: int, frontend_port: int) -> list[Service]:
    api = Service(
        name="api",
        cmd=[
            console_script("agentic-server"),
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            str(api_port),
            *(["--reload"] if args.reload else []),
        ],
        cwd=ROOT,
    )
    # --strictPort makes Vite fail instead of silently taking the next port, so
    # the frontend URL handed to the tray is always the one actually served.
    frontend = Service(
        name="frontend",
        cmd=["npm", "run", "dev", "--", "--port", str(frontend_port), "--strictPort"],
        cwd=FRONTEND_DIR,
        # The dev server proxies /api, /docs, /saq and /openapi.json to the API.
        env={**os.environ, "AGENTIC_API": f"http://127.0.0.1:{api_port}"},
    )
    services = [api, frontend]
    if not args.no_worker:
        services.append(
            Service(
                name="worker",
                cmd=[console_script("agentic-server"), "worker"],
                cwd=ROOT,
                # Agent runs stall without it, but the dev server still works.
                essential=False,
            )
        )
    if not args.no_tray and has_display():
        services.append(
            Service(
                name="tray",
                cmd=[console_script("agentic-stack")],
                cwd=ROOT,
                essential=False,
                env={**os.environ, "AGENTIC_STACK_URL": f"http://localhost:{frontend_port}/stack"},
            )
        )
    return services


def report(services: list[Service], api_port: int, frontend_port: int) -> None:
    api_note = "" if api_port == DEFAULT_API_PORT else f"  (default {DEFAULT_API_PORT} is in use)"
    frontend_note = "" if frontend_port == DEFAULT_FRONTEND_PORT else f"  (default {DEFAULT_FRONTEND_PORT} is in use)"
    print(f"API       http://0.0.0.0:{api_port}{api_note}")
    print(f"frontend  http://0.0.0.0:{frontend_port}{frontend_note}")
    if not any(service.name == "tray" for service in services):
        print("tray      not started")
    print("Ctrl+C stops all", flush=True)


def run(services: list[Service]) -> int:
    """Start every service and block until one essential one stops or Ctrl+C."""
    processes: list[tuple[Service, subprocess.Popen[bytes]]] = []
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    try:
        for service in services:
            # A new session puts each service (and whatever it spawns, like the
            # Vite child of npm or the reloader child of uvicorn) in its own
            # process group, so one signal tears the whole tree down.
            processes.append(
                (service, subprocess.Popen(service.cmd, cwd=service.cwd, env=service.env, start_new_session=True))
            )

        reported: set[str] = set()
        while True:
            for service, proc in processes:
                code = proc.poll()
                if code is None or service.name in reported:
                    continue
                reported.add(service.name)
                if service.essential:
                    print(f"{service.name} exited with code {code}", file=sys.stderr)
                    raise SystemExit(1)
                print(f"{service.name} exited with code {code}; leaving the rest running", file=sys.stderr)
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        for _, proc in processes:
            if proc.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGTERM)
        for _, proc in processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reload", action="store_true", help="reload the API when backend files change")
    parser.add_argument(
        "--api-port", type=int, default=None, help=f"pin the API port (default: first free from {DEFAULT_API_PORT})"
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=None,
        help=f"pin the dev server port (default: first free from {DEFAULT_FRONTEND_PORT})",
    )
    parser.add_argument("--no-tray", action="store_true", help="do not start the tray/global-hotkey companion")
    parser.add_argument("--no-worker", action="store_true", help="do not start the agent-run worker")
    args = parser.parse_args()

    api_port = args.api_port or find_free_port(DEFAULT_API_PORT)
    frontend_port = args.frontend_port or find_free_port(DEFAULT_FRONTEND_PORT)

    services = build_services(args, api_port, frontend_port)
    report(services, api_port, frontend_port)
    return run(services)


if __name__ == "__main__":
    raise SystemExit(main())
