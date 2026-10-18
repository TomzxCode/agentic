"""People mutations: create/resolve, link, upsert, and merge.

Mounted from ``people.py`` and reused by item/task linking; the read side
lives in ``people_service``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlmodel import Session, col, select

from ..crud import add_timeline
from ..models.base import utcnow
from ..models.items import ItemPerson, Person, PersonAlias, TaskPerson, TaskRequester
from .people_service import (
    _add_aliases,
    _find_by_alias,
    item_person_ids,
    normalize_aliases,
)


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


def _link_requester(session: Session, task_id: str, person: Person) -> bool:
    """Link a person as a requester of a task; return True when a new link was created."""
    existing = session.exec(
        select(TaskRequester).where(TaskRequester.task_id == task_id, TaskRequester.person_id == person.id)
    ).first()
    if existing is not None:
        return False
    session.add(TaskRequester(task_id=task_id, person_id=person.id))
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


def merge_people(session: Session, target: Person, source: Person) -> Person:
    """Move every alias, task link, and item link from ``source`` onto ``target``, then delete ``source``.

    A link the target already holds (both people on the same task or item) is
    dropped rather than moved, since ``taskperson`` and ``itemperson`` are unique
    per pair; an alias the target already carries is likewise dropped. A task
    that gains the target records a ``person_added`` timeline event.
    """
    # Aliases: move the ones the target lacks, drop the rest as duplicates.
    target_values = {
        row.value.lower() for row in session.exec(select(PersonAlias).where(PersonAlias.person_id == target.id)).all()
    }
    for alias in session.exec(select(PersonAlias).where(PersonAlias.person_id == source.id)).all():
        if alias.value.lower() in target_values:
            session.delete(alias)
        else:
            alias.person_id = target.id
            session.add(alias)
            target_values.add(alias.value.lower())
    session.commit()

    # Tasks: move the links the target lacks, drop duplicates, record the gain.
    for link in session.exec(select(TaskPerson).where(TaskPerson.person_id == source.id)).all():
        task_id = link.task_id
        existing = session.exec(
            select(TaskPerson).where(TaskPerson.task_id == task_id, TaskPerson.person_id == target.id)
        ).first()
        if existing is not None:
            session.delete(link)
        else:
            link.person_id = target.id
            session.add(link)
            add_timeline(session, task_id, "person_added", f"Person added: {target.name}", {"person_id": target.id})
        session.commit()

    # Requesters: the same, as a link set of its own.
    for link in session.exec(select(TaskRequester).where(TaskRequester.person_id == source.id)).all():
        task_id = link.task_id
        existing = session.exec(
            select(TaskRequester).where(TaskRequester.task_id == task_id, TaskRequester.person_id == target.id)
        ).first()
        if existing is not None:
            session.delete(link)
        else:
            link.person_id = target.id
            session.add(link)
            add_timeline(
                session, task_id, "requester_added", f"Requester added: {target.name}", {"person_id": target.id}
            )
        session.commit()

    # Items: the same, with no timeline (items have none).
    for link in session.exec(select(ItemPerson).where(ItemPerson.person_id == source.id)).all():
        existing = session.exec(
            select(ItemPerson).where(ItemPerson.item_id == link.item_id, ItemPerson.person_id == target.id)
        ).first()
        if existing is not None:
            session.delete(link)
        else:
            link.person_id = target.id
            session.add(link)
        session.commit()

    target.updated_at = utcnow()
    session.add(target)
    session.exec(sa_delete(PersonAlias).where(col(PersonAlias.person_id) == source.id))
    session.exec(sa_delete(TaskRequester).where(col(TaskRequester.person_id) == source.id))
    session.exec(sa_delete(Person).where(col(Person.id) == source.id))
    session.commit()
    session.refresh(target)
    return target


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
