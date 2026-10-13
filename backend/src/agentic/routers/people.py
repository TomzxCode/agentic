"""People: the directory of individuals a task or a source item involves.

A person is a flat directory entry (a name plus optional contact details). Links
to tasks and to items are many-to-many and idempotent: linking a person already
linked returns the existing association rather than creating a duplicate. The
task-side link endpoints live here (rather than in the tasks router) so all the
people logic stays in one module.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlmodel import Session, col, select

from ..crud import add_timeline, get_task_or_404
from ..db import get_session
from ..events import bus
from ..models import ItemPerson, Person, PersonAlias, SourceItem, TaskPerson, utcnow
from ..schemas import PersonCreate, PersonDetail, PersonLink, PersonRead, PersonUpdate

router = APIRouter(prefix="/api/people", tags=["people"])
# The task- and item-side link endpoints, mounted at their natural paths.
link_router = APIRouter(tags=["people"])


def get_person_or_404(session: Session, person_id: str) -> Person:
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


def normalize_aliases(values: list[str] | None) -> list[str]:
    """Trim, drop empties, and de-duplicate aliases case-insensitively, keeping order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = str(value).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def person_aliases(session: Session, person_id: str) -> list[str]:
    """A person's aliases, in the order they were added."""
    rows = session.exec(
        select(PersonAlias).where(PersonAlias.person_id == person_id).order_by(col(PersonAlias.created_at))
    ).all()
    return [row.value for row in rows]


def _set_aliases(session: Session, person_id: str, values: list[str]) -> None:
    """Replace a person's aliases with exactly ``values`` (already normalized)."""
    session.exec(sa_delete(PersonAlias).where(col(PersonAlias.person_id) == person_id))
    for value in values:
        session.add(PersonAlias(person_id=person_id, value=value))
    session.commit()


def _add_aliases(session: Session, person_id: str, values: list[str]) -> bool:
    """Add aliases a person does not already have; return True when any were added."""
    existing = {row.value.lower() for row in session.exec(select(PersonAlias).where(PersonAlias.person_id == person_id)).all()}
    added = False
    for value in values:
        if value.lower() in existing:
            continue
        session.add(PersonAlias(person_id=person_id, value=value))
        existing.add(value.lower())
        added = True
    if added:
        session.commit()
    return added


def _find_by_alias(session: Session, values: list[str]) -> Person | None:
    """The person carrying any of the given aliases (case-insensitive), if any."""
    for value in values:
        row = session.exec(select(PersonAlias).where(func.lower(col(PersonAlias.value)) == value.lower())).first()
        if row is not None:
            person = session.get(Person, row.person_id)
            if person is not None:
                return person
    return None


def _person_read(session: Session, person: Person) -> PersonRead:
    data = PersonRead.model_validate(person)
    data.aliases = person_aliases(session, person.id)
    data.task_count = len(session.exec(select(TaskPerson).where(TaskPerson.person_id == person.id)).all())
    data.item_count = len(session.exec(select(ItemPerson).where(ItemPerson.person_id == person.id)).all())
    return data


def _create_person(session: Session, payload: PersonCreate) -> Person:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    person = Person(name=name, notes=payload.notes or "")
    session.add(person)
    session.commit()
    session.refresh(person)
    _add_aliases(session, person.id, normalize_aliases(payload.aliases))
    return person


def _resolve_person(session: Session, payload: PersonLink) -> Person:
    """An existing person by id, or a newly created one from the given name."""
    if payload.person_id:
        return get_person_or_404(session, payload.person_id)
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provide person_id or name")
    return _create_person(session, PersonCreate(name=name))


def task_people(session: Session, task_id: str) -> list[Person]:
    """The people linked to a task, in link order."""
    links = session.exec(
        select(TaskPerson).where(TaskPerson.task_id == task_id).order_by(col(TaskPerson.created_at))
    ).all()
    people: list[Person] = []
    for link in links:
        person = session.get(Person, link.person_id)
        if person is not None:
            people.append(person)
    return people


def task_person_ids(session: Session, task_id: str) -> list[str]:
    """The ids of people linked to a task, in link order."""
    links = session.exec(
        select(TaskPerson).where(TaskPerson.task_id == task_id).order_by(col(TaskPerson.created_at))
    ).all()
    return [link.person_id for link in links]


def item_person_ids(session: Session, item_id: str) -> list[str]:
    return [link.person_id for link in session.exec(select(ItemPerson).where(ItemPerson.item_id == item_id)).all()]


def _link_task(session: Session, task_id: str, person: Person) -> bool:
    """Link a person to a task; return True when a new link was created."""
    existing = session.exec(
        select(TaskPerson).where(TaskPerson.task_id == task_id, TaskPerson.person_id == person.id)
    ).first()
    if existing is not None:
        return False
    session.add(TaskPerson(task_id=task_id, person_id=person.id))
    session.commit()
    return True


def _link_item(session: Session, item_id: str, person: Person) -> bool:
    existing = session.exec(
        select(ItemPerson).where(ItemPerson.item_id == item_id, ItemPerson.person_id == person.id)
    ).first()
    if existing is not None:
        return False
    session.add(ItemPerson(item_id=item_id, person_id=person.id))
    session.commit()
    return True


def upsert_person(
    session: Session,
    *,
    name: str,
    aliases: list[str] | None = None,
    handle: str | None = None,
    email: str | None = None,
) -> Person | None:
    """Find a person by alias (then by name), creating one when absent.

    Aliases (a GitHub login, a Slack user id, an email) are the identity used to
    de-duplicate auto-populated people across sources. ``handle`` and ``email``
    are accepted for callers that have them as separate fields and are folded
    into the alias list.
    """
    values = normalize_aliases([*(aliases or []), handle or "", email or ""])
    name = (name or "").strip() or (values[0] if values else "")
    if not name:
        return None
    existing = _find_by_alias(session, values)
    if existing is None:
        existing = session.exec(select(Person).where(func.lower(col(Person.name)) == name.lower())).first()
    if existing is not None:
        _add_aliases(session, existing.id, values)
        return existing
    person = Person(name=name)
    session.add(person)
    session.commit()
    session.refresh(person)
    _add_aliases(session, person.id, values)
    return person


def link_people_to_item(session: Session, item_id: str, people: list[dict[str, Any]]) -> list[str]:
    """Upsert and link the people a source's metadata named to an item."""
    linked: list[str] = []
    for entry in people or []:
        if not isinstance(entry, dict):
            continue
        person = upsert_person(
            session,
            name=str(entry.get("name") or entry.get("handle") or ""),
            aliases=entry.get("aliases"),
            handle=entry.get("handle"),
            email=entry.get("email"),
        )
        if person is not None and _link_item(session, item_id, person):
            linked.append(person.id)
    return linked


def link_item_people_to_task(session: Session, task_id: str, item_id: str) -> list[str]:
    """Link everyone already on an item to a task, so a linked source brings its people."""
    linked: list[str] = []
    for person_id in item_person_ids(session, item_id):
        person = session.get(Person, person_id)
        if person is not None and _link_task(session, task_id, person):
            linked.append(person.id)
            add_timeline(session, task_id, "person_added", f"Person added: {person.name}", {"person_id": person.id})
    return linked


# --- directory -------------------------------------------------------------
@router.get("", response_model=list[PersonRead])
def list_people(session: Session = Depends(get_session)) -> list[PersonRead]:
    """List people by name (case-insensitive), each with their link counts."""
    people = session.exec(select(Person).order_by(func.lower(col(Person.name)))).all()
    return [_person_read(session, person) for person in people]


@router.post("", response_model=PersonRead, status_code=201)
def create_person(payload: PersonCreate, session: Session = Depends(get_session)) -> PersonRead:
    return _person_read(session, _create_person(session, payload))


@router.get("/{person_id}", response_model=PersonDetail)
def get_person(person_id: str, session: Session = Depends(get_session)) -> PersonDetail:
    person = get_person_or_404(session, person_id)
    data = _person_read(session, person)
    task_ids = [
        link.task_id for link in session.exec(select(TaskPerson).where(TaskPerson.person_id == person.id)).all()
    ]
    item_ids = [
        link.item_id for link in session.exec(select(ItemPerson).where(ItemPerson.person_id == person.id)).all()
    ]
    return PersonDetail(**data.model_dump(), task_ids=task_ids, item_ids=item_ids)


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
    session.exec(sa_delete(TaskPerson).where(col(TaskPerson.person_id) == person.id))
    session.exec(sa_delete(ItemPerson).where(col(ItemPerson.person_id) == person.id))
    session.exec(sa_delete(PersonAlias).where(col(PersonAlias.person_id) == person.id))
    session.exec(sa_delete(Person).where(col(Person.id) == person.id))
    session.commit()


# --- task links ------------------------------------------------------------
@link_router.post("/api/tasks/{task_id}/people", response_model=PersonRead, status_code=201)
async def link_task_person(task_id: str, payload: PersonLink, session: Session = Depends(get_session)) -> PersonRead:
    get_task_or_404(session, task_id)
    person = _resolve_person(session, payload)
    if _link_task(session, task_id, person):
        add_timeline(session, task_id, "person_added", f"Person added: {person.name}", {"person_id": person.id})
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "people_changed"})
    return _person_read(session, person)


@link_router.delete("/api/tasks/{task_id}/people/{person_id}", status_code=204)
async def unlink_task_person(task_id: str, person_id: str, session: Session = Depends(get_session)) -> None:
    get_task_or_404(session, task_id)
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
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "people_changed"})


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


__all__ = [
    "router",
    "link_router",
    "item_person_ids",
    "link_item_people_to_task",
    "link_people_to_item",
    "normalize_aliases",
    "person_aliases",
    "task_people",
    "task_person_ids",
    "upsert_person",
]
