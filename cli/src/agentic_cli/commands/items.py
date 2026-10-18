"""CLI commands."""

from __future__ import annotations

from cyclopts import App

from .. import runtime
from ..render import (
    _item_line,
    _join,
)
from ..runtime import (
    Source,
    emit,
    safe,
)

item_app = App(name="item", help="Create and manage source items (Slack/GitHub/Drive/URL/note).")


def register(app: App) -> None:
    app.command(item_app)


@item_app.command(name="list")
@safe
def item_list(source: Source | None = None) -> str:
    """List items."""
    with runtime._client() as client:
        items = client.list_items(source=source)
    return emit(items, _join(items, _item_line))


@item_app.command(name="get")
@safe
def item_get(item_id: str) -> str:
    """Show an item."""
    with runtime._client() as client:
        item = client.get_item(item_id)
    return emit(item, _item_line(item))


@item_app.command(name="create")
@safe
def item_create(
    source: Source | None = None,
    url: str | None = None,
    title: str = "",
    content: str = "",
    external_id: str | None = None,
    fetch: bool = True,
) -> str:
    """Create an item (source is inferred from the url/content; fetches unless --no-fetch)."""
    with runtime._client() as client:
        item = client.create_item(
            source=source, url=url, title=title, content=content, external_id=external_id, fetch=fetch
        )
    return emit(item, f"created {item['id']}  {_item_line(item)}")


@item_app.command(name="refresh")
@safe
def item_refresh(item_id: str) -> str:
    """Re-fetch an item's metadata/content."""
    with runtime._client() as client:
        item = client.refresh_item(item_id)
    return emit(item, f"refreshed {item['id']}  {_item_line(item)}")


@item_app.command(name="refresh-due")
@safe
def item_refresh_due() -> str:
    """Re-fetch the Slack/GitHub items the refresh policy says are due."""
    with runtime._client() as client:
        report = client.refresh_due_items()
    text = (
        f"checked {report['checked']}  due {report['due']}  refreshed {report['refreshed']}  failed {report['failed']}"
    )
    for entry in report.get("items") or []:
        marker = "ok" if entry.get("refreshed") else "fail"
        text += f"\n  {marker}  {entry['source']}  {entry['title'] or entry['item_id']}"
    return emit(report, text)


@item_app.command(name="refresh-source")
@safe
def item_refresh_source(source: str) -> str:
    """Re-fetch every item of one source now, ignoring the refresh policy."""
    with runtime._client() as client:
        report = client.refresh_source(source)
    text = f"checked {report['checked']}  refreshed {report['refreshed']}  failed {report['failed']}"
    for entry in report.get("items") or []:
        marker = "ok" if entry.get("refreshed") else "fail"
        text += f"\n  {marker}  {entry['title'] or entry['item_id']}"
    return emit(report, text)


@item_app.command(name="delete")
@safe
def item_delete(item_id: str) -> str:
    """Delete an item and its associations."""
    with runtime._client() as client:
        client.delete_item(item_id)
    return emit({"deleted": item_id}, f"deleted {item_id}")
