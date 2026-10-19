"""Item refresh: the policy-driven fetch pass and the on-demand one.

Kept apart from the item endpoints so the fetch loop (which talks to slackx and
ghx) is read on its own. Shares ``_apply_fetch`` with the single-item refresh.
"""

from __future__ import annotations

from collections import Counter

from sqlmodel import Session, col, select

from ..models.base import utcnow
from ..models.items import SourceItem
from ..refresh import (
    REFRESHABLE_SOURCES,
    PolicyError,
    RefreshPolicy,
    is_due,
    item_age,
    parse_policy,
)
from ..services.parsing import parse_github
from ..services.sources import fetch_source
from ..settings_store import record_refresh_run
from .people_links import link_people_to_item


def _apply_fetch(item: SourceItem, fetched: dict, now) -> str | None:
    """Merge a fetch result into the item and return the fetch's error, if any.

    A failed fetch still merges what it did return (a Slack item's name comes
    from its URL), but leaves ``fetched_at`` alone so the refresh policy retries
    it rather than treating the miss as fresh. A title a person set is kept.
    """
    if not item.title_custom:
        item.title = fetched.get("title") or item.title
    item.content = fetched.get("content") or item.content
    item.metadata_json = {**(item.metadata_json or {}), **fetched.get("metadata", {})}
    error = fetched.get("error")
    if not error:
        item.fetched_at = now
    item.updated_at = now
    return error


def _refresh_entries(session: Session, items: list[SourceItem], now) -> list[dict]:
    """Fetch and persist each item, recording success or the error. Best effort."""
    entries: list[dict] = []
    for item in items:
        entry = {"item_id": item.id, "source": item.source, "title": item.title, "refreshed": False, "error": None}
        try:
            fetched = fetch_source(item.source, item.url, item.external_id, item.title)
            error = _apply_fetch(item, fetched, now)
            session.add(item)
            session.commit()
            session.refresh(item)
            link_people_to_item(session, item.id, fetched.get("people") or [])
            if error:
                entry["error"] = error
            else:
                entry["refreshed"] = True
            entry["title"] = item.title
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            entry["error"] = str(exc)
        entries.append(entry)
    return entries


def _refresh_report(checked: int, entries: list[dict]) -> dict:
    return {
        "checked": checked,
        "due": len(entries),
        "refreshed": sum(1 for entry in entries if entry["refreshed"]),
        "failed": sum(1 for entry in entries if entry["error"]),
        "items": entries,
    }


def _record_runs(session: Session, sources, entries: list[dict], now, origin: str) -> None:
    """Store the per-source outcome of a refresh pass, for the Settings page."""
    refreshed: Counter = Counter()
    failed: Counter = Counter()
    errors: dict[str, str] = {}
    for entry in entries:
        source = entry["source"]
        if entry["refreshed"]:
            refreshed[source] += 1
        if entry.get("error"):
            failed[source] += 1
            errors[source] = entry["error"]
    for source in sources:
        record_refresh_run(
            session,
            source,
            last_run_at=now,
            refreshed=refreshed.get(source, 0),
            failed=failed.get(source, 0),
            error=errors.get(source),
            origin=origin,
        )


def refresh_due_items(session: Session, policies: dict[str, str], now=None, origin: str = "background") -> dict:
    """Refresh every item whose source policy says it is due. Best effort per item.

    ``policies`` maps a source ("slack", "github") to its policy text; a source
    with no policy (or a malformed one) is skipped. Records each active source's
    outcome under ``origin`` ("background" for the timer, "manual" for a run
    asked for through the API/CLI). A failure on one item (slackx/ghx missing or
    erroring) is recorded and does not stop the others.
    """
    now = now or utcnow()
    parsed: dict[str, RefreshPolicy | None] = {}
    for source in REFRESHABLE_SOURCES:
        try:
            parsed[source] = parse_policy(policies.get(source, ""))
        except PolicyError:
            parsed[source] = None
    active = tuple(source for source, policy in parsed.items() if policy is not None and policy.enabled)
    if not active:
        return _refresh_report(0, [])

    items = list(session.exec(select(SourceItem).where(col(SourceItem.source).in_(active))).all())
    due = []
    for item in items:
        # A local narrows the policy for the checker; a repeated lookup in the
        # comprehension does not.
        policy = parsed[item.source]
        if policy is not None and is_due(policy, age=item_age(item, now), fetched_at=item.fetched_at, now=now):
            due.append(item)
    entries = _refresh_entries(session, due, now)
    _record_runs(session, active, entries, now, origin)
    return _refresh_report(len(items), entries)


def force_refresh_source(session: Session, source: str, now=None) -> dict:
    """Re-fetch every item of one source now, ignoring the refresh policy.

    Used by ``POST /api/items/refresh-source/{source}`` and the Settings
    "Force refresh" button, so a source can be pulled on demand even when no
    policy is set or nothing is due.
    """
    if source not in REFRESHABLE_SOURCES:
        raise ValueError(f"Unknown source: {source}")
    now = now or utcnow()
    items = list(session.exec(select(SourceItem).where(SourceItem.source == source)).all())
    fetchable = [item for item in items if item.url]
    entries = _refresh_entries(session, fetchable, now)
    _record_runs(session, [source], entries, now, "manual")
    return _refresh_report(len(items), entries)


# The listing fields that mirror the state a full fetch stores on an item. The
# item's body and people are left alone: the listing does not carry them.
_LISTING_STATE_KEYS = ("state", "is_draft", "merged_at", "created_at", "author")


def _merge_listing(item: SourceItem, entry: dict, now) -> bool:
    """Merge one ghx listing row into an item; True when something changed."""
    title = item.title
    if not item.title_custom and entry.get("title"):
        title = entry["title"]
    metadata = dict(item.metadata_json or {})
    for key in _LISTING_STATE_KEYS:
        if entry.get(key) is not None:
            metadata[key] = entry[key]
    if title == item.title and metadata == (item.metadata_json or {}):
        return False
    item.title = title
    item.metadata_json = metadata
    item.updated_at = now
    return True


def sync_github_listing(session: Session, owner: str, repo: str, entries: list[dict], now=None) -> int:
    """Write a repository listing's state back onto the items it names.

    The repository view reads ghx on every visit (re-fetching when its cache has
    expired) and merges that listing over the stored items for display, so the
    view is never staler than the items. The stored items themselves are only
    written by a policy-driven or on-demand fetch, so without this they keep the
    state they had at their last fetch and read as older than the repository.

    Merging the listing's state into the matching stored items (by GitHub
    owner/repo, number, and kind) keeps an item from being staler than the
    repository that shows it. Only the listing's state fields are written; the
    item's body and people still come from a full fetch. Returns how many items
    changed; a listing that matches the stored state writes nothing.
    """
    now = now or utcnow()
    wanted = {}
    for entry in entries or []:
        number = entry.get("number")
        if number is None:
            continue
        kind = "pr" if entry.get("kind") == "pr" else "issue"
        wanted[(kind, str(number))] = entry
    if not wanted:
        return 0

    target = f"{owner}/{repo}".lower()
    changed = 0
    for item in session.exec(select(SourceItem).where(SourceItem.source == "github")).all():
        parsed = parse_github(item.url or "")
        if parsed is None or f"{parsed['owner']}/{parsed['repo']}".lower() != target:
            continue
        kind = "pr" if parsed["kind"] == "pull_request" else "issue"
        entry = wanted.get((kind, parsed["number"]))
        if entry is None:
            continue
        if _merge_listing(item, entry, now):
            session.add(item)
            changed += 1
    if changed:
        session.commit()
    return changed
