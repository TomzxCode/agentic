"""SQLModel tables for the event bus and its webhook entry points.

A ``WebhookEndpoint`` is a URL a third party posts to (a generic JSON webhook or
a GitHub webhook). Every delivery becomes a ``WebhookEvent`` row, and each
matching ``EventSubscription`` starts the execution graph it points at; the
``EventDelivery`` row records what that event did to that workflow.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from .base import new_id, utcnow


class WebhookEndpoint(SQLModel, table=True):
    """A named inbound webhook URL.

    ``kind`` is ``generic`` for any JSON sender or ``github`` for GitHub's
    webhook format. A secret is an HMAC key on a GitHub endpoint and a shared
    token the sender must present on a generic one.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: str = ""
    kind: str = "generic"
    secret: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EventSubscription(SQLModel, table=True):
    """One workflow wired to one webhook endpoint.

    ``events`` limits the subscription to the named event types (empty matches
    every event), and ``filters`` narrows it further with JSON-path conditions
    such as ``{"path": "action", "equals": "opened"}``.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = ""
    endpoint_id: str = Field(foreign_key="webhookendpoint.id", index=True)
    graph_id: str = Field(foreign_key="executiongraph.id", index=True)
    # The event trigger node this subscription belongs to, when the graph owns
    # it; empty for one wired by hand on the Webhooks page.
    node_id: str = ""
    events: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    filters: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    enabled: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class WebhookEvent(SQLModel, table=True):
    """One inbound delivery, kept so it can be inspected and replayed.

    ``event_type`` is GitHub's event name (``pull_request``, ``push``, ...) or
    the generic sender's own label. ``payload`` is the parsed JSON body, wrapped
    in ``{"body": ...}`` when the body is not a JSON object.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    endpoint_id: str = Field(foreign_key="webhookendpoint.id", index=True)
    source: str = "webhook"
    event_type: str = "event"
    delivery_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    headers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class EventDelivery(SQLModel, table=True):
    """What one event did to one subscription, including the execution it started."""

    id: str = Field(default_factory=new_id, primary_key=True)
    event_id: str = Field(foreign_key="webhookevent.id", index=True)
    subscription_id: str = Field(foreign_key="eventsubscription.id", index=True)
    graph_id: str = Field(foreign_key="executiongraph.id", index=True)
    graph_execution_id: str | None = None
    # started | skipped | failed
    status: str = "started"
    error: str = ""
    created_at: datetime = Field(default_factory=utcnow)
