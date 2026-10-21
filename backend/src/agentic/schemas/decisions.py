"""Request and response models for the colleague-decisions page."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DecisionRead(BaseModel):
    """One decision a colleague made, plus who supported or opposed it."""

    date: str
    author: str
    bucket: str
    text: str
    permalink: str = ""
    supported_by: list[str] = Field(default_factory=list)
    opposed_by: list[str] = Field(default_factory=list)
    source: str = ""


class DecisionsRangeRead(BaseModel):
    """The first and last day the decisions in the payload fall on."""

    start: str
    end: str


class DecisionsCountsRead(BaseModel):
    """How many decisions, people, supporters, and opponents the payload holds."""

    decisions: int = 0
    people: int = 0
    supporters: int = 0
    opponents: int = 0


class DecisionsRead(BaseModel):
    """The Decisions page's payload: the aggregated reports and their context."""

    root: str | None = None
    generated_at: datetime
    reports: int = 0
    counts: DecisionsCountsRead = Field(default_factory=DecisionsCountsRead)
    range: DecisionsRangeRead | None = None
    decisions: list[DecisionRead] = Field(default_factory=list)
    headlines: dict[str, str] = Field(default_factory=dict)
    not_heard: list[str] = Field(default_factory=list)
    cross_cutting: list[str] = Field(default_factory=list)
