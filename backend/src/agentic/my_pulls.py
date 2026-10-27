"""The viewer's own open pull requests, with the state the My PRs page shows.

The rows come from ghx (``services.github.list_my_open_pulls``), one listing per
repository the app knows, because ghx caches one repository at a time and
carries the check rollup and review-thread counts the page shows. This module
refreshes those repositories' ghx caches, caches the assembled result for a
short time, and derives the header's counts, so reloading the page does not
re-query GitHub. The individual checks behind one pull request's CI badge are
read on demand (``fetch_my_pull_checks``), since the page needs only the rollup
state until the badge's popover opens. Nothing is stored in the database: a
pull request that merges leaves the list on the next refresh.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import structlog
from sqlmodel import Session, select

from .models.repositories import Repository
from .parallel import run_parallel
from .services.github import (
    fetch_pull_checks,
    github_owner_repo,
    list_my_open_pulls,
    refresh_github_cache,
)

log = structlog.get_logger(__name__)

#: How long one login's pull requests are reused, so a reload does not re-query.
MY_PULLS_TTL = 60
#: A lookup that failed (ghx missing, offline) is retried after this long rather
#: than on every request.
MY_PULLS_FAILED_TTL = 30
#: How long one pull request's checks are reused, so closing and reopening the
#: CI popover does not re-query GitHub. Checks move faster than the list, so it
#: is shorter than the list's own cache.
PULL_CHECKS_TTL = 30

#: A message for when no GitHub login is configured at all.
NO_LOGIN_ERROR = "No GitHub login is configured; set it in Settings > Identity to list your pull requests."
#: A message for when no repository carries a GitHub remote to read.
NO_REPOSITORIES_ERROR = "No GitHub repositories are registered; add one in Repositories to list your pull requests."
#: A message for when the login is known but GitHub could not be read.
UNREACHABLE_ERROR = "Could not read your pull requests from GitHub; check that `ghx` is installed and authenticated."
#: A message for when one pull request's checks could not be read.
CHECKS_UNREACHABLE_ERROR = (
    "Could not read this pull request's checks from GitHub; check that `ghx` is installed and authenticated."
)

#: (lowercased login, lowercased repositories) -> (monotonic fetch time, pull
#: requests or None on failure). The repository set is part of the key, so
#: registering or removing a repository never serves the previous list.
_cache: dict[tuple[str, tuple[str, ...]], tuple[float, list[dict[str, Any]] | None]] = {}
#: (lowercased repository, number) -> (monotonic fetch time, checks or None).
_checks_cache: dict[tuple[str, int], tuple[float, dict[str, Any] | None]] = {}


def known_github_repositories(session: Session) -> list[str]:
    """The GitHub repositories the app knows, as deduplicated ``owner/name``.

    ghx lists one repository at a time, so the My PRs read covers exactly the
    repositories registered here. Two checkouts of the same remote collapse to
    one entry, and a repository without a GitHub remote is left out.
    """
    repositories: list[str] = []
    seen: set[str] = set()
    for row in session.exec(select(Repository)).all():
        parsed = github_owner_repo(row.remote_url)
        if parsed is None:
            continue
        full_name = f"{parsed[0]}/{parsed[1]}"
        if full_name.lower() in seen:
            continue
        seen.add(full_name.lower())
        repositories.append(full_name)
    return repositories


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


def _refresh_repositories(repositories: list[str]) -> None:
    """Bring the repositories' ghx caches up to date before listing.

    ``ghx cache`` runs a delta fetch, which is cheap for an unchanged
    repository. The repositories run together, so one slow fetch does not add
    its latency to the others. A failure is left to the listing, which answers
    from the cache it has or reports the read as unreachable.
    """
    calls = []
    for repository in repositories:
        owner, _, name = repository.partition("/")
        if owner and name:
            calls.append(lambda owner=owner, name=name: refresh_github_cache(owner, name))
    if calls:
        run_parallel(calls)


def fetch_my_pulls(login: str, repositories: Sequence[str], refresh: bool = False) -> dict[str, Any]:
    """The login's open pull requests, cached, with their counts and any error.

    A lookup that could not run reports the reason and no pull requests, so the
    page can say what is wrong instead of showing an empty list as if there were
    no open work. ``refresh`` skips the reuse and re-queries GitHub. A lookup
    that could run refreshes the repositories' ghx caches first, so the rows
    carry the state GitHub has now rather than whenever ghx last wrote them.
    """
    login = (login or "").strip()
    if not login:
        return _report("", [], NO_LOGIN_ERROR)
    repositories = list(dict.fromkeys(repository for repository in repositories if repository))
    if not repositories:
        return _report(login, [], NO_REPOSITORIES_ERROR)

    key = (login.lower(), tuple(repository.lower() for repository in repositories))
    cached = _cache.get(key)
    if cached is not None and not refresh:
        ttl = MY_PULLS_TTL if cached[1] is not None else MY_PULLS_FAILED_TTL
        if time.monotonic() - cached[0] < ttl:
            pulls = cached[1]
            if pulls is None:
                return _report(login, [], UNREACHABLE_ERROR)
            return _report(login, pulls, None)

    _refresh_repositories(repositories)
    pulls = list_my_open_pulls(repositories, login)
    _cache[key] = (time.monotonic(), pulls)
    if pulls is None:
        log.warning("my pulls lookup failed", login=login)
        return _report(login, [], UNREACHABLE_ERROR)
    return _report(login, pulls, None)


def fetch_my_pull_checks(owner: str, repo: str, number: int, refresh: bool = False) -> dict[str, Any]:
    """One pull request's checks, cached briefly, with any error.

    The My PRs row carries only the rollup state, so this read backs the CI
    badge's popover. A read that could not run reports the reason and no checks,
    so the popover can say what is wrong instead of reading as a pull request
    with nothing to run. ``refresh`` skips the reuse and asks ghx again.
    """
    repository = f"{owner}/{repo}"
    key = (repository.lower(), number)
    cached = _checks_cache.get(key)
    if cached is not None and not refresh and time.monotonic() - cached[0] < PULL_CHECKS_TTL:
        report = cached[1]
    else:
        report = fetch_pull_checks(owner, repo, number)
        _checks_cache[key] = (time.monotonic(), report)
    if report is None:
        return {"rollup": "none", "checks": [], "total": 0, "error": CHECKS_UNREACHABLE_ERROR}
    return {**report, "error": None}


__all__ = ["fetch_my_pull_checks", "fetch_my_pulls", "known_github_repositories", "pull_counts"]
