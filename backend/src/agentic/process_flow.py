"""The SDLC process read as a production line.

Tasks are work items moving between stations: the backlog is the raw-material
queue, in progress is the work station, blocked is the rework and waiting area,
done is finished goods, and archived goods have shipped.

Like ``metrics.py`` and ``cycle_time.py``, everything here is pure: it takes
tasks and their status transitions (already parsed from the timeline by the
router) plus the reporting window, and returns the manufacturing metrics:

- **Station inventory**: how many items sit in each station now, and how long
  the items currently there have been waiting (queue age).
- **Flows**: how many items moved between stations in the window, plus arrivals
  into the backlog and completions out of it.
- **Cycle time**: for items completed in the window, the time from creation to
  done, summarized as a distribution (percentiles plus a histogram).
- **Station dwell**: where that time went, per station, for completed items.
- **Weekly flow**: arrivals and completions per week.
- **Little's law**: average work in process, throughput, and the cycle time
  the line's queue depth implies.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import fmean, median

BACKLOG = "backlog"
IN_PROGRESS = "in_progress"
BLOCKED = "blocked"
DONE = "done"
ARCHIVED = "archived"

#: The stations of the line, in flow order.
STAGES: tuple[str, ...] = (BACKLOG, IN_PROGRESS, BLOCKED, DONE, ARCHIVED)

STAGE_LABELS: dict[str, str] = {
    BACKLOG: "Backlog",
    IN_PROGRESS: "In progress",
    BLOCKED: "Blocked",
    DONE: "Done",
    ARCHIVED: "Archived",
}

#: Task statuses mapped onto stations. Unknown statuses fall back to the backlog.
STATUS_TO_STAGE: dict[str, str] = {
    "open": BACKLOG,
    "in_progress": IN_PROGRESS,
    "blocked": BLOCKED,
    "done": DONE,
    "archived": ARCHIVED,
}

#: The stations that hold unfinished work, the queues Little's law is about.
ACTIVE_STAGES: tuple[str, ...] = (BACKLOG, IN_PROGRESS, BLOCKED)

DEFAULT_WINDOW_DAYS = 90

#: Cycle-time histogram buckets in hours, open-ended at the top.
HISTOGRAM_BUCKETS: tuple[tuple[str, float, float | None], ...] = (
    ("<1d", 0.0, 24.0),
    ("1-2d", 24.0, 48.0),
    ("2-4d", 48.0, 96.0),
    ("4-7d", 96.0, 168.0),
    ("1-2w", 168.0, 336.0),
    ("2-4w", 336.0, 720.0),
    ("1-2mo", 720.0, 1440.0),
    (">2mo", 1440.0, None),
)


@dataclass(frozen=True)
class TaskRecord:
    """One work item, reduced to what the flow computation needs."""

    id: str
    created_at: datetime
    status: str


@dataclass(frozen=True)
class Transition:
    """One observed status change, already mapped onto stations."""

    task_id: str
    at: datetime
    from_stage: str
    to_stage: str


@dataclass(frozen=True)
class StageStat:
    """One station's inventory: how many items, and how long they have waited."""

    stage: str
    label: str
    count: int = 0
    oldest_hours: float | None = None
    median_age_hours: float | None = None
    newest_hours: float | None = None


@dataclass(frozen=True)
class StageFlow:
    """How many items moved from one station to another in the window."""

    from_stage: str
    to_stage: str
    count: int = 0


@dataclass(frozen=True)
class Distribution:
    """A set of durations summarized as a distribution, in hours."""

    count: int = 0
    mean_hours: float | None = None
    median_hours: float | None = None
    p10_hours: float | None = None
    p90_hours: float | None = None
    fastest_hours: float | None = None
    slowest_hours: float | None = None


@dataclass(frozen=True)
class HistogramBucket:
    """One cycle-time bucket: [from_hours, to_hours), open-ended when ``to`` is None."""

    label: str
    from_hours: float
    to_hours: float | None
    count: int = 0


@dataclass(frozen=True)
class StageDwell:
    """Where completed items' time went, for one station."""

    stage: str
    label: str
    count: int = 0
    mean_hours: float | None = None
    median_hours: float | None = None


@dataclass(frozen=True)
class FlowWeek:
    """One week of the window: arrivals and completions."""

    start: datetime
    end: datetime
    created: int = 0
    completed: int = 0


@dataclass(frozen=True)
class LittlesLaw:
    """Average work in process, throughput, and the implied cycle time."""

    avg_wip: float | None = None
    throughput_per_day: float | None = None
    projected_cycle_hours: float | None = None


@dataclass(frozen=True)
class ProcessReport:
    """The whole production-line report for one window."""

    generated_at: datetime
    window_days: int
    stages: list[StageStat] = field(default_factory=list)
    flows: list[StageFlow] = field(default_factory=list)
    arrivals: int = 0
    completions: int = 0
    cycle_time: Distribution = Distribution()
    histogram: list[HistogramBucket] = field(default_factory=list)
    dwell: list[StageDwell] = field(default_factory=list)
    weekly: list[FlowWeek] = field(default_factory=list)
    littles: LittlesLaw = LittlesLaw()


def hours_between(start: datetime, end: datetime) -> float:
    """Elapsed hours between two instants (never negative)."""
    return max(0.0, (end - start).total_seconds() / 3600)


def quantile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated quantile of a sample, or None when it is empty."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def stage_of(task: TaskRecord) -> str:
    """The station a task sits in now, from its current status."""
    return STATUS_TO_STAGE.get(task.status, BACKLOG)


def stage_timeline(task: TaskRecord, transitions: Sequence[Transition]) -> list[tuple[datetime, str]]:
    """A task's (time, station) pairs from creation to now, oldest first.

    Every task starts in the backlog at creation. A transition only applies
    when the task is in the station it claims to leave, so gaps or overlaps in
    the recorded history cannot corrupt the walk. When the walk ends somewhere
    other than the task's current status (history is missing), the last entry
    is corrected to the current station: the task has been there since its last
    known move.
    """
    timeline: list[tuple[datetime, str]] = [(task.created_at, BACKLOG)]
    for transition in sorted((tr for tr in transitions if tr.task_id == task.id), key=lambda tr: tr.at):
        _, stage = timeline[-1]
        if transition.at > timeline[-1][0] and transition.from_stage == stage:
            timeline.append((transition.at, transition.to_stage))
    current = stage_of(task)
    if timeline[-1][1] != current:
        timeline[-1] = (timeline[-1][0], current)
    return timeline


def summarize_durations(durations: Sequence[float]) -> Distribution:
    """Reduce a sample of durations (hours) to its distribution summary."""
    if not durations:
        return Distribution()
    return Distribution(
        count=len(durations),
        mean_hours=fmean(durations),
        median_hours=median(durations),
        p10_hours=quantile(durations, 0.10),
        p90_hours=quantile(durations, 0.90),
        fastest_hours=min(durations),
        slowest_hours=max(durations),
    )


def histogram_for(durations: Sequence[float]) -> list[HistogramBucket]:
    """Count a sample of durations (hours) into the fixed histogram buckets."""
    counts = [0] * len(HISTOGRAM_BUCKETS)
    for value in durations:
        for index, (_, low, high) in enumerate(HISTOGRAM_BUCKETS):
            if value >= low and (high is None or value < high):
                counts[index] += 1
                break
    return [
        HistogramBucket(label=label, from_hours=low, to_hours=high, count=counts[index])
        for index, (label, low, high) in enumerate(HISTOGRAM_BUCKETS)
    ]


def stage_inventory(tasks: Sequence[TaskRecord], transitions: Sequence[Transition], now: datetime) -> list[StageStat]:
    """Per-station counts and the waiting time of the items currently there."""
    timelines = {task.id: stage_timeline(task, transitions) for task in tasks}
    stats: list[StageStat] = []
    for stage in STAGES:
        members = [task for task in tasks if stage_of(task) == stage]
        ages = [hours_between(timelines[task.id][-1][0], now) for task in members]
        stats.append(
            StageStat(
                stage=stage,
                label=STAGE_LABELS[stage],
                count=len(members),
                oldest_hours=max(ages, default=None),
                median_age_hours=median(ages) if ages else None,
                newest_hours=min(ages, default=None),
            )
        )
    return stats


def stage_flows(transitions: Sequence[Transition], start: datetime, end: datetime) -> list[StageFlow]:
    """Transition counts per station pair, for moves inside the window."""
    counts: dict[tuple[str, str], int] = {}
    for transition in transitions:
        if start <= transition.at <= end:
            key = (transition.from_stage, transition.to_stage)
            counts[key] = counts.get(key, 0) + 1
    return [
        StageFlow(from_stage=from_stage, to_stage=to_stage, count=count)
        for (from_stage, to_stage), count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _completion_transitions(
    tasks: Sequence[TaskRecord], transitions: Sequence[Transition], start: datetime, end: datetime
) -> list[tuple[TaskRecord, datetime]]:
    """Tasks that reached done inside the window, with the moment they did."""
    by_id = {task.id: task for task in tasks}
    completions: list[tuple[TaskRecord, datetime]] = []
    for transition in transitions:
        if transition.to_stage != DONE or not (start <= transition.at <= end):
            continue
        task = by_id.get(transition.task_id)
        if task is not None:
            completions.append((task, transition.at))
    return sorted(completions, key=lambda pair: pair[1])


def cycle_time_distribution(
    completions: Sequence[tuple[TaskRecord, datetime]],
) -> Distribution:
    """Time from creation to done, for the window's completions."""
    return summarize_durations([hours_between(task.created_at, at) for task, at in completions])


def stage_dwell(
    tasks: Sequence[TaskRecord],
    transitions: Sequence[Transition],
    completions: Sequence[tuple[TaskRecord, datetime]],
) -> list[StageDwell]:
    """Where the completed items' cycle time went, per station.

    For each completed item, its time in each station is accumulated up to the
    completion moment. A station's numbers cover only the items that actually
    waited there (``count`` is how many did), so a median over the blocked
    station answers "when an item got stuck, how long was it stuck".
    """
    timelines = {task.id: stage_timeline(task, transitions) for task, _ in completions}
    waits: dict[str, list[float]] = {}
    for task, completed_at in completions:
        timeline = timelines[task.id]
        for index, (entered_at, stage) in enumerate(timeline):
            left_at = timeline[index + 1][0] if index + 1 < len(timeline) else completed_at
            if left_at > completed_at:
                left_at = completed_at
            if left_at <= entered_at:
                continue
            waits.setdefault(stage, []).append(hours_between(entered_at, left_at))
    return [
        StageDwell(
            stage=stage,
            label=STAGE_LABELS[stage],
            count=len(waits.get(stage, ())),
            mean_hours=fmean(waits[stage]) if waits.get(stage) else None,
            median_hours=median(waits[stage]) if waits.get(stage) else None,
        )
        for stage in STAGES
    ]


def weekly_flow(
    tasks: Sequence[TaskRecord],
    completions: Sequence[tuple[TaskRecord, datetime]],
    start: datetime,
    end: datetime,
) -> list[FlowWeek]:
    """Arrivals and completions per week, anchored at the window start."""
    weeks: list[FlowWeek] = []
    week_start = start
    while week_start < end:
        week_end = min(week_start + timedelta(days=7), end)
        weeks.append(
            FlowWeek(
                start=week_start,
                end=week_end,
                created=sum(1 for task in tasks if week_start <= task.created_at < week_end),
                completed=sum(1 for _, at in completions if week_start <= at < week_end),
            )
        )
        week_start = week_end
    return weeks


def littles_law(
    tasks: Sequence[TaskRecord],
    transitions: Sequence[Transition],
    completions: Sequence[tuple[TaskRecord, datetime]],
    start: datetime,
    end: datetime,
) -> LittlesLaw:
    """Average work in process, throughput, and the cycle time they imply.

    Average WIP is the exact time integral: for every task, the time it spent
    in the active stations inside the window, summed and divided by the window
    length. Throughput is completions per day. Little's law then says the line
    should take ``avg_wip / throughput`` to finish an item; comparing that with
    the observed median shows whether the queue, not the work, is the delay.
    """
    window_hours = hours_between(start, end)
    if window_hours <= 0:
        return LittlesLaw()
    total_active_hours = 0.0
    for task in tasks:
        timeline = stage_timeline(task, transitions)
        for index, (entered_at, stage) in enumerate(timeline):
            left_at = timeline[index + 1][0] if index + 1 < len(timeline) else end
            overlap_start = max(entered_at, start)
            overlap_end = min(left_at, end)
            if stage in ACTIVE_STAGES and overlap_end > overlap_start:
                total_active_hours += hours_between(overlap_start, overlap_end)
    avg_wip = total_active_hours / window_hours
    window_days = window_hours / 24
    throughput_per_day = len(completions) / window_days
    projected = (avg_wip / throughput_per_day) * 24 if throughput_per_day > 0 else None
    return LittlesLaw(avg_wip=avg_wip, throughput_per_day=throughput_per_day, projected_cycle_hours=projected)


def build_report(
    tasks: Sequence[TaskRecord],
    transitions: Sequence[Transition],
    now: datetime,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> ProcessReport:
    """Compute the whole production-line report for the window ending at ``now``."""
    start = now - timedelta(days=window_days)
    known = {task.id for task in tasks}
    transitions = [transition for transition in transitions if transition.task_id in known]
    completions = _completion_transitions(tasks, transitions, start, now)
    distribution = cycle_time_distribution(completions)
    return ProcessReport(
        generated_at=now,
        window_days=window_days,
        stages=stage_inventory(tasks, transitions, now),
        flows=stage_flows(transitions, start, now),
        arrivals=sum(1 for task in tasks if start <= task.created_at <= now),
        completions=len(completions),
        cycle_time=distribution,
        histogram=histogram_for([hours_between(task.created_at, at) for task, at in completions]),
        dwell=stage_dwell(tasks, transitions, completions),
        weekly=weekly_flow(tasks, completions, start, now),
        littles=littles_law(tasks, transitions, completions, start, now),
    )


__all__ = [
    "ACTIVE_STAGES",
    "ARCHIVED",
    "BACKLOG",
    "BLOCKED",
    "DEFAULT_WINDOW_DAYS",
    "DONE",
    "HISTOGRAM_BUCKETS",
    "IN_PROGRESS",
    "STAGES",
    "STAGE_LABELS",
    "STATUS_TO_STAGE",
    "Distribution",
    "FlowWeek",
    "HistogramBucket",
    "LittlesLaw",
    "ProcessReport",
    "StageDwell",
    "StageFlow",
    "StageStat",
    "TaskRecord",
    "Transition",
    "build_report",
    "cycle_time_distribution",
    "histogram_for",
    "hours_between",
    "littles_law",
    "quantile",
    "stage_dwell",
    "stage_flows",
    "stage_inventory",
    "stage_of",
    "stage_timeline",
    "summarize_durations",
    "weekly_flow",
]
