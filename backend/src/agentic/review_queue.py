"""Enrich the review-store rows with their GitHub fields.

The store read lives in ``review_store``; this module overlays the pull
request's own fields (title, state, author, creation time) from ghx, cached for
a short time so a page reload does not shell out again.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from .review_store import (
    collect_review_prs as collect_review_prs,
)
from .review_store import (
    determine_stale_steps as determine_stale_steps,
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
    pr["draft"] = bool(metadata.get("is_draft", pr.get("draft", False)))


def enrich_from_github(prs: list[dict[str, Any]], refresh: bool = False) -> None:
    """Fill each PR's GitHub fields from ghx, in place.

    The lookups run one at a time: ghx caches through a SQLite database that
    refuses concurrent writers (``database is locked``), so a fetched batch
    would drop rows at random. ghx's own disk cache keeps a warm lookup around
    tens of milliseconds, and a result is reused for ``GITHUB_METADATA_TTL``
    seconds unless *refresh* is set. A failed lookup leaves the store's value in
    place, so the queue still renders without GitHub.
    """
    now = time.monotonic()
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
        try:
            metadata = fetch_github_issue(owner, name, number, "pull_request")
        except Exception as exc:  # noqa: BLE001
            log.warning("ghx pull request fetch failed", pr=key, error=str(exc))
            metadata = None
        _metadata_cache[key] = (time.monotonic(), metadata)
        if metadata:
            _apply_github(pr, metadata)
