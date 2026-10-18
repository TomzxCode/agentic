"""CLI commands."""

from __future__ import annotations

import sys
from typing import Literal

from cyclopts import App

from .. import runtime
from ..render import (
    _join,
    _stack_line,
)
from ..runtime import (
    emit,
    safe,
)

stack_app = App(name="stack", help="Work the focus stack: the current task and the queue below it.")


def register(app: App) -> None:
    app.command(stack_app)


@stack_app.command(name="list")
@safe
def stack_list() -> str:
    """Show the stack, the current task first."""
    with runtime._client() as client:
        entries = client.list_stack()
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="current")
@safe
def stack_current() -> str:
    """Show the current task (the top of the stack)."""
    with runtime._client() as client:
        entry = client.stack_current()
    if entry is None:
        return emit(None, "(stack is empty)")
    return emit(entry, _stack_line(entry))


@stack_app.command(name="history")
@safe
def stack_history() -> str:
    """Show the soft-deleted stack history, most recent first."""
    with runtime._client() as client:
        entries = client.stack_history()
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="push")
@safe
def stack_push(
    title: str = "",
    description: str = "",
    position: Literal["top", "next", "last"] = "top",
    task_id: str | None = None,
) -> str | int:
    """Add a task to the stack: a new one (--title) or an existing --task-id.

    --position picks where it lands: top (becomes current), next (after the
    current task), or last (the bottom of the queue).
    """
    if not title.strip() and not task_id:
        print("error: provide --title or --task-id", file=sys.stderr)
        return 1
    with runtime._client() as client:
        entries = client.push_stack(title=title, description=description, position=position, task_id=task_id)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="pop")
@safe
def stack_pop() -> str:
    """Pop the current task (mark it done) and promote the next one."""
    with runtime._client() as client:
        entries = client.pop_stack()
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="promote")
@safe
def stack_promote(entry_id: str) -> str:
    """Move an entry to the top of the stack (make it the current task)."""
    with runtime._client() as client:
        entries = client.promote_stack(entry_id)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="reorder")
@safe
def stack_reorder(entry_id: str, position: int) -> str:
    """Move an entry to a new position (0 is the current task)."""
    with runtime._client() as client:
        entries = client.reorder_stack(entry_id, position)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="edit")
@safe
def stack_edit(entry_id: str, title: str | None = None, description: str | None = None) -> str:
    """Edit the task behind an entry (its title and/or description)."""
    with runtime._client() as client:
        entries = client.update_stack_entry(entry_id, title=title, description=description)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="remove")
@safe
def stack_remove(entry_id: str) -> str:
    """Remove an entry from the stack (soft delete; the task is kept)."""
    with runtime._client() as client:
        client.remove_stack_entry(entry_id)
    return emit({"removed": entry_id}, f"removed {entry_id}")
