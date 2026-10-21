"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .base import ORMModel


class MetricCounts(BaseModel):
    accepted: int = 0
    touchless: int = 0
    reverted: int = 0
    rejected: int = 0
    pending_observation: int = 0
    open: int = 0


class MetricResult(BaseModel):
    metric: str
    label: str
    value: float | None = None
    numerator: int = 0
    denominator: int = 0
    baseline: float | None = None
    delta: float | None = None
    direction: str
    unit: str = "ratio"


class MetricsReport(BaseModel):
    window_days: int
    observation_days: int
    tolerance: float
    generated_at: datetime
    metrics: list[MetricResult] = []
    counts: MetricCounts = MetricCounts()


class CycleTimeBucket(BaseModel):
    start: datetime
    end: datetime
    median_hours: float | None = None
    count: int = 0


class CycleTimeSeries(BaseModel):
    metric: str
    label: str
    unit: str = "hours"
    median_hours: float | None = None
    count: int = 0
    buckets: list[CycleTimeBucket] = []


class RepositoryCycleTime(BaseModel):
    repository_id: str
    name: str
    full_name: str | None = None
    error: str | None = None
    series: list[CycleTimeSeries] = []


class CycleTimeReport(BaseModel):
    window_days: int
    bucket_days: int
    generated_at: datetime
    repositories: list[RepositoryCycleTime] = []


class BaselineSet(BaseModel):
    value: float
    window_days: int = 30
    observation_days: int = 14
    note: str = ""
    captured_at: datetime | None = None


class BaselineRead(ORMModel):
    metric: str
    value: float
    window_days: int
    observation_days: int
    note: str
    captured_at: datetime
