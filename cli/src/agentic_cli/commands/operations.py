"""CLI commands."""

from __future__ import annotations

from typing import Literal

from cyclopts import App

from .. import runtime
from ..render import (
    _join,
    _operation_line,
)
from ..runtime import (
    emit,
    safe,
)

operation_app = App(name="operation", help="Read the audit log of mutating operations.")


def register(app: App) -> None:
    app.command(operation_app)


@operation_app.command(name="list")
@safe
def operation_list(
    client: Literal["web", "cli", "api"] | None = None,
    actor: Literal["human", "agent"] | None = None,
    limit: int = 100,
) -> str:
    """List recorded operations, newest first."""
    with runtime._client() as c:
        operations = c.list_operations(client=client, actor=actor, limit=limit)
    return emit(operations, _join(operations, _operation_line))
