"""CLI commands."""

from __future__ import annotations

import sys

from cyclopts import App

from .. import runtime
from ..runtime import (
    Source,
    emit,
    safe,
)

link_app = App(name="link", help="Associate items with tasks.")


def register(app: App) -> None:
    app.command(link_app)


@link_app.command(name="add")
@safe
def link_add(
    task_id: str,
    item_id: str | None = None,
    source: Source | None = None,
    url: str | None = None,
    title: str = "",
    content: str = "",
    external_id: str | None = None,
    note: str = "",
    fetch: bool = True,
) -> str | int:
    """Associate an existing item (--item-id) or a new one (--url/--content) with a task."""
    item = None
    if item_id is None:
        if not (url or content or title):
            print("error: provide --item-id, or a --url/--content for a new item", file=sys.stderr)
            return 1
        item = {
            "source": source,
            "url": url,
            "title": title,
            "content": content,
            "external_id": external_id,
            "fetch": fetch,
        }
    with runtime._client() as client:
        association = client.associate(task_id, item_id=item_id, item=item, note=note)
    return emit(association, f"linked {association['item']['id']} to {task_id}")


@link_app.command(name="remove")
@safe
def link_remove(task_id: str, item_id: str) -> str:
    """Remove an item's association with a task."""
    with runtime._client() as client:
        client.unassociate(task_id, item_id)
    return emit({"unlinked": item_id}, f"unlinked {item_id} from {task_id}")
