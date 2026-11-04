"""The one job that runs ``ghx cache``: a periodic refresh of the local cache.

Every page reads ghx's cache, and no read path refreshes it: a delta fetch is a
subprocess wait per repository, and a page load should never pay it (or, on a
repository ghx has never fully cached, start a whole-history walk). The
background pass keeps the registered repositories current so the pages that
read them are as fresh as the last pass, and it warms a repository ghx has no
completed cache for yet. The Settings page's force-refresh button calls the same
pass by hand, ignoring both the cadence and a failed repository's backoff.

The cadence is ``ghx_cache_refresh_interval`` (a duration such as ``15m``; empty
disables the scheduled pass). A repository whose refresh failed is left alone
for a while, so a cache that cannot be written does not restart a long walk on
every tick.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TypedDict

import structlog
from sqlmodel import Session

from .models.base import utcnow
from .my_pulls import known_github_repositories
from .parallel import run_parallel
from .refresh import parse_duration
from .services.github import list_cached_repositories, refresh_github_cache
from .settings_store import get_ghx_cache_status, get_settings, record_ghx_cache_run

log = structlog.get_logger(__name__)

#: How long a warmed repository's delta refresh may take. A delta is a few small
#: requests, so a call still running after this is one the job can drop.
DELTA_TIMEOUT = 60
#: How long a repository ghx has never fully cached may take on its first pass.
#: It walks the whole history (every issue and pull request, with comments),
#: which is why it runs here rather than on a page load.
WARM_TIMEOUT = 3600
#: How long a repository whose refresh failed is left alone. A failed warm walk
#: would otherwise restart from the beginning on every tick.
RETRY_AFTER = timedelta(hours=1)

#: Spellings of a cadence that mean the job is off.
_OFF_VALUES = frozenset({"off", "never", "none", "-"})

#: Lowercased repository -> monotonic time before which it is not refreshed
#: again, set when a refresh fails. A restart clears it, which is fine: the
#: cadence itself still keeps a failure from retrying more than once a tick.
_retry_after: dict[str, float] = {}


class CacheReport(TypedDict):
    """What one pass did, and the error that stopped it from doing more."""

    refreshed: int
    failed: int
    skipped: int
    error: str | None


def cache_interval(value: str | None) -> timedelta | None:
    """The configured cadence, or None when the job is off or the text is malformed."""
    text = (value or "").strip().lower()
    if not text or text in _OFF_VALUES:
        return None
    return parse_duration(text)


def _parse_timestamp(value: object) -> datetime | None:
    """A status timestamp as an aware datetime, or None when it is missing."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _refresh_one(repository: str, *, warm: bool) -> bool:
    """Refresh one repository, backing it off for a while when the call fails."""
    key = repository.lower()
    _retry_after[key] = time.monotonic() + RETRY_AFTER.total_seconds()
    owner, _, name = repository.partition("/")
    refreshed = refresh_github_cache(
        owner,
        name,
        timeout=DELTA_TIMEOUT if warm else WARM_TIMEOUT,
    )
    if refreshed:
        _retry_after.pop(key, None)
    return refreshed


def refresh_repositories(repositories: list[str], *, force: bool = False) -> CacheReport:
    """Refresh the caches of *repositories*, returning a count of what happened.

    A repository with a completed cache takes the delta fetch; any other one
    walks its whole history, since a background pass is the only place that can
    wait for it. Repositories in their retry backoff are skipped, unless *force*
    is set (the manual refresh, which should retry a failed repository now).
    When ghx cannot say which caches are warm, the pass is skipped rather than
    risking a full walk on every repository.
    """
    now = time.monotonic()
    due = [repository for repository in repositories if force or _retry_after.get(repository.lower(), 0.0) <= now]
    skipped = len(repositories) - len(due)
    if not due:
        return {"refreshed": 0, "failed": 0, "skipped": skipped, "error": None}
    cached = list_cached_repositories()
    if cached is None:
        message = "ghx could not list its cached repositories; the cache refresh was skipped"
        log.warning("ghx cache listing failed; skipping the cache refresh")
        return {"refreshed": 0, "failed": 0, "skipped": len(repositories), "error": message}

    calls: list[Callable[[], bool]] = []
    for repository in due:
        calls.append(partial(_refresh_one, repository, warm=repository.lower() in cached))
    results = run_parallel(calls)
    return {
        "refreshed": sum(1 for refreshed in results if refreshed),
        "failed": sum(1 for refreshed in results if not refreshed),
        "skipped": skipped,
        "error": None,
    }


def run_ghx_cache_refresh(session: Session, origin: str = "background", *, force: bool = False) -> CacheReport:
    """Refresh every registered GitHub repository's cache and record the pass.

    *origin* is ``background`` for the scheduled pass and ``manual`` for the
    Settings page's button, which also sets *force* to ignore the retry backoff.
    """
    repositories = known_github_repositories(session)
    report = refresh_repositories(repositories, force=force)
    record_ghx_cache_run(
        session,
        last_run_at=utcnow(),
        refreshed=report["refreshed"],
        failed=report["failed"],
        skipped=report["skipped"],
        error=report["error"],
        origin=origin,
    )
    return report


def run_due_ghx_cache_refresh(session: Session) -> CacheReport | dict[str, object]:
    """Run the refresh when its cadence says it is due."""
    interval = cache_interval(get_settings(session).get("ghx_cache_refresh_interval", ""))
    if interval is None:
        return {"skipped": "disabled"}
    last = _parse_timestamp(get_ghx_cache_status(session).get("last_run_at"))
    if last is not None and utcnow() - last < interval:
        return {"skipped": "not-due"}
    return run_ghx_cache_refresh(session)


__all__ = [
    "DELTA_TIMEOUT",
    "RETRY_AFTER",
    "WARM_TIMEOUT",
    "cache_interval",
    "refresh_repositories",
    "run_due_ghx_cache_refresh",
    "run_ghx_cache_refresh",
]
