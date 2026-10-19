"""Presence and versions of the external tools Agentic shells out to.

The Settings page's Diagnostics section reads this so a missing or outdated
helper CLI (``ghx``, ``slackx``, ``gh``, ``git``) is visible without digging
through logs. ACP harnesses are included too, including any custom ones, since
a run needs their command on ``PATH``.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from .models.agents import Harness
from .parallel import run_parallel
from .schemas.settings import (
    CachedRepositoryRead,
    DependencyRead,
    DiagnosticsRead,
    GhxCacheRead,
    SlackxCacheRead,
)
from .services.shell import run_cli_raw

# A version probe should never hold the Settings page open. A harness that
# treats an unknown flag as something else (or starts a server) is killed here.
VERSION_TIMEOUT = 5
# The cache listings read local data, but a wedged CLI must still not hang the
# Settings page.
CACHE_TIMEOUT = 30


@dataclass(frozen=True)
class DependencySpec:
    """One external command and how to ask it for its version."""

    id: str
    name: str
    command: str
    purpose: str
    category: str = "tool"
    required: bool = False
    version_args: tuple[str, ...] = ("--version",)


# The helper CLIs the backend invokes, in the order the UI lists them.
TOOL_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec(
        id="git",
        name="git",
        command="git",
        purpose="Worktree creation, status, and diffs.",
        required=True,
    ),
    DependencySpec(
        id="ghx",
        name="ghx",
        command="ghx",
        purpose="Reading GitHub issues and pull requests.",
    ),
    DependencySpec(
        id="gh",
        name="gh",
        command="gh",
        purpose="Creating GitHub issues, the review scan, and GitHub login detection.",
    ),
    DependencySpec(
        id="slackx",
        name="slackx",
        command="slackx",
        purpose="Importing Slack threads and refreshing their content.",
    ),
)


def _read_version(path: str, args: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Ask a command for its version: the first output line, or an error.

    Helpers do not agree on where a version goes (stdout or stderr) or whether
    they report one at all, so an empty result is not an error: the caller then
    shows the command as installed without a version.
    """
    if not args:
        return None, None
    try:
        result = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {VERSION_TIMEOUT}s"
    except OSError as exc:
        return None, str(exc)
    text = (result.stdout or "").strip() or (result.stderr or "").strip()
    if not text:
        return None, None
    return text.splitlines()[0].strip() or None, None


def probe(spec: DependencySpec) -> DependencyRead:
    """Whether one command is on PATH, where it is, and what it reports."""
    path = shutil.which(spec.command)
    if path is None:
        return DependencyRead(
            id=spec.id,
            name=spec.name,
            command=spec.command,
            category=spec.category,
            required=spec.required,
            purpose=spec.purpose,
            present=False,
        )
    version, error = _read_version(path, spec.version_args)
    return DependencyRead(
        id=spec.id,
        name=spec.name,
        command=spec.command,
        category=spec.category,
        required=spec.required,
        purpose=spec.purpose,
        present=True,
        path=path,
        version=version,
        error=error,
    )


def _python_report() -> DependencyRead:
    """The interpreter running the server, which no PATH lookup describes."""
    path = sys.executable or None
    return DependencyRead(
        id="python",
        name="Python",
        command="python",
        category="runtime",
        required=True,
        purpose="Runs the Agentic server.",
        present=True,
        path=path,
        version=platform.python_version(),
    )


def _harness_reports(session: Session) -> list[DependencyRead]:
    """Every configured harness command, including custom ones."""
    reports: list[DependencyRead] = []
    for harness in session.exec(select(Harness).order_by(Harness.name)).all():
        spec = DependencySpec(
            id=f"harness:{harness.id}",
            name=harness.name,
            command=harness.command,
            purpose=harness.description or "ACP agent harness.",
            category="harness",
        )
        reports.append(probe(spec))
    return reports


def parse_ghx_repositories(text: str) -> list[CachedRepositoryRead]:
    """Parse the table ``ghx repo list`` prints.

    ghx has no JSON output for this command, so the columns are read from the
    whitespace-separated rows. The age is an em dash when ghx has no cache
    metadata, and the status can be several words.
    """
    repositories: list[CachedRepositoryRead] = []
    for line in text.splitlines():
        cells = line.split()
        if len(cells) < 4 or cells[0] == "REPO":
            continue
        try:
            issues = int(cells[1])
            pull_requests = int(cells[2])
        except ValueError:
            continue
        rest = cells[3:]
        cached_age = None
        if rest and rest[0] in {"—", "-"}:
            rest = rest[1:]
        elif rest:
            cached_age = rest[0]
            rest = rest[1:]
        repositories.append(
            CachedRepositoryRead(
                repository=cells[0],
                issues=issues,
                pull_requests=pull_requests,
                cached_age=cached_age,
                status=" ".join(rest),
            )
        )
    return repositories


def ghx_cache() -> GhxCacheRead:
    """The repositories in ghx's local cache, from ``ghx repo list``."""
    result = run_cli_raw(["ghx", "repo", "list"], timeout=CACHE_TIMEOUT)
    if result is None:
        return GhxCacheRead(available=False, error="`ghx` not found on PATH")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return GhxCacheRead(
            available=True,
            error=detail[0] if detail else f"ghx repo list exited with {result.returncode}",
        )
    return GhxCacheRead(available=True, repositories=parse_ghx_repositories(result.stdout))


def _text(value: object) -> str | None:
    """A non-empty string from a JSON value, or None."""
    if isinstance(value, str):
        return value.strip() or None
    return None


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def slackx_cache() -> SlackxCacheRead:
    """The cache counts from ``slackx cache status --json``."""
    result = run_cli_raw(["slackx", "cache", "status", "--json"], timeout=CACHE_TIMEOUT)
    if result is None:
        return SlackxCacheRead(available=False, error="`slackx` not found on PATH")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return SlackxCacheRead(
            available=True,
            error=detail[0] if detail else f"slackx cache status exited with {result.returncode}",
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return SlackxCacheRead(available=True, error="slackx cache status did not return JSON")
    if not isinstance(data, dict):
        return SlackxCacheRead(available=True, error="slackx cache status returned an unexpected value")
    return SlackxCacheRead(
        available=True,
        workspace=_text(data.get("workspace")),
        db_path=_text(data.get("db_path")),
        channel_count=int(data.get("channel_count") or 0),
        user_count=int(data.get("user_count") or 0),
        thread_count=int(data.get("thread_count") or 0),
        message_count=int(data.get("message_count") or 0),
        read_marker_count=int(data.get("read_marker_count") or 0),
        channels_updated_at=_timestamp(data.get("channels_updated_at")),
        users_updated_at=_timestamp(data.get("users_updated_at")),
        threads_updated_at=_timestamp(data.get("threads_updated_at")),
    )


def collect_diagnostics(session: Session) -> DiagnosticsRead:
    """Probe every runtime, helper CLI, and harness, plus both local caches.

    Every probe and both cache listings wait on a subprocess, so they run
    together rather than one after another. ``_harness_reports`` is the only one
    that reads the database, so it stays on this thread.
    """
    probes: list[Callable[[], Any]] = [_python_report]
    probes.extend(lambda spec=spec: probe(spec) for spec in TOOL_DEPENDENCIES)
    # Each probe returns its own report type; the pool's result is unpacked back
    # into the positions the constructor expects.
    results: list[Any] = run_parallel([*probes, ghx_cache, slackx_cache])
    return DiagnosticsRead(
        dependencies=[*results[: len(probes)], *_harness_reports(session)],
        ghx_cache=results[-2],
        slackx_cache=results[-1],
        checked_at=datetime.now(UTC),
    )


__all__ = [
    "DependencySpec",
    "TOOL_DEPENDENCIES",
    "collect_diagnostics",
    "ghx_cache",
    "parse_ghx_repositories",
    "probe",
    "slackx_cache",
]
