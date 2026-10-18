"""Task items: associate and unassociate source items on a task.

Mounted under the same ``/api/tasks`` prefix as the task CRUD router; the shared
helpers live in ``tasks.py`` so the source-fetch seam stays in one place.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..crud import add_timeline, get_task_or_404
from ..db import get_session
from ..events import bus
from ..models.items import Association, SourceItem
from ..schemas.items import AssociateRequest, AssociationDetail, ItemRead
from .items import _upsert_item
from .task_service import _link_item, _populate_item_people

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/{task_id}/items", response_model=AssociationDetail, status_code=201)
async def associate_item(
    task_id: str, payload: AssociateRequest, session: Session = Depends(get_session)
) -> AssociationDetail:
    get_task_or_404(session, task_id)
    if payload.item is not None:
        # Fetching (network/CLI) happens here; keep it off the event loop.
        item = await anyio.to_thread.run_sync(_upsert_item, session, payload.item)
    elif payload.item_id is not None:
        item = session.get(SourceItem, payload.item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
    else:
        raise HTTPException(status_code=400, detail="Provide item_id or item")

    # An item that never fetched (or failed to) still names its author via
    # GitHub; fetch it off the event loop so the task gets the person.
    await anyio.to_thread.run_sync(_populate_item_people, session, item)

    assoc = _link_item(session, task_id, item, payload.note)
    add_timeline(
        session,
        task_id,
        "item_added",
        f"Associated [{item.source}] {item.title or item.url or item.id}",
        {"item_id": item.id},
    )
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "items_changed"})
    return AssociationDetail(
        id=assoc.id, note=assoc.note, created_at=assoc.created_at, item=ItemRead.model_validate(item)
    )


@router.delete("/{task_id}/items/{item_id}", status_code=204)
async def unassociate_item(task_id: str, item_id: str, session: Session = Depends(get_session)) -> None:
    assoc = session.exec(
        select(Association).where(Association.task_id == task_id, Association.item_id == item_id)
    ).first()
    if assoc is None:
        raise HTTPException(status_code=404, detail="Association not found")
    session.delete(assoc)
    session.commit()
    add_timeline(session, task_id, "item_removed", "Item unassociated", {"item_id": item_id})
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "items_changed"})


__all__ = ["router"]
