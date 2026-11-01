"""Pydantic request/response models for webhook endpoints and event deliveries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from .base import ORMModel

EndpointKind = Literal["generic", "github"]


class EventFilter(BaseModel):
    """One condition a payload must satisfy, for example action equals opened."""

    path: str
    equals: str | bool | int | float | None = None
    contains: str | None = None
    exists: bool | None = None


class WebhookEndpointCreate(BaseModel):
    name: str
    description: str = ""
    kind: EndpointKind = "generic"
    secret: str = ""
    enabled: bool = True


class WebhookEndpointUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    kind: EndpointKind | None = None
    secret: str | None = None
    enabled: bool | None = None


class WebhookEndpointRead(ORMModel):
    id: str
    name: str
    description: str
    kind: str
    secret: str
    enabled: bool
    subscription_count: int = 0
    event_count: int = 0
    created_at: datetime
    updated_at: datetime


class EventSubscriptionCreate(BaseModel):
    graph_id: str
    name: str = ""
    events: list[str] = []
    filters: list[EventFilter] = []
    enabled: bool = True


class EventSubscriptionUpdate(BaseModel):
    graph_id: str | None = None
    name: str | None = None
    events: list[str] | None = None
    filters: list[EventFilter] | None = None
    enabled: bool | None = None


class EventSubscriptionRead(ORMModel):
    id: str
    endpoint_id: str
    graph_id: str
    graph_name: str = ""
    name: str
    events: list[str]
    filters: list[dict[str, Any]]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class EventDeliveryRead(ORMModel):
    id: str
    event_id: str
    subscription_id: str
    subscription_name: str = ""
    graph_id: str
    graph_name: str = ""
    graph_execution_id: str | None = None
    status: str
    error: str
    created_at: datetime


class WebhookEventRead(ORMModel):
    id: str
    endpoint_id: str
    endpoint_name: str = ""
    source: str
    event_type: str
    delivery_id: str
    payload: dict[str, Any]
    headers: dict[str, str]
    delivery_count: int = 0
    created_at: datetime


class WebhookEventDetailRead(WebhookEventRead):
    deliveries: list[EventDeliveryRead] = []


class WebhookResultRead(BaseModel):
    """What one inbound delivery (or replay) started."""

    id: str
    event_type: str
    deliveries: list[EventDeliveryRead] = []


class WebhookTestSend(BaseModel):
    event_type: str = "test"
    payload: dict[str, Any] = {}
