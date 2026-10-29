"""People: the directory endpoints and the task/item link endpoints.

A person is a flat directory entry (a name plus optional contact details). Links
to tasks and to items are many-to-many and idempotent: linking a person already
linked returns the existing association rather than creating a duplicate. The
task-side link endpoints live here (rather than in the tasks router) so all the
people logic stays in one module. The lookups, linking, and merging helpers live
in ``people_service.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from ..checklists import apply_task_templates
from ..crud import add_timeline, get_task_or_404
from ..db import get_session
from ..events import bus
from ..models.base import utcnow
from ..models.items import ItemPerson, Person, PersonAlias, SourceItem, TaskPerson, TaskRequester
from ..models.tasks import Task
from ..schemas.people import PersonCreate, PersonDetail, PersonLink, PersonMerge, PersonRead, PersonUpdate
from .people_links import _link_item, _link_requester, _link_task, merge_people
from .people_service import (
    _create_person,
    _person_read,
    _person_reads,
    _resolve_person,
    _set_aliases,
    get_person_or_404,
    normalize_aliases,
    person_involved_task_ids,
    person_requester_task_ids,
    person_task_ids,
    task_person_ids,
)

router = APIRouter(prefix="/api/people", tags=["people"])
# The task- and item-side link endpoints, mounted at their natural paths.
link_router = APIRouter(tags=["people"])


# --- directory -------------------------------------------------------------
@router.get("", response_model=list[PersonRead])
def list_people(session: Session = Depends(get_session)) -> list[PersonRead]:
    """List people by name (case-insensitive), each with their link counts."""
    people = session.exec(select(Person).order_by(func.lower(col(Person.name)))).all()
    return _person_reads(session, list(people))


@router.post("", response_model=PersonRead, status_code=201)
def create_person(payload: PersonCreate, session: Session = Depends(get_session)) -> PersonRead:
    return _person_read(session, _create_person(session, payload))


@router.get("/{person_id}", response_model=PersonDetail)
def get_person(person_id: str, session: Session = Depends(get_session)) -> PersonDetail:
    person = get_person_or_404(session, person_id)
    data = _person_read(session, person)
    task_ids = person_task_ids(session, person.id)
    involved_task_ids = person_involved_task_ids(session, person.id)
    requester_task_ids = person_requester_task_ids(session, person.id)
    item_ids = [
        link.item_id for link in session.exec(select(ItemPerson).where(ItemPerson.person_id == person.id)).all()
    ]
    return PersonDetail(
        **data.model_dump(),
        task_ids=task_ids,
        involved_task_ids=involved_task_ids,
        requester_task_ids=requester_task_ids,
        item_ids=item_ids,
    )


@router.patch("/{person_id}", response_model=PersonRead)
def update_person(person_id: str, payload: PersonUpdate, session: Session = Depends(get_session)) -> PersonRead:
    person = get_person_or_404(session, person_id)
    data = payload.model_dump(exclude_unset=True)
    aliases = data.pop("aliases", None)
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        data["name"] = name
    for key, value in data.items():
        setattr(person, key, value)
    person.updated_at = utcnow()
    session.add(person)
    session.commit()
    session.refresh(person)
    if aliases is not None:
        _set_aliases(session, person.id, normalize_aliases(aliases))
    return _person_read(session, person)


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: str, session: Session = Depends(get_session)) -> None:
    person = get_person_or_404(session, person_id)
    # A task may be waiting on this person; the FK would block the delete, and
    # the wait has no meaning without them.
    session.exec(
        sa_update(Task)
        .where(col(Task.waiting_on_person_id) == person.id)
        .values(waiting_on_person_id=None, follow_up_at=None)
    )
    session.exec(sa_delete(TaskPerson).where(col(TaskPerson.person_id) == person.id))
    session.exec(sa_delete(TaskRequester).where(col(TaskRequester.person_id) == person.id))
    session.exec(sa_delete(ItemPerson).where(col(ItemPerson.person_id) == person.id))
    session.exec(sa_delete(PersonAlias).where(col(PersonAlias.person_id) == person.id))
    session.exec(sa_delete(Person).where(col(Person.id) == person.id))
    session.commit()


@router.post("/{person_id}/merge", response_model=PersonRead)
async def merge_person(person_id: str, payload: PersonMerge, session: Session = Depends(get_session)) -> PersonRead:
    """Merge the person in ``source_id`` into ``person_id``, which survives with their links."""
    target = get_person_or_404(session, person_id)
    source = get_person_or_404(session, payload.source_id)
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Cannot merge a person into themselves")
    affected_tasks = task_person_ids(session, source.id)
    merge_people(session, target, source)
    for task_id in affected_tasks:
        await bus.publish(f"task:{task_id}", {"kind": "task", "action": "people_changed"})
    return _person_read(session, target)


# --- task links ------------------------------------------------------------
@link_router.post("/api/tasks/{task_id}/people", response_model=PersonRead, status_code=201)
async def link_task_person(task_id: str, payload: PersonLink, session: Session = Depends(get_session)) -> PersonRead:
    task = get_task_or_404(session, task_id)
    person = _resolve_person(session, payload)
    if _link_task(session, task_id, person):
        add_timeline(session, task_id, "person_added", f"Person added: {person.name}", {"person_id": person.id})
    apply_task_templates(session, task)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "people_changed"})
    return _person_read(session, person)


@link_router.delete("/api/tasks/{task_id}/people/{person_id}", status_code=204)
async def unlink_task_person(task_id: str, person_id: str, session: Session = Depends(get_session)) -> None:
    task = get_task_or_404(session, task_id)
    link = session.exec(
        select(TaskPerson).where(TaskPerson.task_id == task_id, TaskPerson.person_id == person_id)
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    session.delete(link)
    session.commit()
    person = session.get(Person, person_id)
    add_timeline(
        session,
        task_id,
        "person_removed",
        f"Person removed: {person.name if person else person_id}",
        {"person_id": person_id},
    )
    apply_task_templates(session, task)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "people_changed"})


# --- task requesters -------------------------------------------------------
@link_router.post("/api/tasks/{task_id}/requesters", response_model=PersonRead, status_code=201)
async def link_task_requester(task_id: str, payload: PersonLink, session: Session = Depends(get_session)) -> PersonRead:
    """Link a person who requested the task, separately from the people it involves."""
    task = get_task_or_404(session, task_id)
    person = _resolve_person(session, payload)
    if _link_requester(session, task_id, person):
        add_timeline(session, task_id, "requester_added", f"Requester added: {person.name}", {"person_id": person.id})
    apply_task_templates(session, task)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "requesters_changed"})
    return _person_read(session, person)


@link_router.delete("/api/tasks/{task_id}/requesters/{person_id}", status_code=204)
async def unlink_task_requester(task_id: str, person_id: str, session: Session = Depends(get_session)) -> None:
    task = get_task_or_404(session, task_id)
    link = session.exec(
        select(TaskRequester).where(TaskRequester.task_id == task_id, TaskRequester.person_id == person_id)
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    session.delete(link)
    session.commit()
    person = session.get(Person, person_id)
    add_timeline(
        session,
        task_id,
        "requester_removed",
        f"Requester removed: {person.name if person else person_id}",
        {"person_id": person_id},
    )
    apply_task_templates(session, task)
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "requesters_changed"})


# --- item links ------------------------------------------------------------
@link_router.post("/api/items/{item_id}/people", response_model=PersonRead, status_code=201)
def link_item_person(item_id: str, payload: PersonLink, session: Session = Depends(get_session)) -> PersonRead:
    if session.get(SourceItem, item_id) is None:
        raise HTTPException(status_code=404, detail="Item not found")
    person = _resolve_person(session, payload)
    _link_item(session, item_id, person)
    return _person_read(session, person)


@link_router.delete("/api/items/{item_id}/people/{person_id}", status_code=204)
def unlink_item_person(item_id: str, person_id: str, session: Session = Depends(get_session)) -> None:
    link = session.exec(
        select(ItemPerson).where(ItemPerson.item_id == item_id, ItemPerson.person_id == person_id)
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    session.delete(link)
    session.commit()


__all__ = ["router", "link_router"]
