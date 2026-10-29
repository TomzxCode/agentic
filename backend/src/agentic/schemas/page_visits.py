"""Pydantic request/response models for page visits."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class VisitCreate(BaseModel):
    """One stretch a page was open and visible, as the browser reports it."""

    path: str = Field(min_length=1, max_length=500)
    route_name: str = Field(default="", max_length=100)
    title: str = Field(default="", max_length=200)
    started_at: datetime
    ended_at: datetime


class VisitBatch(BaseModel):
    """A client's buffered visits, sent together when a page closes or a tab hides."""

    visits: list[VisitCreate] = Field(default_factory=list, max_length=200)


class VisitRead(BaseModel):
    id: str
    path: str
    route_name: str
    title: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    # What the path shows, resolved from the record it points at (a task title,
    # a pull request reference). None when the page is a list or the record is gone.
    detail: str | None = None


class VisitList(BaseModel):
    start: datetime
    end: datetime
    visits: list[VisitRead] = []


class PageTotalRead(BaseModel):
    key: str
    label: str
    duration_ms: int
    visits: int
    share: float = 0


class PlaceRead(PageTotalRead):
    path: str
    detail: str | None = None


class DayTotalRead(BaseModel):
    date: date
    duration_ms: int
    visits: int


class PageTimeReportRead(BaseModel):
    window_days: int
    tz_offset: int
    generated_at: datetime
    start: datetime
    end: datetime
    duration_ms: int
    visits: int
    pages: list[PageTotalRead] = []
    places: list[PlaceRead] = []
    days: list[DayTotalRead] = []
