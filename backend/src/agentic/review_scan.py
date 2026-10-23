"""Find the pull requests awaiting the user's review, and keep the set stored.

The review queue reads the reports the review skills wrote to ``~/.sdlc``, which
only holds pull requests a review has already run against. This module covers the
other half of the ``review_requested_prs`` script: asking GitHub which pull
requests are waiting, so the queue can show them before any report exists.

Two searches make up the set, matching the script: ``review-requested:@me`` (a
review is asked of the user) and ``reviewed-by:@me`` (the user reviewed it and it
is still open). Both go through ``gh search prs``: ghx caches and reads issues and
pull requests, but has no search qualifiers.

The script's ``--notifications`` recovery of dropped team review requests is not
ported: it needs the notifications API plus a batched GraphQL drop check, and the
plain searches do not surface those pull requests at all.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlmodel import Session, select

from .config import settings
from .models.base import utcnow
from .models.repositories import Repository, ReviewScanPolicy
from .models.reviews import ReviewRequest, ReviewScanSource
from .parallel import run_parallel
from .refresh import parse_duration
from .services import shell
from .services.github import github_owner_repo
from .settings_store import get_review_scan_status, get_settings, record_review_scan_run

log = structlog.get_logger(__name__)

#: The fields ``gh search prs`` returns for a row.
SEARCH_FIELDS = "number,title,url,state,isDraft,repository,author,createdAt"
SEARCH_TIMEOUT = 90

#: The two searches, in priority order: a pull request asking for the user's
#: review is reported as ``requested`` even when the second search also matches.
SEARCHES: tuple[tuple[str, ReviewScanSource], ...] = (
    ("--review-requested=@me", ReviewScanSource.requested),
    ("--reviewed-by=@me", ReviewScanSource.reviewed),
)

#: Cadence spellings that mean the scan is off.
_OFF_VALUES = frozenset({"off", "never", "none", "-"})


def parse_exclude_authors(value: str | None) -> set[str]:
    """The logins a scan leaves out, lowercased."""
    return {part.strip().lower() for part in (value or "").split(",") if part.strip()}


def scan_interval(value: str | None) -> timedelta | None:
    """The configured cadence, or None when the scan is off or malformed."""
    text = (value or "").strip().lower()
    if not text or text in _OFF_VALUES:
        return None
    return parse_duration(text)


def configured_review_slo(session: Session) -> timedelta | None:
    """The review SLO: how long a review may wait, or None when it is off."""
    return scan_interval(get_settings(session).get("review_slo", ""))


def scan_due(last_run_at: datetime | None, interval: timedelta | None, now: datetime) -> bool:
    """Whether a scan is due: never run yet, or the cadence has elapsed."""
    if interval is None:
        return False
    if last_run_at is None:
        return True
    return now - last_run_at >= interval


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _search(flag: str, limit: int) -> list[dict[str, Any]] | None:
    """Run one search. None when it could not run at all."""
    raw = shell._run_cli(
        ["gh", "search", "prs", flag, "--state=open", "--limit", str(limit), "--json", SEARCH_FIELDS],
        timeout=SEARCH_TIMEOUT,
    )
    if not raw:
        return None
    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return results if isinstance(results, list) else None


def _normalize(entry: dict[str, Any], source: ReviewScanSource) -> dict[str, Any] | None:
    """One search result as a stored row, or None when it names no pull request."""
    repository = str((entry.get("repository") or {}).get("nameWithOwner") or "").strip()
    number = entry.get("number")
    if not repository or number is None:
        return None
    return {
        "repository": repository,
        "number": int(number),
        "source": source.value,
        "title": str(entry.get("title") or ""),
        "url": str(entry.get("url") or ""),
        "author": str((entry.get("author") or {}).get("login") or ""),
        "state": str(entry.get("state") or "").upper(),
        "draft": bool(entry.get("isDraft")),
        "created_at": entry.get("createdAt"),
    }


def search_awaiting_reviews(limit: int, exclude_authors: set[str]) -> list[dict[str, Any]] | None:
    """The pull requests awaiting the user's review, requested ones first.

    None when neither search could run (``gh`` missing, not authenticated); one
    failing search is tolerated, since the other still yields its half. Each
    search carries its own *limit*, as the script's did. The two searches are
    independent, so they run together.
    """
    found: dict[tuple[str, int], dict[str, Any]] = {}
    ran = False
    searches = run_parallel([lambda flag=flag: _search(flag, limit) for flag, _ in SEARCHES])
    for (flag, source), results in zip(SEARCHES, searches, strict=True):
        if results is None:
            log.warning("review scan search failed", flag=flag)
            continue
        ran = True
        for entry in results:
            row = _normalize(entry, source)
            if row is None or row["author"].lower() in exclude_authors:
                continue
            found.setdefault((row["repository"].lower(), row["number"]), row)
    if not ran:
        return None
    return list(found.values())


def include_repository(repository: str, policies: dict[str, str], default: str) -> bool:
    """Whether a repository's pull requests belong in the scan.

    The repository's own policy wins; with none, the app-wide default decides, so
    "include" scans every repository except the exclusions and "exclude" scans
    only the repositories marked include. *policies* is keyed by lowercased
    ``owner/name``.
    """
    policy = policies.get(repository.lower(), ReviewScanPolicy.default.value)
    if policy == ReviewScanPolicy.include:
        return True
    if policy == ReviewScanPolicy.exclude:
        return False
    return default == ReviewScanPolicy.include.value


def repository_policies(session: Session) -> dict[str, str]:
    """Each registered repository's scan policy, keyed by its lowercased remote."""
    policies: dict[str, str] = {}
    for repository in session.exec(select(Repository)).all():
        parsed = github_owner_repo(repository.remote_url)
        if parsed:
            policies[f"{parsed[0]}/{parsed[1]}".lower()] = repository.review_scan
    return policies


def scan_default(session: Session) -> str:
    """The app-wide default for a repository with no policy of its own."""
    value = get_settings(session).get("review_scan_default", "").strip().lower()
    if value in (ReviewScanPolicy.include.value, ReviewScanPolicy.exclude.value):
        return value
    return ReviewScanPolicy.include.value


def stored_review_requests(session: Session) -> list[ReviewRequest]:
    """The stored scan rows, minus any whose repository is now excluded.

    The scan filters as it stores, so this only matters between a repository
    being marked exclude and the next scan: the queue should not keep showing its
    pull requests in the meantime.
    """
    policies = repository_policies(session)
    default = scan_default(session)
    return [
        row
        for row in session.exec(select(ReviewRequest)).all()
        if include_repository(row.repository, policies, default)
    ]


def store_scan_results(session: Session, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Replace the stored set with *rows*: upsert what was found, drop the rest.

    ``first_seen_at`` is kept from the existing row, so a pull request keeps the
    time it was first seen waiting. Returns ``(stored, removed)``.
    """
    existing = {(row.repository.lower(), row.number): row for row in session.exec(select(ReviewRequest)).all()}
    now = utcnow()
    for row in rows:
        current = existing.pop((row["repository"].lower(), row["number"]), None)
        if current is None:
            session.add(ReviewRequest(**row))
            continue
        for field, value in row.items():
            setattr(current, field, value)
        current.updated_at = now
        session.add(current)
    for stale in existing.values():
        session.delete(stale)
    session.commit()
    return len(rows), len(existing)


def run_review_scan(session: Session, origin: str = "background", force: bool = False) -> dict[str, Any]:
    """Run one scan: ask GitHub, filter, and replace the stored set.

    A scan that could not run leaves the stored set untouched, so a broken ``gh``
    never empties the queue; the failure is recorded and retried on the next
    cadence. *force* runs even when the scan is switched off, which is what the
    "Scan now" button does.
    """
    interval = scan_interval(get_settings(session).get("review_scan_interval", ""))
    if interval is None and not force:
        return {"skipped": "off"}
    exclude = parse_exclude_authors(settings.review_scan_exclude_authors)
    found = search_awaiting_reviews(settings.review_scan_limit, exclude)
    if found is None:
        error = "gh could not search for review requests; install and authenticate the GitHub CLI"
        record_review_scan_run(session, last_run_at=utcnow(), found=0, stored=0, error=error, origin=origin)
        log.warning("review scan failed", error=error)
        return {"error": error}
    policies = repository_policies(session)
    default = scan_default(session)
    kept = [row for row in found if include_repository(row["repository"], policies, default)]
    stored, removed = store_scan_results(session, kept)
    record_review_scan_run(session, last_run_at=utcnow(), found=len(found), stored=stored, error=None, origin=origin)
    log.info("review scan done", found=len(found), stored=stored, removed=removed)
    return {"found": len(found), "stored": stored, "removed": removed}


def run_due_review_scan(session: Session) -> dict[str, Any]:
    """Run the scan when the configured cadence says it is due."""
    interval = scan_interval(get_settings(session).get("review_scan_interval", ""))
    last = _parse_timestamp(get_review_scan_status(session).get("last_run_at"))
    if not scan_due(last, interval, utcnow()):
        return {"skipped": "not-due"}
    return run_review_scan(session)


def review_scan_state(session: Session) -> dict[str, Any]:
    """The scan's configuration and its last pass, for the API and the UI."""
    values = get_settings(session)
    interval = scan_interval(values.get("review_scan_interval", ""))
    status = get_review_scan_status(session)
    last = _parse_timestamp(status.get("last_run_at"))
    next_run = last + interval if last and interval else (utcnow() if interval else None)
    return {
        "interval": values.get("review_scan_interval", ""),
        "enabled": interval is not None,
        "interval_seconds": interval.total_seconds() if interval else None,
        "default": scan_default(session),
        "stored": len(session.exec(select(ReviewRequest)).all()),
        "last_run_at": last,
        "next_run_at": next_run,
        "found": status.get("found", 0),
        "kept": status.get("stored", 0),
        "error": status.get("error"),
        "origin": status.get("origin"),
    }
