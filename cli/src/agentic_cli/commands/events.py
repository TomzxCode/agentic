"""CLI commands for sending events through Slack."""

from __future__ import annotations

from cyclopts import App

from .. import runtime
from ..runtime import emit, safe

events_app = App(name="events", help="Send events through Slack.")


def register(app) -> None:
    app.command(events_app)


@events_app.command(name="send-slack")
@safe
def events_send_slack(
    event_id: str | None = None,
    user_id: str | None = None,
    task_id: str | None = None,
    text: str | None = None,
) -> str:
    """Send one event (or recent events) to Slack."""
    body = {}
    if user_id:
        body["user_id"] = user_id
    if task_id:
        body["task_id"] = task_id
    if text:
        body["text"] = text
    with runtime._client() as client:
        if event_id:
            result = client.send_event_to_slack(event_id, body)
        else:
            result = client.send_events_to_slack(body)
    return emit(result, f"sent {result.get('count', 1)} event(s) to Slack")