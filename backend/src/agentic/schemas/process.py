"""Pydantic request/response models for the process (production line) report."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StageInventory(BaseModel):
    stage: str
    label: str
    count: int = 0
    oldest_hours: float | None = None
    median_age_hours: float | None = None
    newest_hours: float | None = None


class StageFlow(BaseModel):
    from_stage: str
    to_stage: str
    count: int = 0


class CycleTimeSummary(BaseModel):
    count: int = 0
    mean_hours: float | None = None
    median_hours: float | None = None
    p10_hours: float | None = None
    p90_hours: float | None = None
    fastest_hours: float | None = None
    slowest_hours: float | None = None


class CycleHistogramBucket(BaseModel):
    label: str
    from_hours: float
    to_hours: float | None = None
    count: int = 0


class StageDwell(BaseModel):
    stage: str
    label: str
    count: int = 0
    mean_hours: float | None = None
    median_hours: float | None = None


class FlowWeek(BaseModel):
    start: datetime
    end: datetime
    created: int = 0
    completed: int = 0


class LittlesLaw(BaseModel):
    avg_wip: float | None = None
    throughput_per_day: float | None = None
    projected_cycle_hours: float | None = None


class ProcessReport(BaseModel):
    generated_at: datetime
    window_days: int
    stages: list[StageInventory] = []
    flows: list[StageFlow] = []
    arrivals: int = 0
    completions: int = 0
    cycle_time: CycleTimeSummary = CycleTimeSummary()
    histogram: list[CycleHistogramBucket] = []
    dwell: list[StageDwell] = []
    weekly: list[FlowWeek] = []
    littles: LittlesLaw = LittlesLaw()
