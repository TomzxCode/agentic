"""SQLModel tables for system."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from .base import (
    OperationActor,
    OperationClient,
    new_id,
    utcnow,
)


class Setting(SQLModel, table=True):
    """Key/value app settings that override environment defaults."""

    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: datetime = Field(default_factory=utcnow)


class Operation(SQLModel, table=True):
    """One mutating request, kept as an audit log of how work entered the system.

    Records the method and path, the resulting status, which client sent it, and
    whether a person or a coding agent was behind it. This is the cross-cutting
    counterpart to a task's timeline: it covers operations with no task to hang a
    ``TimelineEvent`` off, such as settings, repositories, and harnesses.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    method: str = ""
    path: str = ""
    status_code: int = 0
    client: OperationClient = Field(default=OperationClient.api, index=True)
    actor: OperationActor = Field(default=OperationActor.human, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class PageVisit(SQLModel, table=True):
    """One stretch of time a page stayed open and visible in the web app.

    The client records these itself: navigation ends one visit and starts the
    next, and a tab that goes to the background closes its visit, so time the
    app spent behind another window is not counted. ``route_name`` is the
    grouping key (``task``, ``inbox``) and ``path`` is the exact page (one task,
    one pull request), which is what the Time page drills into.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    path: str = Field(index=True)
    route_name: str = Field(default="", index=True)
    title: str = ""
    started_at: datetime = Field(default_factory=utcnow, index=True)
    ended_at: datetime = Field(default_factory=utcnow)
    duration_ms: int = 0


class MetricBaseline(SQLModel, table=True):
    """The comparison point a metric's direction is measured against.

    One row per metric; the article's advice to write the baseline down before
    the first factory run only means something if the value is stored.
    """

    metric: str = Field(primary_key=True)
    value: float
    window_days: int = 30
    observation_days: int = 14
    note: str = ""
    captured_at: datetime = Field(default_factory=utcnow)
