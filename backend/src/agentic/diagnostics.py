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
    GhxHitRateRead,
    SlackxCacheRead,
)
from .services import shell
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

    Stdin is closed because some harnesses (``pi-acp``) ignore ``--version`` and
    start their ACP loop instead, reading stdin until it ends. Inheriting the
    server's stdin (a terminal) kept such a probe alive until the timeout, which
    held the whole Diagnostics read open.
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
            stdin=subprocess.DEVNULL,
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
    """Whether one command can run, where it is, and what it reports.

    A helper in rpc mode needs no local binary (``services.shell`` answers for
    it), so "present" means on PATH or served by a configured rpc server; the
    server itself is not probed here (a downed one shows up in the cache
    listings below), and path and version are only known for a local install.
    """
    path = shutil.which(spec.command)
    if path is None and not shell._cli_available(spec.command):
        return DependencyRead(
            id=spec.id,
            name=spec.name,
            command=spec.command,
            category=spec.category,
            required=spec.required,
            purpose=spec.purpose,
            present=False,
        )
    version, error = (None, None)
    if path is not None:
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


def _harness_specs(session: Session) -> list[DependencySpec]:
    """One probe spec per configured harness command, including custom ones."""
    return [
        DependencySpec(
            id=f"harness:{harness.id}",
            name=harness.name,
            command=harness.command,
            purpose=harness.description or "ACP agent harness.",
            category="harness",
        )
        for harness in session.exec(select(Harness).order_by(Harness.name)).all()
    ]


# ghx prints an em dash (or a plain dash) in a column with no value.
_NO_VALUE = {"—", "-"}
# The hit-rate columns ghx appends to each row, right to left.
_HIT_RATE_COLUMNS = 4


def _parse_hit_rates(cells: list[str]) -> tuple[list[GhxHitRateRead], list[str]]:
    """Split the trailing hit-rate columns off a row.

    ghx renders a rate as a percentage followed by the retrieval count in
    parentheses, for example ``67% (3)``, or a dash when it has recorded no
    retrieval of that kind. The row is whitespace-split, so the count is its own
    cell. Rows from a ghx that predates the columns end at the status and yield
    no rates.
    """
    rates: list[GhxHitRateRead] = []
    index = len(cells)
    while len(rates) < _HIT_RATE_COLUMNS and index > 0:
        token = cells[index - 1]
        if token in _NO_VALUE:
            rates.append(GhxHitRateRead())
            index -= 1
        elif token.startswith("(") and token.endswith(")") and index >= 2 and cells[index - 2].endswith("%"):
            try:
                retrievals = int(token[1:-1])
                percent = int(cells[index - 2][:-1])
            except ValueError:
                break
            rates.append(GhxHitRateRead(percent=percent, retrievals=retrievals))
            index -= 2
        else:
            break
    rates.reverse()
    return rates, cells[:index]


def parse_ghx_repositories(text: str) -> list[CachedRepositoryRead]:
    """Parse the table ``ghx repo list`` prints.

    ghx has no JSON output for this command, so the columns are read from the
    whitespace-separated rows. The age is a dash when ghx has no cache metadata,
    and the status can be several words, so the hit-rate columns are peeled off
    the end first.
    """
    repositories: list[CachedRepositoryRead] = []
    for line in text.splitlines():
        cells = line.split()
        if len(cells) < 4 or cells[0] == "REPO":
            continue
        rates, cells = _parse_hit_rates(cells)
        if len(cells) < 3:
            continue
        try:
            issues = int(cells[1])
            pull_requests = int(cells[2])
        except ValueError:
            continue
        rest = cells[3:]
        cached_age = None
        if rest and rest[0] not in _NO_VALUE:
            cached_age = rest[0]
        rest = rest[1:]
        # A ghx that predates the hit-rate columns leaves the four fields empty.
        rates.extend(GhxHitRateRead() for _ in range(_HIT_RATE_COLUMNS - len(rates)))
        repositories.append(
            CachedRepositoryRead(
                repository=cells[0],
                issues=issues,
                pull_requests=pull_requests,
                cached_age=cached_age,
                status=" ".join(rest),
                issue_list=rates[0],
                issue_view=rates[1],
                pr_list=rates[2],
                pr_view=rates[3],
            )
        )
    return repositories


def ghx_cache() -> GhxCacheRead:
    """The repositories in ghx's local cache, from ``ghx repo list``.

    Deliberately not the typed repo.list: only the table carries the
    per-retrieval hit rates (and a ghx whose rpc server runs with exec
    disabled), so the one spawn this manual page makes buys the full picture.
    """
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
    together rather than one after another, harnesses included: a harness whose
    version probe has to be killed must not add its timeout to the others. The
    harness list is read from the database first, on this thread, because a
    session is not shared across threads.
    """
    harness_specs = _harness_specs(session)
    probes: list[Callable[[], Any]] = [_python_report]
    probes.extend(lambda spec=spec: probe(spec) for spec in (*TOOL_DEPENDENCIES, *harness_specs))
    # Each probe returns its own report type; the pool's result is unpacked back
    # into the positions the constructor expects.
    results: list[Any] = run_parallel([*probes, ghx_cache, slackx_cache])
    return DiagnosticsRead(
        dependencies=results[: len(probes)],
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
