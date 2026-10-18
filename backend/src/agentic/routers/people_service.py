"""People service: directory helpers shared by the people, task, and item routers.

A person is a flat directory entry (a name plus optional contact details). Links
to tasks and to items are many-to-many and idempotent: linking a person already
linked returns the existing association rather than creating a duplicate. The
endpoints live in ``people.py``; the lookups, linking, and merging logic lives
here so the routers that need it share one implementation.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlmodel import Session, col, select

from ..models.items import ItemPerson, Person, PersonAlias, TaskPerson, TaskRequester
from ..schemas.people import PersonCreate, PersonLink, PersonRead


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
    existing = {
        row.value.lower() for row in session.exec(select(PersonAlias).where(PersonAlias.person_id == person_id)).all()
    }
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
    data.task_count = len(person_task_ids(session, person.id))
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


def task_requesters(session: Session, task_id: str) -> list[Person]:
    """The people who requested a task, in link order."""
    links = session.exec(
        select(TaskRequester).where(TaskRequester.task_id == task_id).order_by(col(TaskRequester.created_at))
    ).all()
    people: list[Person] = []
    for link in links:
        person = session.get(Person, link.person_id)
        if person is not None:
            people.append(person)
    return people


def task_requester_ids(session: Session, task_id: str) -> list[str]:
    """The ids of the people who requested a task, in link order."""
    links = session.exec(
        select(TaskRequester).where(TaskRequester.task_id == task_id).order_by(col(TaskRequester.created_at))
    ).all()
    return [link.person_id for link in links]


def person_task_ids(session: Session, person_id: str) -> list[str]:
    """Every task a person is attached to, as an involved person or as a requester.

    A task the person both requested and is involved in counts once.
    """
    ids = person_involved_task_ids(session, person_id)
    for task_id in person_requester_task_ids(session, person_id):
        if task_id not in ids:
            ids.append(task_id)
    return ids


def person_involved_task_ids(session: Session, person_id: str) -> list[str]:
    """The tasks a person is attached to as one of the people they involve."""
    return [link.task_id for link in session.exec(select(TaskPerson).where(TaskPerson.person_id == person_id)).all()]


def person_requester_task_ids(session: Session, person_id: str) -> list[str]:
    """The tasks a person is attached to as a requester."""
    return [
        link.task_id for link in session.exec(select(TaskRequester).where(TaskRequester.person_id == person_id)).all()
    ]


def item_person_ids(session: Session, item_id: str) -> list[str]:
    return [link.person_id for link in session.exec(select(ItemPerson).where(ItemPerson.item_id == item_id)).all()]
