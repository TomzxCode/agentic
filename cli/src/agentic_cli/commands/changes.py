"""CLI commands."""

from __future__ import annotations

from cyclopts import App

from .. import runtime
from ..render import (
    _change_line,
    _change_text,
    _join,
)
from ..runtime import (
    ChangeClassArg,
    ChangeStatusArg,
    InterventionArg,
    emit,
    safe,
)

change_app = App(name="change", help="Record the factory changes the metrics are computed from.")


def register(app: App) -> None:
    app.command(change_app)


@change_app.command(name="list")
@safe
def change_list(
    task_id: str | None = None,
    status: ChangeStatusArg | None = None,
    change_class: ChangeClassArg | None = None,
) -> str:
    """List changes, newest first."""
    with runtime._client() as client:
        changes = client.list_changes(task_id=task_id, status=status, change_class=change_class)
    return emit(changes, _join(changes, _change_line))


@change_app.command(name="get")
@safe
def change_get(change_id: str) -> str:
    """Show a change with its interventions."""
    with runtime._client() as client:
        change = client.get_change(change_id)
    return emit(change, _change_text(change))


@change_app.command(name="create")
@safe
def change_create(
    task_id: str,
    title: str = "",
    change_class: ChangeClassArg = "feature",
    external_ref: str | None = None,
    repository_id: str | None = None,
    worktree_id: str | None = None,
    notes: str = "",
) -> str:
    """Record a change against a task."""
    with runtime._client() as client:
        change = client.create_change(
            task_id=task_id,
            title=title,
            change_class=change_class,
            external_ref=external_ref,
            repository_id=repository_id,
            worktree_id=worktree_id,
            notes=notes,
        )
    return emit(change, f"created change {change['id']}  {_change_line(change)}")


def _transition(change_id: str, status: str) -> str:
    with runtime._client() as client:
        change = client.transition_change(change_id, status)
    return emit(change, f"{status}: {_change_line(change)}")


@change_app.command(name="verify")
@safe
def change_verify(change_id: str) -> str:
    """Mark a change verified."""
    return _transition(change_id, "verified")


@change_app.command(name="accept")
@safe
def change_accept(change_id: str) -> str:
    """Mark a change accepted (reached production)."""
    return _transition(change_id, "accepted")


@change_app.command(name="reject")
@safe
def change_reject(change_id: str) -> str:
    """Reject a change before acceptance."""
    return _transition(change_id, "rejected")


@change_app.command(name="revert")
@safe
def change_revert(change_id: str) -> str:
    """Mark an accepted change reverted (it did not survive observation)."""
    return _transition(change_id, "reverted")


@change_app.command(name="intervene")
@safe
def change_intervene(change_id: str, kind: InterventionArg = "other", note: str = "") -> str:
    """Record a human intervention, which makes the change non-touchless."""
    with runtime._client() as client:
        intervention = client.add_intervention(change_id, kind=kind, note=note)
    return emit(intervention, f"intervened ({kind}) on {change_id}")


@change_app.command(name="delete")
@safe
def change_delete(change_id: str) -> str:
    """Delete a change and its interventions."""
    with runtime._client() as client:
        client.delete_change(change_id)
    return emit({"deleted": change_id}, f"deleted {change_id}")
