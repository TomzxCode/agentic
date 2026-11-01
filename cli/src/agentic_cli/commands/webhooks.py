"""CLI commands for the event bus: webhook endpoints, subscriptions, and deliveries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from cyclopts import App

from .. import runtime
from ..render import _join
from ..runtime import emit, safe

webhook_app = App(name="webhooks", help="Manage webhook endpoints and the workflows they trigger.")

EndpointKind = Literal["generic", "github"]


def register(app: App) -> None:
    app.command(webhook_app)


def _endpoint_line(row: dict) -> str:
    state = "enabled" if row.get("enabled") else "disabled"
    return (
        f"{row['id']}  {row['name']}  [{row['kind']}]  {state}"
        f"  {row.get('subscription_count', 0)} workflow(s)  {row.get('event_count', 0)} event(s)"
    )


def _endpoint_text(row: dict) -> str:
    lines = [_endpoint_line(row)]
    if row.get("description"):
        lines.append(f"  {row['description']}")
    if row.get("secret"):
        lines.append("  secret: set")
    else:
        lines.append("  secret: not set")
    return "\n".join(lines)


def _condition_text(item: dict) -> str:
    for operator in ("equals", "contains", "exists"):
        if operator in item:
            return f"{item.get('path')} {operator} {item[operator]}"
    return str(item.get("path") or "")


def _subscription_line(row: dict) -> str:
    events = ", ".join(row.get("events") or []) or "all events"
    filters = ", ".join(_condition_text(item) for item in row.get("filters") or [])
    state = "enabled" if row.get("enabled") else "disabled"
    line = f"{row['id']}  {row.get('name') or '(unnamed)'}  ->  {row.get('graph_name') or row['graph_id']}"
    line += f"  [{events}]  {state}"
    if filters:
        line += f"  filters: {filters}"
    return line


def _event_line(row: dict) -> str:
    deliveries = row.get("delivery_count", 0)
    return (
        f"{row['id']}  {row['event_type']}  from {row.get('endpoint_name') or row['endpoint_id']}"
        f"  {deliveries} delivery(s)  {row['created_at']}"
    )


def _payload(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read payload from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("The payload file must hold a JSON object")
    return value


def _filters(pairs: list[str] | None, *, contains: bool = False) -> list[dict[str, str]]:
    conditions: list[dict[str, str]] = []
    for pair in pairs or []:
        path, separator, value = pair.partition("=")
        if not separator or not path.strip():
            raise ValueError(f"Expected path=value, got '{pair}'")
        conditions.append({"path": path.strip(), ("contains" if contains else "equals"): value})
    return conditions


@webhook_app.command(name="list")
@safe
def webhook_list() -> str:
    """List webhook endpoints, newest first."""
    with runtime._client() as client:
        rows = client.list_webhook_endpoints()
    return emit(rows, _join(rows, _endpoint_line))


@webhook_app.command(name="get")
@safe
def webhook_get(endpoint_id: str) -> str:
    """Show one webhook endpoint.

    Parameters
    ----------
    endpoint_id
        The endpoint id, as shown by ``webhooks list``.
    """
    with runtime._client() as client:
        row = client.get_webhook_endpoint(endpoint_id)
    return emit(row, _endpoint_text(row))


@webhook_app.command(name="create")
@safe
def webhook_create(
    name: str,
    kind: EndpointKind = "generic",
    description: str | None = None,
    secret: str | None = None,
    disabled: bool = False,
) -> str:
    """Create a webhook entry point.

    Parameters
    ----------
    name
        A label for the endpoint.
    kind
        ``generic`` for any JSON sender, or ``github`` for GitHub's signed webhooks.
    description
        What this endpoint feeds.
    secret
        A GitHub endpoint's HMAC secret, or a shared token a generic sender must present.
    disabled
        Create the endpoint disabled instead of enabled.
    """
    with runtime._client() as client:
        row = client.create_webhook_endpoint(
            name, kind=kind, description=description, secret=secret, enabled=not disabled
        )
    return emit(row, f"created {_endpoint_line(row)}")


@webhook_app.command(name="update")
@safe
def webhook_update(
    endpoint_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    kind: EndpointKind | None = None,
    secret: str | None = None,
    enable: bool = False,
    disable: bool = False,
) -> str:
    """Update a webhook endpoint, or enable/disable it.

    Parameters
    ----------
    endpoint_id
        The endpoint id, as shown by ``webhooks list``.
    name
        New label.
    description
        New description.
    kind
        New kind: generic or github.
    secret
        New secret. Pass an empty string to clear it.
    enable
        Accept events again.
    disable
        Stop accepting events.
    """
    fields: dict[str, Any] = {
        "name": name,
        "description": description,
        "kind": kind,
        "secret": secret,
    }
    if enable:
        fields["enabled"] = True
    if disable:
        fields["enabled"] = False
    with runtime._client() as client:
        row = client.update_webhook_endpoint(endpoint_id, **fields)
    return emit(row, _endpoint_text(row))


@webhook_app.command(name="delete")
@safe
def webhook_delete(endpoint_id: str) -> str:
    """Delete an endpoint with its subscriptions and stored events.

    Parameters
    ----------
    endpoint_id
        The endpoint id, as shown by ``webhooks list``.
    """
    with runtime._client() as client:
        client.delete_webhook_endpoint(endpoint_id)
    return emit({"deleted": endpoint_id}, f"deleted {endpoint_id}")


@webhook_app.command(name="subscribe")
@safe
def webhook_subscribe(
    endpoint_id: str,
    graph_id: str,
    name: str = "",
    event: list[str] | None = None,
    filter: list[str] | None = None,
    filter_contains: list[str] | None = None,
    disabled: bool = False,
) -> str:
    """Wire an execution graph to an endpoint.

    Parameters
    ----------
    endpoint_id
        The endpoint id, as shown by ``webhooks list``.
    graph_id
        The execution graph that should run, as shown by ``graphs list``.
    name
        A label for the subscription.
    event
        An event type to accept (for example ``pull_request``); repeat it for several.
        Omitted means every event the endpoint receives.
    filter
        A payload condition written ``path=value`` (for example ``action=opened``); repeatable.
    filter_contains
        A payload condition where the value must appear inside the field, ``path=text``; repeatable.
    disabled
        Create the subscription disabled.
    """
    with runtime._client() as client:
        row = client.create_webhook_subscription(
            endpoint_id,
            graph_id,
            name=name,
            events=event,
            filters=[*_filters(filter), *_filters(filter_contains, contains=True)],
            enabled=not disabled,
        )
    return emit(row, f"subscribed {_subscription_line(row)}")


@webhook_app.command(name="subscriptions")
@safe
def webhook_subscriptions(endpoint_id: str | None = None) -> str:
    """List subscriptions, optionally only one endpoint's.

    Parameters
    ----------
    endpoint_id
        Show only the workflows wired to this endpoint.
    """
    with runtime._client() as client:
        rows = client.list_webhook_subscriptions(endpoint_id)
    return emit(rows, _join(rows, _subscription_line))


@webhook_app.command(name="unsubscribe")
@safe
def webhook_unsubscribe(subscription_id: str) -> str:
    """Remove a subscription (the endpoint and its history stay).

    Parameters
    ----------
    subscription_id
        The subscription id, as shown by ``webhooks subscriptions``.
    """
    with runtime._client() as client:
        client.delete_webhook_subscription(subscription_id)
    return emit({"deleted": subscription_id}, f"removed {subscription_id}")


@webhook_app.command(name="events")
@safe
def webhook_events(endpoint_id: str | None = None, event_type: str | None = None, limit: int = 50) -> str:
    """List stored inbound events, newest first.

    Parameters
    ----------
    endpoint_id
        Show only this endpoint's events.
    event_type
        Show only this event type, for example ``pull_request``.
    limit
        Maximum number of events to list.
    """
    with runtime._client() as client:
        rows = client.list_webhook_events(endpoint_id, event_type, limit)
    return emit(rows, _join(rows, _event_line))


@webhook_app.command(name="event")
@safe
def webhook_event(event_id: str) -> str:
    """Show one stored event with its payload and the workflows it started.

    Parameters
    ----------
    event_id
        The event id, as shown by ``webhooks events``.
    """
    with runtime._client() as client:
        row = client.get_webhook_event(event_id)
    lines = [_event_line(row), json.dumps(row.get("payload") or {}, indent=2, ensure_ascii=False)]
    for delivery in row.get("deliveries") or []:
        target = delivery.get("graph_name") or delivery["graph_id"]
        status = delivery["status"]
        if delivery.get("graph_execution_id"):
            status += f" -> execution {delivery['graph_execution_id']}"
        if delivery.get("error"):
            status += f" ({delivery['error']})"
        lines.append(f"  {delivery.get('subscription_name') or delivery['subscription_id']}: {target}  {status}")
    return emit(row, "\n".join(lines))


@webhook_app.command(name="replay")
@safe
def webhook_replay(event_id: str) -> str:
    """Deliver a stored event to its workflows again.

    Parameters
    ----------
    event_id
        The event id, as shown by ``webhooks events``.
    """
    with runtime._client() as client:
        result = client.replay_webhook_event(event_id)
    return emit(result, f"replayed {event_id}: {len(result.get('deliveries') or [])} delivery(s)")


@webhook_app.command(name="test")
@safe
def webhook_test(
    endpoint_id: str,
    event_type: str = "test",
    payload: str | None = None,
) -> str:
    """Send a sample event through an endpoint, skipping its secret.

    Parameters
    ----------
    endpoint_id
        The endpoint id, as shown by ``webhooks list``.
    event_type
        The event type the sample carries, so matching subscriptions fire.
    payload
        Path to a JSON object to use as the payload.
    """
    with runtime._client() as client:
        result = client.test_webhook_endpoint(endpoint_id, event_type=event_type, payload=_payload(payload))
    return emit(result, f"sent {event_type}: {len(result.get('deliveries') or [])} delivery(s)")
