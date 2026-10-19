"""Low-level process helpers shared by the git, GitHub, and Slack fetchers.

They live in one module so there is a single place to stub a subprocess in tests.
"""

from __future__ import annotations

import shutil
import subprocess

import structlog

log = structlog.get_logger(__name__)

# The helper CLIs whose every invocation is logged at info level, so the
# server's external calls (and their arguments) are visible while it runs.
_LOGGED_CLIS = frozenset({"ghx", "slackx"})


def _log_cli_call(cmd: list[str]) -> None:
    """Log an invocation of a tracked helper CLI (ghx, slackx) at info level."""
    if cmd and cmd[0] in _LOGGED_CLIS:
        log.info("cli call", cmd=cmd)


def _git(args: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _cli_available(name: str) -> bool:
    """Whether a helper CLI (ghx, slackx) is on PATH, so a fetch can name it."""
    return shutil.which(name) is not None


def _run_cli(cmd: list[str], timeout: int = 60) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    _log_cli_call(cmd)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.info("cli fetch failed", cmd=cmd[0], error=str(exc))
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def run_cli_raw(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str] | None:
    """Run a helper CLI and return the raw result, for callers that need stderr."""
    if shutil.which(cmd[0]) is None:
        return None
    _log_cli_call(cmd)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.info("cli fetch failed", cmd=cmd[0], error=str(exc))
        return None
