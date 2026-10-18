"""CLI commands."""

from __future__ import annotations

from cyclopts import App

from .. import runtime
from ..render import _join
from ..runtime import (
    emit,
    safe,
)

tag_app = App(name="tag", help="Inspect the tags carried by tasks.")


def register(app: App) -> None:
    app.command(tag_app)


@tag_app.command(name="list")
@safe
def tag_list() -> str:
    """List the tags in use, with how many tasks carry each."""
    with runtime._client() as client:
        tags = client.list_tags()
    return emit(tags, _join(tags, lambda t: f"{t['name']}  ({t['count']})"))
