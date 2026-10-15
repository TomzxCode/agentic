"""Items: external things (Slack threads, GitHub issues, Drive docs, URLs, notes)."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..db import get_session
from ..models import Association, ItemPerson, SourceItem, utcnow
from ..refresh import (
    REFRESHABLE_SOURCES,
    PolicyError,
    RefreshPolicy,
    is_due,
    item_age,
    parse_policy,
    policies_from_settings,
)
from ..schemas import ItemCreate, ItemRead, ItemUpdate, RefreshDueReport
from ..services import fetch_source, infer_item_source, looks_like_url
from ..settings_store import get_settings, record_refresh_run
from .people import item_person_ids, link_people_to_item

router = APIRouter(prefix="/api/items", tags=["items"])


def _upsert_item(session: Session, payload: ItemCreate) -> SourceItem:
    # Text pasted where a URL was expected is not a URL: keep it as the note's
    # content instead of storing (and later rendering) a bogus link.
    raw_url = (payload.url or "").strip()
    url = raw_url if looks_like_url(raw_url) else None
    content = payload.content or (raw_url if raw_url and url is None else "")

    # Infer the source/kind/external id when the caller did not spell them out.
    inferred = infer_item_source(url, payload.external_id, content)
    source = payload.source or inferred["source"] or "note"
    kind = payload.kind or inferred.get("kind") or ""
    external_id = payload.external_id or inferred.get("external_id")

    item: SourceItem | None = None
    if external_id:
        item = session.exec(
            select(SourceItem).where(SourceItem.source == source, SourceItem.external_id == external_id)
        ).first()
    if item is None and url:
        item = session.exec(select(SourceItem).where(SourceItem.url == url)).first()

    if item is None:
        item = SourceItem(source=source)
        session.add(item)

    item.source = source
    item.kind = kind or item.kind
    item.title = payload.title or item.title
    if url:
        item.url = url
    item.external_id = external_id or item.external_id
    item.metadata_json = {**(item.metadata_json or {}), **payload.metadata_json}
    if content:
        item.content = content

    fetched_people: list[dict] = []
    if payload.fetch and item.url and not item.content:
        fetched = fetch_source(item.source, item.url, item.external_id, item.title)
        item.title = item.title or fetched.get("title") or item.url or item.source
        item.content = item.content or fetched.get("content", "")
        item.metadata_json = {**(item.metadata_json or {}), **fetched.get("metadata", {})}
        item.fetched_at = utcnow()
        fetched_people = fetched.get("people") or []

    if not item.title and item.content:
        item.title = item.content.strip().splitlines()[0][:120]

    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    if fetched_people:
        # The source named people (a GitHub author/commenter, a Slack
        # participant): upsert them and link them to the item.
        link_people_to_item(session, item.id, fetched_people)
    return item


def _item_read(session: Session, item: SourceItem) -> ItemRead:
    data = ItemRead.model_validate(item)
    data.task_ids = [
        assoc.task_id for assoc in session.exec(select(Association).where(Association.item_id == item.id)).all()
    ]
    data.person_ids = item_person_ids(session, item.id)
    return data


def _refresh_entries(session: Session, items: list[SourceItem], now) -> list[dict]:
    """Fetch and persist each item, recording success or the error. Best effort."""
    entries: list[dict] = []
    for item in items:
        entry = {"item_id": item.id, "source": item.source, "title": item.title, "refreshed": False, "error": None}
        try:
            fetched = fetch_source(item.source, item.url, item.external_id, item.title)
            item.title = fetched.get("title") or item.title
            item.content = fetched.get("content") or item.content
            item.metadata_json = {**(item.metadata_json or {}), **fetched.get("metadata", {})}
            item.fetched_at = now
            item.updated_at = now
            session.add(item)
            session.commit()
            session.refresh(item)
            link_people_to_item(session, item.id, fetched.get("people") or [])
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


@router.get("", response_model=list[ItemRead])
def list_items(
    source: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[ItemRead]:
    query = select(SourceItem).order_by(col(SourceItem.created_at).desc())
    if source:
        query = query.where(SourceItem.source == source)
    items = list(session.exec(query).all())
    if q:
        needle = q.lower()
        items = [
            item
            for item in items
            if needle in item.title.lower()
            or needle in (item.url or "").lower()
            or needle in (item.content or "").lower()
        ]
    return [_item_read(session, item) for item in items]


@router.post("", response_model=ItemRead, status_code=201)
def create_item(payload: ItemCreate, session: Session = Depends(get_session)) -> ItemRead:
    return _item_read(session, _upsert_item(session, payload))


@router.post("/refresh-due", response_model=RefreshDueReport)
def refresh_due(session: Session = Depends(get_session)) -> RefreshDueReport:
    """Re-fetch every item whose source refresh policy says it is due."""
    policies = policies_from_settings(get_settings(session))
    return RefreshDueReport.model_validate(refresh_due_items(session, policies, origin="manual"))


@router.post("/refresh-source/{source}", response_model=RefreshDueReport)
def refresh_source(source: str, session: Session = Depends(get_session)) -> RefreshDueReport:
    """Re-fetch every item of one source now, ignoring the refresh policy."""
    try:
        report = force_refresh_source(session, source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RefreshDueReport.model_validate(report)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _item_read(session, item)


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: str, payload: ItemUpdate, session: Session = Depends(get_session)) -> ItemRead:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key == "metadata_json":
            continue
        setattr(item, key, value)
    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_read(session, item)


@router.post("/{item_id}/refresh", response_model=ItemRead)
def refresh_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    fetched = fetch_source(item.source, item.url, item.external_id, item.title)
    item.title = fetched.get("title") or item.title
    item.content = fetched.get("content") or item.content
    item.metadata_json = {**(item.metadata_json or {}), **fetched.get("metadata", {})}
    item.fetched_at = utcnow()
    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    link_people_to_item(session, item.id, fetched.get("people") or [])
    return _item_read(session, item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, session: Session = Depends(get_session)) -> None:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    session.exec(sa_delete(Association).where(col(Association.item_id) == item_id))
    session.exec(sa_delete(ItemPerson).where(col(ItemPerson.item_id) == item_id))
    session.exec(sa_delete(SourceItem).where(col(SourceItem.id) == item_id))
    session.commit()


__all__ = ["router", "_upsert_item", "force_refresh_source", "refresh_due_items"]
