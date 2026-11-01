"""The event bus: receive a webhook delivery, store it, and fan it out.

An inbound event is persisted as a ``WebhookEvent`` first, then published on the
in-process bus and matched against the endpoint's subscriptions. Each match
starts the workflow (execution graph) it points at, passing the payload to the
graph's trigger node, and records an ``EventDelivery`` row for what happened.

This module owns the matching and dispatch rules; the router only authenticates
the request and parses the body.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from .db import engine
from .events import bus
from .graphs import EVENT_MISSING, resolve_event_value
from .models.webhooks import EventDelivery, EventSubscription, WebhookEndpoint, WebhookEvent

log = structlog.get_logger(__name__)

ENDPOINT_KINDS = ("generic", "github")

DELIVERY_STARTED = "started"
DELIVERY_SKIPPED = "skipped"
DELIVERY_FAILED = "failed"


def _text(value: Any) -> str:
    """A payload value as the text a filter compares against."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _condition_matches(payload: dict[str, Any], condition: dict[str, Any]) -> bool:
    """One filter condition, for example ``{"path": "action", "equals": "opened"}``.

    Supported operators are ``equals``, ``contains``, and ``exists``. A missing
    path only matches ``exists: false``.
    """
    path = str(condition.get("path") or "").strip()
    if not path:
        return True
    value = resolve_event_value(payload, path)
    if "exists" in condition:
        present = value is not EVENT_MISSING
        return present == bool(condition.get("exists"))
    if value is EVENT_MISSING:
        return False
    if "equals" in condition:
        return _text(value) == _text(condition.get("equals"))
    if "contains" in condition:
        return _text(condition.get("contains")) in _text(value)
    return True


def subscription_matches(subscription: EventSubscription, event_type: str, payload: dict[str, Any]) -> bool:
    """True when an event type and payload satisfy this subscription."""
    events = [str(item) for item in (subscription.events or []) if str(item).strip()]
    if events and event_type not in events:
        return False
    return all(
        _condition_matches(payload, condition)
        for condition in (subscription.filters or [])
        if isinstance(condition, dict)
    )


async def ingest_event(
    session: Session,
    endpoint: WebhookEndpoint,
    *,
    payload: dict[str, Any],
    event_type: str,
    delivery_id: str = "",
    headers: dict[str, str] | None = None,
) -> WebhookEvent:
    """Store one inbound event, publish it, and fan it out to subscriptions."""
    event = WebhookEvent(
        endpoint_id=endpoint.id,
        source=endpoint.kind,
        event_type=(event_type or "event").strip() or "event",
        delivery_id=delivery_id or "",
        payload=payload,
        headers=headers or {},
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    await bus.publish(
        "webhook",
        {
            "id": event.id,
            "endpoint_id": event.endpoint_id,
            "event_type": event.event_type,
            "delivery_id": event.delivery_id,
            "received_at": event.created_at.isoformat(),
        },
    )
    await dispatch_event(event.id)
    return event


def _event_payload(event: WebhookEvent) -> dict[str, Any]:
    """The payload a workflow sees: the body, with the event's own name added."""
    payload = dict(event.payload or {})
    payload.setdefault("event", event.event_type)
    payload.setdefault("delivery_id", event.delivery_id)
    return payload


async def dispatch_event(event_id: str) -> list[EventDelivery]:
    """Start every subscription that matches a stored event, recording each outcome."""
    from . import graphs
    from .models.graphs import ExecutionGraph

    with Session(engine) as session:
        event = session.get(WebhookEvent, event_id)
        if event is None:
            return []
        subscriptions = session.exec(
            select(EventSubscription)
            .where(col(EventSubscription.endpoint_id) == event.endpoint_id)
            .where(col(EventSubscription.enabled) == True)  # noqa: E712
        ).all()
        payload = _event_payload(event)
        event_type = event.event_type
        candidates = [
            (subscription.id, subscription.graph_id)
            for subscription in subscriptions
            if subscription_matches(subscription, event_type, payload)
        ]
        event_data = {
            "id": event.id,
            "type": event.event_type,
            "deliveryId": event.delivery_id,
            "endpointId": event.endpoint_id,
            "payload": payload,
        }

    deliveries: list[EventDelivery] = []
    for subscription_id, graph_id in candidates:
        status, execution_id, error = DELIVERY_FAILED, None, ""
        with Session(engine) as session:
            graph = session.get(ExecutionGraph, graph_id)
            if graph is None:
                error = "The workflow no longer exists"
            elif not graph.enabled:
                status, error = DELIVERY_SKIPPED, "The workflow is paused"
            else:
                try:
                    execution_id = await graphs.start_execution(
                        session, graph, trigger=f"event:{event_type}", event=event_data
                    )
                    status, error = DELIVERY_STARTED, ""
                except ValueError as exc:
                    error = str(exc)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "failed to start a workflow for an event",
                        event_id=event_id,
                        subscription_id=subscription_id,
                        error=str(exc),
                    )
                    error = str(exc)
        deliveries.append(
            _record_delivery(
                event_id,
                subscription_id,
                graph_id,
                execution_id=execution_id,
                status=status,
                error=error,
            )
        )
    return deliveries


def _record_delivery(
    event_id: str,
    subscription_id: str,
    graph_id: str,
    *,
    execution_id: str | None,
    status: str,
    error: str,
) -> EventDelivery:
    with Session(engine) as session:
        delivery = EventDelivery(
            event_id=event_id,
            subscription_id=subscription_id,
            graph_id=graph_id,
            graph_execution_id=execution_id,
            status=status,
            error=error[:500],
        )
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        session.expunge(delivery)
        return delivery


async def replay_event(event_id: str) -> list[EventDelivery]:
    """Deliver a stored event again, which starts its workflows a second time."""
    return await dispatch_event(event_id)


def delete_endpoint_rows(session: Session, endpoint_id: str) -> None:
    """Remove an endpoint with its subscriptions, events, and deliveries.

    Foreign keys are enforced, so the order is explicit: deliveries, then
    events and subscriptions, then the endpoint.
    """
    event_ids = [
        event.id
        for event in session.exec(select(WebhookEvent).where(col(WebhookEvent.endpoint_id) == endpoint_id)).all()
    ]
    subscription_ids = [
        sub.id
        for sub in session.exec(
            select(EventSubscription).where(col(EventSubscription.endpoint_id) == endpoint_id)
        ).all()
    ]
    if event_ids:
        session.exec(sa_delete(EventDelivery).where(col(EventDelivery.event_id).in_(event_ids)))
    if subscription_ids:
        session.exec(sa_delete(EventDelivery).where(col(EventDelivery.subscription_id).in_(subscription_ids)))
        session.exec(sa_delete(EventSubscription).where(col(EventSubscription.id).in_(subscription_ids)))
    if event_ids:
        session.exec(sa_delete(WebhookEvent).where(col(WebhookEvent.id).in_(event_ids)))
    session.exec(sa_delete(WebhookEndpoint).where(col(WebhookEndpoint.id) == endpoint_id))
    session.commit()


def delete_subscription_rows(session: Session, subscription_id: str) -> None:
    """Remove a subscription and the deliveries it produced."""
    session.exec(sa_delete(EventDelivery).where(col(EventDelivery.subscription_id) == subscription_id))
    session.exec(sa_delete(EventSubscription).where(col(EventSubscription.id) == subscription_id))
    session.commit()
