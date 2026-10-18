"""CLI commands."""

from __future__ import annotations

from cyclopts import App

from .. import runtime
from ..runtime import (
    CONTEXT,
    emit,
    safe,
)


def register(app: App) -> None:
    app.command(name="health")(health)


@safe
def health() -> str:
    """Check that the API is reachable."""
    with runtime._client() as client:
        data = client.health()
    return emit(data, f"{data.get('status')} ({data.get('service')}) at {CONTEXT['api_url']}")
