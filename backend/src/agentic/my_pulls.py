"""The viewer's own open pull requests, with the state the My PRs page shows.

The rows come from one GraphQL search (``services.github.search_my_open_pulls``);
this module caches the result for a short time and derives the header's counts,
so reloading the page does not re-query GitHub. Nothing is stored in the
database: a pull request that merges leaves the list on the next refresh.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from .services.github import search_my_open_pulls

log = structlog.get_logger(__name__)

#: How long one login's pull requests are reused, so a reload does not re-query.
MY_PULLS_TTL = 60
#: A lookup that failed (gh missing, offline) is retried after this long rather
#: than on every request.
MY_PULLS_FAILED_TTL = 30

#: A message for when no GitHub login is configured at all.
NO_LOGIN_ERROR = "No GitHub login is configured; set it in Settings > Identity to list your pull requests."
#: A message for when the login is known but GitHub could not be read.
UNREACHABLE_ERROR = "Could not read your pull requests from GitHub; check that `gh` is installed and authenticated."

#: lowercased login -> (monotonic fetch time, pull requests or None on failure).
_cache: dict[str, tuple[float, list[dict[str, Any]] | None]] = {}


def pull_counts(pulls: list[dict[str, Any]]) -> dict[str, int]:
    """The header's totals over a set of pull requests.

    ``attention`` counts the pull requests that need the author to act: failing
    checks, requested changes, or an unresolved review thread.
    """
    return {
        "total": len(pulls),
        "attention": sum(
            1
            for pull in pulls
            if pull["ci"] == "failure"
            or pull["review_decision"] == "CHANGES_REQUESTED"
            or int(pull["open_threads"]) > 0
        ),
        "approved": sum(1 for pull in pulls if pull["approved"]),
        "failing": sum(1 for pull in pulls if pull["ci"] == "failure"),
        "open_threads": sum(int(pull["open_threads"]) for pull in pulls),
        "draft": sum(1 for pull in pulls if pull["draft"]),
    }


def _report(login: str, pulls: list[dict[str, Any]], error: str | None) -> dict[str, Any]:
    return {"login": login, "pulls": pulls, "counts": pull_counts(pulls), "error": error}


def fetch_my_pulls(login: str, refresh: bool = False) -> dict[str, Any]:
    """The login's open pull requests, cached, with their counts and any error.

    A lookup that could not run reports the reason and no pull requests, so the
    page can say what is wrong instead of showing an empty list as if there were
    no open work. ``refresh`` skips the reuse and re-queries GitHub.
    """
    login = (login or "").strip()
    if not login:
        return _report("", [], NO_LOGIN_ERROR)

    cached = _cache.get(login.lower())
    if cached is not None and not refresh:
        ttl = MY_PULLS_TTL if cached[1] is not None else MY_PULLS_FAILED_TTL
        if time.monotonic() - cached[0] < ttl:
            pulls = cached[1]
            if pulls is None:
                return _report(login, [], UNREACHABLE_ERROR)
            return _report(login, pulls, None)

    pulls = search_my_open_pulls(login)
    _cache[login.lower()] = (time.monotonic(), pulls)
    if pulls is None:
        log.warning("my pulls lookup failed", login=login)
        return _report(login, [], UNREACHABLE_ERROR)
    return _report(login, pulls, None)


__all__ = ["fetch_my_pulls", "pull_counts"]
