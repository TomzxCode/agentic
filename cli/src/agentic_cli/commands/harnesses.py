"""CLI commands."""

from __future__ import annotations

from cyclopts import App

from .. import runtime
from ..render import _join
from ..runtime import (
    emit,
    safe,
)

harness_app = App(name="harness", help="Inspect and configure agent harnesses.")


def register(app: App) -> None:
    app.command(harness_app)


@harness_app.command(name="list")
@safe
def harness_list() -> str:
    """List harnesses, whether they are on PATH, and which is the default."""
    with runtime._client() as client:
        harnesses = client.list_harnesses()
    text = _join(
        harnesses,
        lambda h: (
            f"{'*' if h.get('is_default') else ' '} {h['id']:<10} "
            f"{'available' if h['available'] else 'missing':<10} {h.get('detail', '')}"
        ),
    )
    return emit(harnesses, text)


@harness_app.command(name="create")
@safe
def harness_create(
    name: str,
    command: str,
    args: list[str] | None = None,
    description: str = "",
    resume_command: str | None = None,
    model: str | None = None,
    default_model_source: str | None = None,
) -> str:
    """Add an ACP harness."""
    with runtime._client() as client:
        harness = client.create_harness(
            name=name,
            command=command,
            args=args or [],
            description=description,
            resume_command=resume_command,
            model=model,
            default_model_source=default_model_source,
        )
    return emit(harness, f"created harness {harness['id']}  {harness['command']}")


@harness_app.command(name="update")
@safe
def harness_update(
    harness_id: str,
    name: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    resume_command: str | None = None,
    model: str | None = None,
    default_model_source: str | None = None,
) -> str:
    """Update a harness."""
    with runtime._client() as client:
        harness = client.update_harness(
            harness_id,
            name=name,
            command=command,
            args=args,
            resume_command=resume_command,
            model=model,
            default_model_source=default_model_source,
        )
    return emit(harness, f"updated harness {harness['id']}")


@harness_app.command(name="delete")
@safe
def harness_delete(harness_id: str) -> str:
    """Delete a harness."""
    with runtime._client() as client:
        client.delete_harness(harness_id)
    return emit({"deleted": harness_id}, f"deleted {harness_id}")
