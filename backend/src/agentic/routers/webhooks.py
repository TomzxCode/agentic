"""Webhook endpoints, their subscriptions, and the inbound hook routes.

The management API lives under ``/api/webhooks``: endpoints, the workflows each
one feeds, and the stored deliveries. The inbound entry points are separate:
``POST /api/hooks/{endpoint}`` for any JSON sender and
``POST /api/hooks/github/{endpoint}`` for GitHub's signed webhooks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlmodel import Session, col, select

from ..crud import get_or_404
from ..db import get_session
from ..event_bus import (
    ENDPOINT_KINDS,
    delete_endpoint_rows,
    delete_subscription_rows,
    ingest_event,
    replay_event,
)
from ..models.base import utcnow
from ..models.graphs import ExecutionGraph
from ..models.webhooks import EventDelivery, EventSubscription, WebhookEndpoint, WebhookEvent
from ..schemas.webhooks import (
    EventDeliveryRead,
    EventSubscriptionCreate,
    EventSubscriptionRead,
    EventSubscriptionUpdate,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
    WebhookEventDetailRead,
    WebhookEventRead,
    WebhookResultRead,
    WebhookTestSend,
)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
hook_router = APIRouter(prefix="/api/hooks", tags=["hooks"])


# --- reading rows ----------------------------------------------------------
def _counts(session: Session, endpoint_id: str) -> tuple[int, int]:
    subscriptions = session.exec(
        select(func.count()).select_from(EventSubscription).where(col(EventSubscription.endpoint_id) == endpoint_id)
    ).one()
    events = session.exec(
        select(func.count()).select_from(WebhookEvent).where(col(WebhookEvent.endpoint_id) == endpoint_id)
    ).one()
    return int(subscriptions), int(events)


def _endpoint_read(session: Session, endpoint: WebhookEndpoint) -> WebhookEndpointRead:
    subscriptions, events = _counts(session, endpoint.id)
    return WebhookEndpointRead(
        id=endpoint.id,
        name=endpoint.name,
        description=endpoint.description,
        kind=endpoint.kind,
        secret=endpoint.secret,
        enabled=endpoint.enabled,
        subscription_count=subscriptions,
        event_count=events,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )


def _graph_names(session: Session, graph_ids: list[str]) -> dict[str, str]:
    if not graph_ids:
        return {}
    rows = session.exec(select(ExecutionGraph).where(col(ExecutionGraph.id).in_(graph_ids))).all()
    return {graph.id: graph.name for graph in rows}


def _subscription_read(
    session: Session, subscription: EventSubscription, graph_names: dict[str, str] | None = None
) -> EventSubscriptionRead:
    names = graph_names if graph_names is not None else _graph_names(session, [subscription.graph_id])
    return EventSubscriptionRead(
        id=subscription.id,
        endpoint_id=subscription.endpoint_id,
        graph_id=subscription.graph_id,
        graph_name=names.get(subscription.graph_id, ""),
        node_id=subscription.node_id,
        name=subscription.name,
        events=list(subscription.events or []),
        filters=list(subscription.filters or []),
        enabled=subscription.enabled,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


def _delivery_reads(session: Session, deliveries: list[EventDelivery]) -> list[EventDeliveryRead]:
    subscription_ids = {delivery.subscription_id for delivery in deliveries}
    subscriptions = (
        session.exec(select(EventSubscription).where(col(EventSubscription.id).in_(subscription_ids))).all()
        if subscription_ids
        else []
    )
    subscription_names = {subscription.id: subscription.name for subscription in subscriptions}
    graph_names = _graph_names(session, [delivery.graph_id for delivery in deliveries])
    return [
        EventDeliveryRead(
            id=delivery.id,
            event_id=delivery.event_id,
            subscription_id=delivery.subscription_id,
            subscription_name=subscription_names.get(delivery.subscription_id, ""),
            graph_id=delivery.graph_id,
            graph_name=graph_names.get(delivery.graph_id, ""),
            graph_execution_id=delivery.graph_execution_id,
            status=delivery.status,
            error=delivery.error,
            created_at=delivery.created_at,
        )
        for delivery in deliveries
    ]


def _event_read(session: Session, event: WebhookEvent) -> WebhookEventRead:
    endpoint = session.get(WebhookEndpoint, event.endpoint_id)
    count = session.exec(
        select(func.count()).select_from(EventDelivery).where(col(EventDelivery.event_id) == event.id)
    ).one()
    return WebhookEventRead(
        id=event.id,
        endpoint_id=event.endpoint_id,
        endpoint_name=endpoint.name if endpoint is not None else "",
        source=event.source,
        event_type=event.event_type,
        delivery_id=event.delivery_id,
        payload=event.payload or {},
        headers=event.headers or {},
        delivery_count=int(count),
        created_at=event.created_at,
    )


def _event_detail(session: Session, event: WebhookEvent) -> WebhookEventDetailRead:
    read = _event_read(session, event)
    deliveries = session.exec(
        select(EventDelivery).where(col(EventDelivery.event_id) == event.id).order_by(col(EventDelivery.created_at))
    ).all()
    return WebhookEventDetailRead(**read.model_dump(), deliveries=_delivery_reads(session, list(deliveries)))


# --- endpoint management ---------------------------------------------------
@router.get("/endpoints", response_model=list[WebhookEndpointRead])
def list_endpoints(session: Session = Depends(get_session)) -> list[WebhookEndpointRead]:
    """Every webhook entry point, newest first."""
    rows = session.exec(select(WebhookEndpoint).order_by(col(WebhookEndpoint.created_at).desc())).all()
    return [_endpoint_read(session, endpoint) for endpoint in rows]


@router.post("/endpoints", response_model=WebhookEndpointRead, status_code=201)
def create_endpoint(payload: WebhookEndpointCreate, session: Session = Depends(get_session)) -> WebhookEndpointRead:
    """Create an entry point. A GitHub endpoint needs a secret before it accepts events."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if payload.kind not in ENDPOINT_KINDS:
        raise HTTPException(status_code=400, detail="Kind must be generic or github")
    endpoint = WebhookEndpoint(
        name=name,
        description=payload.description.strip(),
        kind=payload.kind,
        secret=payload.secret.strip(),
        enabled=payload.enabled,
    )
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return _endpoint_read(session, endpoint)


@router.get("/endpoints/{endpoint_id}", response_model=WebhookEndpointRead)
def get_endpoint(endpoint_id: str, session: Session = Depends(get_session)) -> WebhookEndpointRead:
    return _endpoint_read(session, get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found"))


@router.patch("/endpoints/{endpoint_id}", response_model=WebhookEndpointRead)
def update_endpoint(
    endpoint_id: str, payload: WebhookEndpointUpdate, session: Session = Depends(get_session)
) -> WebhookEndpointRead:
    endpoint = get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        endpoint.name = name
    if data.get("description") is not None:
        endpoint.description = data["description"].strip()
    if data.get("kind") is not None:
        if data["kind"] not in ENDPOINT_KINDS:
            raise HTTPException(status_code=400, detail="Kind must be generic or github")
        endpoint.kind = data["kind"]
    if data.get("secret") is not None:
        endpoint.secret = data["secret"].strip()
    if data.get("enabled") is not None:
        endpoint.enabled = data["enabled"]
    endpoint.updated_at = utcnow()
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return _endpoint_read(session, endpoint)


@router.delete("/endpoints/{endpoint_id}", status_code=204)
def delete_endpoint(endpoint_id: str, session: Session = Depends(get_session)) -> None:
    get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found")
    delete_endpoint_rows(session, endpoint_id)


@router.get("/endpoints/{endpoint_id}/subscriptions", response_model=list[EventSubscriptionRead])
def list_subscriptions(endpoint_id: str, session: Session = Depends(get_session)) -> list[EventSubscriptionRead]:
    get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found")
    rows = session.exec(
        select(EventSubscription)
        .where(col(EventSubscription.endpoint_id) == endpoint_id)
        .order_by(col(EventSubscription.created_at))
    ).all()
    names = _graph_names(session, [row.graph_id for row in rows])
    return [_subscription_read(session, row, names) for row in rows]


@router.post("/endpoints/{endpoint_id}/subscriptions", response_model=EventSubscriptionRead, status_code=201)
def create_subscription(
    endpoint_id: str,
    payload: EventSubscriptionCreate,
    session: Session = Depends(get_session),
) -> EventSubscriptionRead:
    """Wire a workflow to an endpoint, optionally limited to event types and payload filters."""
    get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found")
    get_or_404(session, ExecutionGraph, payload.graph_id, "Workflow not found")
    subscription = EventSubscription(
        endpoint_id=endpoint_id,
        graph_id=payload.graph_id,
        name=payload.name.strip(),
        events=_clean_events(payload.events),
        filters=[condition.model_dump(exclude_none=True) for condition in payload.filters],
        enabled=payload.enabled,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return _subscription_read(session, subscription)


@router.get("/subscriptions", response_model=list[EventSubscriptionRead])
def list_all_subscriptions(
    endpoint_id: str | None = None, session: Session = Depends(get_session)
) -> list[EventSubscriptionRead]:
    query = select(EventSubscription).order_by(col(EventSubscription.created_at))
    if endpoint_id:
        query = query.where(col(EventSubscription.endpoint_id) == endpoint_id)
    rows = session.exec(query).all()
    names = _graph_names(session, [row.graph_id for row in rows])
    return [_subscription_read(session, row, names) for row in rows]


@router.patch("/subscriptions/{subscription_id}", response_model=EventSubscriptionRead)
def update_subscription(
    subscription_id: str,
    payload: EventSubscriptionUpdate,
    session: Session = Depends(get_session),
) -> EventSubscriptionRead:
    subscription = get_or_404(session, EventSubscription, subscription_id, "Subscription not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("graph_id") is not None:
        get_or_404(session, ExecutionGraph, data["graph_id"], "Workflow not found")
        subscription.graph_id = data["graph_id"]
    if data.get("name") is not None:
        subscription.name = data["name"].strip()
    if "events" in data and data["events"] is not None:
        subscription.events = _clean_events(data["events"])
    if "filters" in data and data["filters"] is not None:
        subscription.filters = [
            condition.model_dump(exclude_none=True) if hasattr(condition, "model_dump") else condition
            for condition in data["filters"]
        ]
    if data.get("enabled") is not None:
        subscription.enabled = data["enabled"]
    subscription.updated_at = utcnow()
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return _subscription_read(session, subscription)


@router.delete("/subscriptions/{subscription_id}", status_code=204)
def delete_subscription(subscription_id: str, session: Session = Depends(get_session)) -> None:
    get_or_404(session, EventSubscription, subscription_id, "Subscription not found")
    delete_subscription_rows(session, subscription_id)


def _clean_events(events: list[str] | None) -> list[str]:
    seen: list[str] = []
    for event in events or []:
        text = str(event).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


# --- event history ---------------------------------------------------------
@router.get("/events", response_model=list[WebhookEventRead])
def list_events(
    endpoint_id: str | None = None,
    event_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[WebhookEventRead]:
    """Stored deliveries, newest first."""
    query = select(WebhookEvent).order_by(col(WebhookEvent.created_at).desc()).limit(limit)
    if endpoint_id:
        query = query.where(col(WebhookEvent.endpoint_id) == endpoint_id)
    if event_type:
        query = query.where(col(WebhookEvent.event_type) == event_type)
    return [_event_read(session, event) for event in session.exec(query).all()]


@router.get("/events/{event_id}", response_model=WebhookEventDetailRead)
def get_event(event_id: str, session: Session = Depends(get_session)) -> WebhookEventDetailRead:
    return _event_detail(session, get_or_404(session, WebhookEvent, event_id, "Event not found"))


@router.post("/events/{event_id}/replay", response_model=WebhookResultRead)
async def replay_stored_event(event_id: str, session: Session = Depends(get_session)) -> WebhookResultRead:
    """Deliver a stored event to its workflows again."""
    event = get_or_404(session, WebhookEvent, event_id, "Event not found")
    deliveries = await replay_event(event_id)
    return WebhookResultRead(id=event.id, event_type=event.event_type, deliveries=_delivery_reads(session, deliveries))


@router.post("/endpoints/{endpoint_id}/test", response_model=WebhookResultRead)
async def test_endpoint(
    endpoint_id: str, payload: WebhookTestSend, session: Session = Depends(get_session)
) -> WebhookResultRead:
    """Send a sample event through the endpoint without going through its secret."""
    endpoint = get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found")
    event = await ingest_event(
        session,
        endpoint,
        payload=payload.payload,
        event_type=payload.event_type,
        delivery_id="test",
        headers={"x-agentic-test": "true"},
    )
    deliveries = session.exec(select(EventDelivery).where(col(EventDelivery.event_id) == event.id)).all()
    return WebhookResultRead(
        id=event.id, event_type=event.event_type, deliveries=_delivery_reads(session, list(deliveries))
    )


# --- inbound hooks ---------------------------------------------------------
def _payload(raw: bytes) -> dict[str, Any]:
    """The request body as an object; a non-object or non-JSON body is wrapped."""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {"body": raw.decode("utf-8", "replace")}
    return value if isinstance(value, dict) else {"body": value}


def _check_generic_secret(request: Request, secret: str) -> None:
    if not secret:
        return
    presented = request.headers.get("x-webhook-secret") or ""
    authorization = request.headers.get("authorization") or ""
    if not presented and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    presented = presented or (request.query_params.get("secret") or "")
    if not hmac.compare_digest(presented, secret):
        raise HTTPException(status_code=401, detail="The webhook secret does not match")


def _check_github_signature(request: Request, raw: bytes, secret: str) -> None:
    if not secret:
        raise HTTPException(status_code=400, detail="This GitHub endpoint has no secret configured")
    signature = request.headers.get("x-hub-signature-256") or ""
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="The GitHub signature does not match")


def _event_type(request: Request, fallback: str) -> str:
    return (
        request.query_params.get("event")
        or request.headers.get("x-event-type")
        or request.headers.get("x-github-event")
        or fallback
    ).strip()


@hook_router.post("/{endpoint_id}", response_model=WebhookResultRead, status_code=202)
async def receive_generic(
    endpoint_id: str, request: Request, session: Session = Depends(get_session)
) -> WebhookResultRead:
    """The generic entry point: any JSON sender, with an optional shared secret."""
    endpoint = get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found")
    if endpoint.kind != "generic":
        raise HTTPException(status_code=404, detail="This is not a generic webhook endpoint")
    if not endpoint.enabled:
        raise HTTPException(status_code=403, detail="This endpoint is disabled")
    _check_generic_secret(request, endpoint.secret)
    raw = await request.body()
    event = await ingest_event(
        session,
        endpoint,
        payload=_payload(raw),
        event_type=_event_type(request, "event"),
        delivery_id=request.headers.get("x-webhook-id") or "",
        headers=_kept_headers(request, ("content-type", "user-agent", "x-event-type", "x-webhook-id")),
    )
    deliveries = session.exec(select(EventDelivery).where(col(EventDelivery.event_id) == event.id)).all()
    return WebhookResultRead(
        id=event.id, event_type=event.event_type, deliveries=_delivery_reads(session, list(deliveries))
    )


@hook_router.post("/github/{endpoint_id}", response_model=WebhookResultRead, status_code=202)
async def receive_github(
    endpoint_id: str, request: Request, session: Session = Depends(get_session)
) -> WebhookResultRead:
    """GitHub's entry point: verify the HMAC signature, then deliver the payload."""
    endpoint = get_or_404(session, WebhookEndpoint, endpoint_id, "Endpoint not found")
    if endpoint.kind != "github":
        raise HTTPException(status_code=404, detail="This is not a GitHub webhook endpoint")
    if not endpoint.enabled:
        raise HTTPException(status_code=403, detail="This endpoint is disabled")
    raw = await request.body()
    _check_github_signature(request, raw, endpoint.secret)
    event = await ingest_event(
        session,
        endpoint,
        payload=_payload(raw),
        event_type=_event_type(request, "unknown"),
        delivery_id=request.headers.get("x-github-delivery") or "",
        headers=_kept_headers(
            request, ("content-type", "user-agent", "x-github-event", "x-github-delivery", "x-github-hook-id")
        ),
    )
    deliveries = session.exec(select(EventDelivery).where(col(EventDelivery.event_id) == event.id)).all()
    return WebhookResultRead(
        id=event.id, event_type=event.event_type, deliveries=_delivery_reads(session, list(deliveries))
    )


def _kept_headers(request: Request, names: tuple[str, ...]) -> dict[str, str]:
    return {name: request.headers[name] for name in names if name in request.headers}


__all__ = ["router", "hook_router"]
