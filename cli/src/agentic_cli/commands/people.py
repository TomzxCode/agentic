"""CLI commands."""

from __future__ import annotations

import sys

from cyclopts import App

from .. import runtime
from ..render import (
    _join,
    _person_line,
    _person_text,
)
from ..runtime import (
    emit,
    safe,
)

person_app = App(name="person", help="Create and manage people and their links.")


def register(app: App) -> None:
    app.command(person_app)


@person_app.command(name="list")
@safe
def person_list() -> str:
    """List people with their task and item counts."""
    with runtime._client() as client:
        people = client.list_people()
    return emit(people, _join(people, _person_line))


@person_app.command(name="get")
@safe
def person_get(person_id: str) -> str:
    """Show a person and what they are linked to."""
    with runtime._client() as client:
        person = client.get_person(person_id)
    return emit(person, _person_text(person))


@person_app.command(name="create")
@safe
def person_create(
    *,
    name: str,
    aliases: list[str] | None = None,
    notes: str = "",
) -> str:
    """Create a person. Pass --aliases once per handle or email."""
    with runtime._client() as client:
        person = client.create_person(name=name, aliases=aliases, notes=notes)
    return emit(person, f"created {person['id']}  {person['name']}")


@person_app.command(name="update")
@safe
def person_update(
    person_id: str,
    *,
    name: str | None = None,
    aliases: list[str] | None = None,
    notes: str | None = None,
) -> str:
    """Update a person's fields. --aliases replaces the whole list."""
    with runtime._client() as client:
        person = client.update_person(person_id, name=name, aliases=aliases, notes=notes)
    return emit(person, f"updated {person['id']}  {_person_line(person)}")


@person_app.command(name="delete")
@safe
def person_delete(person_id: str) -> str:
    """Delete a person and their links."""
    with runtime._client() as client:
        client.delete_person(person_id)
    return emit({"deleted": person_id}, f"deleted {person_id}")


@person_app.command(name="merge")
@safe
def person_merge(source_id: str, *, into: str) -> str:
    """Merge a person into another (--into), which absorbs their aliases and links."""
    with runtime._client() as client:
        person = client.merge_person(source_id, into)
    return emit(person, f"merged {source_id} into {person['id']}  {person['name']}")


@person_app.command(name="link")
@safe
def person_link(
    person_id: str,
    *,
    task: str | None = None,
    item: str | None = None,
    requested_by: str | None = None,
) -> str | int:
    """Link a person to a task (--task), an item (--item), or as the requester of a task (--requested-by TASK)."""
    if requested_by:
        with runtime._client() as client:
            person = client.link_requester(person_id, requested_by)
        return emit(person, f"linked {person['id']} as a requester of task {requested_by}")
    if not task and not item:
        print("error: provide --task, --item, or --requested-by", file=sys.stderr)
        return 1
    with runtime._client() as client:
        person = client.link_person(person_id, task_id=task, item_id=item)
    target = f"task {task}" if task else f"item {item}"
    return emit(person, f"linked {person['id']} to {target}")


@person_app.command(name="unlink")
@safe
def person_unlink(
    person_id: str,
    *,
    task: str | None = None,
    item: str | None = None,
    requested_by: str | None = None,
) -> str | int:
    """Unlink a person from a task (--task), an item (--item), or a task they requested (--requested-by TASK)."""
    if requested_by:
        with runtime._client() as client:
            client.unlink_requester(person_id, requested_by)
        return emit({"unlinked": person_id}, f"unlinked {person_id} as a requester of task {requested_by}")
    if not task and not item:
        print("error: provide --task, --item, or --requested-by", file=sys.stderr)
        return 1
    with runtime._client() as client:
        client.unlink_person(person_id, task_id=task, item_id=item)
    target = f"task {task}" if task else f"item {item}"
    return emit({"unlinked": person_id}, f"unlinked {person_id} from {target}")
