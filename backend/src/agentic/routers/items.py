"""Items: external things (Slack threads, GitHub issues, Drive docs, URLs, notes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import SourceItem, utcnow
from ..schemas import ItemCreate, ItemRead, ItemUpdate
from ..services import fetch_source

router = APIRouter(prefix="/api/items", tags=["items"])


def _upsert_item(session: Session, payload: ItemCreate) -> SourceItem:
    item: SourceItem | None = None
    if payload.external_id:
        item = session.exec(
            select(SourceItem).where(SourceItem.source == payload.source, SourceItem.external_id == payload.external_id)
        ).first()
    if item is None and payload.url:
        item = session.exec(select(SourceItem).where(SourceItem.url == payload.url)).first()

    if item is None:
        item = SourceItem(source=payload.source)
        session.add(item)

    item.kind = payload.kind or item.kind
    item.title = payload.title or item.title
    item.url = payload.url or item.url
    item.external_id = payload.external_id or item.external_id
    item.metadata_json = {**(item.metadata_json or {}), **payload.metadata_json}
    if payload.content:
        item.content = payload.content

    if payload.fetch and not item.content:
        fetched = fetch_source(item.source, item.url, item.external_id, item.title)
        item.title = item.title or fetched.get("title") or item.url or item.source
        item.content = item.content or fetched.get("content", "")
        item.metadata_json = {**(item.metadata_json or {}), **fetched.get("metadata", {})}
        item.fetched_at = utcnow()

    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("", response_model=list[ItemRead])
def list_items(source: str | None = None, session: Session = Depends(get_session)) -> list[SourceItem]:
    query = select(SourceItem).order_by(SourceItem.created_at.desc())
    if source:
        query = query.where(SourceItem.source == source)
    return list(session.exec(query).all())


@router.post("", response_model=ItemRead, status_code=201)
def create_item(payload: ItemCreate, session: Session = Depends(get_session)) -> SourceItem:
    return _upsert_item(session, payload)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: str, session: Session = Depends(get_session)) -> SourceItem:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: str, payload: ItemUpdate, session: Session = Depends(get_session)) -> SourceItem:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.post("/{item_id}/refresh", response_model=ItemRead)
def refresh_item(item_id: str, session: Session = Depends(get_session)) -> SourceItem:
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
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, session: Session = Depends(get_session)) -> None:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    session.delete(item)
    session.commit()


__all__ = ["router", "_upsert_item"]
