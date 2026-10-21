"""Enrich the review-store rows with their GitHub fields.

The store read lives in ``review_store``; this module overlays the pull
request's own fields (title, state, author, creation time) from ghx, cached for
a short time so a page reload does not shell out again.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from .parallel import run_parallel
from .review_store import (
    collect_review_prs as collect_review_prs,
)
from .review_store import (
    determine_stale_steps as determine_stale_steps,
)
from .review_store import (
    in_progress_steps as in_progress_steps,
)
from .review_store import (
    readiness_signal as readiness_signal,
)
from .services.github import fetch_github_issue

log = structlog.get_logger(__name__)

#: How long a ghx lookup of a pull request's GitHub fields is reused, so a page
#: reload does not shell out again. A Refresh (``?refresh=true``) bypasses it.
GITHUB_METADATA_TTL = 300
#: A lookup that failed (ghx missing, offline) is retried after this long rather
#: than on every request.
GITHUB_METADATA_FAILED_TTL = 60

#: (owner, repo, number) -> (monotonic fetch time, ghx metadata or None).
_metadata_cache: dict[tuple[str, str, int], tuple[float, dict[str, Any] | None]] = {}


def _apply_github(pr: dict[str, Any], metadata: dict[str, Any]) -> None:
    """Overlay ghx's fields on a store row, keeping the store's value when ghx
    has none.

    ghx is the source of truth for a pull request's own fields (its title, state,
    author, creation time), which the store only ever held as a snapshot from
    the review run that wrote it.
    """
    if metadata.get("title"):
        pr["title"] = metadata["title"]
    if metadata.get("url"):
        pr["url"] = metadata["url"]
    if metadata.get("author"):
        pr["author"] = metadata["author"]
    if metadata.get("state"):
        pr["state"] = metadata["state"]
    if metadata.get("created_at"):
        pr["created_at"] = metadata["created_at"]
    if metadata.get("review_decision"):
        pr["review_decision"] = metadata["review_decision"]
    pr["draft"] = bool(metadata.get("is_draft", pr.get("draft", False)))
    # The store's newest reviewed commit stands in for the head when GitHub
    # cannot be read; ghx knows the real one, so match the running markers
    # against it rather than against a commit the head has moved past.
    head = str(metadata.get("head_sha") or "")
    if head and pr.get("store_dir"):
        pr["in_progress"] = in_progress_steps(Path(str(pr["store_dir"])), head)


def _fetch_pr_metadata(owner: str, name: str, number: int) -> dict[str, Any] | None:
    """One pull request's GitHub fields, or None when the lookup failed."""
    try:
        return fetch_github_issue(owner, name, number, "pull_request")
    except Exception as exc:  # noqa: BLE001
        log.warning("ghx pull request fetch failed", pr=(owner, name, number), error=str(exc))
        return None


def enrich_from_github(prs: list[dict[str, Any]], refresh: bool = False) -> None:
    """Fill each PR's GitHub fields from ghx, in place.

    A pull request whose fields are cached is overlaid without a lookup; the
    result is reused for ``GITHUB_METADATA_TTL`` seconds unless *refresh* is
    set. The rest are fetched together, since each lookup is a ``ghx``
    subprocess wait: ghx caches through a SQLite database in WAL mode with a
    busy timeout, so a concurrent lookup waits for a write rather than failing
    with ``database is locked``. A lookup that still failed is cached as a miss
    and retried after ``GITHUB_METADATA_FAILED_TTL``. A failed lookup leaves the
    store's value in place, so the queue still renders without GitHub.
    """
    now = time.monotonic()
    wanted: list[tuple[dict[str, Any], tuple[str, str, int]]] = []
    missing: dict[tuple[str, str, int], tuple[str, str, int]] = {}
    for pr in prs:
        owner, name, number = pr.get("owner"), pr.get("name"), pr.get("number")
        if not owner or not name or not number:
            continue
        key = (str(owner).lower(), str(name).lower(), int(number))
        cached = _metadata_cache.get(key)
        if cached and not refresh:
            ttl = GITHUB_METADATA_TTL if cached[1] else GITHUB_METADATA_FAILED_TTL
            if now - cached[0] < ttl:
                if cached[1]:
                    _apply_github(pr, cached[1])
                continue
        wanted.append((pr, key))
        missing.setdefault(key, (str(owner), str(name), int(number)))
    if missing:
        keys = list(missing)
        fetched = run_parallel([lambda key=key: _fetch_pr_metadata(*missing[key]) for key in keys])
        fetched_at = time.monotonic()
        for key, metadata in zip(keys, fetched, strict=True):
            _metadata_cache[key] = (fetched_at, metadata)
    for pr, key in wanted:
        entry = _metadata_cache.get(key)
        if entry and entry[1]:
            _apply_github(pr, entry[1])
