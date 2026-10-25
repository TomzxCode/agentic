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
import random
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

#: Queue-trend verdicts for a station's net flow.
FILLING = "filling"
DRAINING = "draining"
STEADY = "steady"

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
    title: str = ""


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
class StageWaitShare:
    """One station's slice of an average completed trip.

    ``share`` compares the station's total wait across all completed items
    with their total cycle time, so the shares of every station sum to one.
    """

    stage: str
    label: str
    count: int = 0
    mean_hours: float | None = None
    total_hours: float = 0.0
    share: float = 0.0


@dataclass(frozen=True)
class QueuePressure:
    """Whether a station's queue is growing, shrinking, or holding steady.

    A queue that fills over the window marks the constraint: items arrive at
    the station faster than it can pass them on. ``weekly_wip`` samples the
    inventory at each week's end, oldest first, ending at the current count.
    """

    stage: str
    label: str
    count: int = 0
    arrived: int = 0
    departed: int = 0
    net: int = 0
    trend: str = STEADY
    weekly_wip: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class FlowWeek:
    """One week of the window: arrivals and completions."""

    start: datetime
    end: datetime
    created: int = 0
    completed: int = 0


@dataclass(frozen=True)
class FlowSample:
    """One instant's snapshot of the line, for the cumulative flow diagram.

    ``completed`` counts every task that had reached done by ``at`` (including
    archived ones), so it only ever grows; the three station counts are the
    inventory at that instant. Sampled once a day.
    """

    at: datetime
    backlog: int = 0
    in_progress: int = 0
    blocked: int = 0
    completed: int = 0


@dataclass(frozen=True)
class WipItem:
    """One item currently on the line, for the aging work-in-progress list."""

    id: str
    title: str
    stage: str
    entered_at: datetime
    age_hours: float


@dataclass(frozen=True)
class TouchRecord:
    """One focus-stack session: a stretch of time a task was the current task."""

    task_id: str
    started_at: datetime
    ended_at: datetime | None


@dataclass(frozen=True)
class TouchStats:
    """How much of completed items' cycle time was actual work.

    Touch time comes from focus-stack sessions clipped to the trip, so an item
    nobody focused while on the line reads as zero touched, not as missing.
    """

    completions: int = 0
    covered: int = 0
    touch_hours: float = 0.0
    cycle_hours: float = 0.0
    efficiency: float | None = None
    mean_touch_hours: float | None = None


@dataclass(frozen=True)
class Forecast:
    """Monte Carlo projection for clearing the items currently on the line.

    Each simulation draws one week's completions from the observed weekly
    history until the active count is exhausted. ``p50``/``p85`` are the
    quantiles of that distribution, as weeks and as dates.
    """

    items: int = 0
    sims: int = 0
    weeks_observed: int = 0
    p50_weeks: float | None = None
    p85_weeks: float | None = None
    p50_date: datetime | None = None
    p85_date: datetime | None = None


@dataclass(frozen=True)
class Outcomes:
    """Where the window's arrivals stand now: shipped, done, or still on the line."""

    created: int = 0
    done: int = 0
    archived: int = 0
    active: int = 0


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
    wait_shares: list[StageWaitShare] = field(default_factory=list)
    queue_pressure: list[QueuePressure] = field(default_factory=list)
    flow_samples: list[FlowSample] = field(default_factory=list)
    wip_items: list[WipItem] = field(default_factory=list)
    touch: TouchStats = TouchStats()
    forecast: Forecast = Forecast()
    outcomes: Outcomes = Outcomes()


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


def _stage_waits(
    timelines: dict[str, list[tuple[datetime, str]]], completions: Sequence[tuple[TaskRecord, datetime]]
) -> dict[str, list[float]]:
    """Time each completed item spent per station, clamped at its completion.

    The segments of a completed item's timeline cover its whole trip, so the
    sums over stations add up to the item's cycle time.
    """
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
    return waits


def stage_dwell(
    tasks: Sequence[TaskRecord],
    transitions: Sequence[Transition],
    completions: Sequence[tuple[TaskRecord, datetime]],
) -> list[StageDwell]:
    """Where the completed items' cycle time went, per station.

    A station's numbers cover only the items that actually waited there
    (``count`` is how many did), so a median over the blocked station answers
    "when an item got stuck, how long was it stuck".
    """
    timelines = {task.id: stage_timeline(task, transitions) for task, _ in completions}
    waits = _stage_waits(timelines, completions)
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


def stage_wait_shares(
    tasks: Sequence[TaskRecord],
    transitions: Sequence[Transition],
    completions: Sequence[tuple[TaskRecord, datetime]],
) -> list[StageWaitShare]:
    """Each station's share of the completed items' total cycle time.

    This is the bottleneck ranking: the station holding the largest slice of
    an average trip is where the line loses the most time.
    """
    timelines = {task.id: stage_timeline(task, transitions) for task, _ in completions}
    waits = _stage_waits(timelines, completions)
    grand_total = sum(total for samples in waits.values() for total in samples)
    shares: list[StageWaitShare] = []
    for stage in STAGES:
        samples = waits.get(stage, ())
        total = sum(samples)
        shares.append(
            StageWaitShare(
                stage=stage,
                label=STAGE_LABELS[stage],
                count=len(samples),
                mean_hours=fmean(samples) if samples else None,
                total_hours=total,
                share=total / grand_total if grand_total > 0 else 0.0,
            )
        )
    return shares


def week_boundaries(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Consecutive seven-day (last one possibly shorter) spans covering the window."""
    boundaries: list[tuple[datetime, datetime]] = []
    week_start = start
    while week_start < end:
        week_end = min(week_start + timedelta(days=7), end)
        boundaries.append((week_start, week_end))
        week_start = week_end
    return boundaries


def _stage_at(timeline: Sequence[tuple[datetime, str]], at: datetime) -> str | None:
    """The station a timeline puts a task in at ``at``, or None before creation."""
    current: str | None = None
    for entered_at, stage in timeline:
        if entered_at > at:
            break
        current = stage
    return current


def queue_pressure(
    tasks: Sequence[TaskRecord],
    transitions: Sequence[Transition],
    start: datetime,
    end: datetime,
) -> list[QueuePressure]:
    """Net flow and inventory trend for each active station.

    ``arrived`` counts moves into the station in the window (creations count
    as backlog arrivals) and ``departed`` moves out, so ``net`` says whether
    the queue grew. ``trend`` reads the net directly, and ``weekly_wip``
    samples the inventory at each week's end for a sparkline.
    """
    timelines = {task.id: stage_timeline(task, transitions) for task in tasks}
    weeks = week_boundaries(start, end)
    weekly: dict[str, list[int]] = {stage: [] for stage in ACTIVE_STAGES}
    for _, week_end in weeks:
        counts = dict.fromkeys(ACTIVE_STAGES, 0)
        for task in tasks:
            stage = _stage_at(timelines[task.id], week_end)
            if stage in counts:
                counts[stage] += 1
        for stage in ACTIVE_STAGES:
            weekly[stage].append(counts[stage])

    arrived = dict.fromkeys(ACTIVE_STAGES, 0)
    departed = dict.fromkeys(ACTIVE_STAGES, 0)
    for transition in transitions:
        if not (start <= transition.at <= end):
            continue
        if transition.to_stage in arrived:
            arrived[transition.to_stage] += 1
        if transition.from_stage in departed:
            departed[transition.from_stage] += 1
    arrived[BACKLOG] += sum(1 for task in tasks if start <= task.created_at <= end)

    current = {stage: (weekly[stage][-1] if weekly[stage] else 0) for stage in ACTIVE_STAGES}
    pressure: list[QueuePressure] = []
    for stage in ACTIVE_STAGES:
        net = arrived[stage] - departed[stage]
        pressure.append(
            QueuePressure(
                stage=stage,
                label=STAGE_LABELS[stage],
                count=current[stage],
                arrived=arrived[stage],
                departed=departed[stage],
                net=net,
                trend=FILLING if net > 0 else DRAINING if net < 0 else STEADY,
                weekly_wip=weekly[stage],
            )
        )
    return pressure


def flow_samples(
    tasks: Sequence[TaskRecord], transitions: Sequence[Transition], start: datetime, end: datetime
) -> list[FlowSample]:
    """Daily snapshots of every station's inventory plus cumulative completions.

    This is the raw material of the cumulative flow diagram: plotted as stacked
    bands, a widening band is a queue forming, and the top edge is the line's
    total output to date.
    """
    timelines = {task.id: stage_timeline(task, transitions) for task in tasks}
    done_at = {
        task.id: min((entered_at for entered_at, stage in timelines[task.id] if stage == DONE), default=None)
        for task in tasks
    }
    samples: list[FlowSample] = []
    day = start
    while day <= end:
        counts = dict.fromkeys((BACKLOG, IN_PROGRESS, BLOCKED), 0)
        completed = 0
        for task in tasks:
            stage = _stage_at(timelines[task.id], day)
            if stage in counts:
                counts[stage] += 1
            finished = done_at[task.id]
            if finished is not None and finished <= day:
                completed += 1
        samples.append(
            FlowSample(
                at=day,
                backlog=counts[BACKLOG],
                in_progress=counts[IN_PROGRESS],
                blocked=counts[BLOCKED],
                completed=completed,
            )
        )
        day += timedelta(days=1)
    return samples


def wip_items(tasks: Sequence[TaskRecord], transitions: Sequence[Transition], now: datetime) -> list[WipItem]:
    """Everything currently on the line, longest wait first.

    This is the aging report: inventory counts say how many items wait, this
    says which ones, since when, and in which station.
    """
    items: list[WipItem] = []
    for task in tasks:
        if stage_of(task) not in ACTIVE_STAGES:
            continue
        entered_at = stage_timeline(task, transitions)[-1][0]
        items.append(
            WipItem(
                id=task.id,
                title=task.title,
                stage=stage_of(task),
                entered_at=entered_at,
                age_hours=hours_between(entered_at, now),
            )
        )
    return sorted(items, key=lambda item: item.age_hours, reverse=True)


def touch_stats(
    sessions: Sequence[TouchRecord], completions: Sequence[tuple[TaskRecord, datetime]], now: datetime
) -> TouchStats:
    """How much of the completed items' time on the line was actual work.

    A session counts toward a trip when it overlaps the span between creation
    and completion; the rest of the trip was waiting.
    """
    if not completions:
        return TouchStats()
    by_task: dict[str, list[TouchRecord]] = {}
    for record in sessions:
        by_task.setdefault(record.task_id, []).append(record)
    touch_total = 0.0
    cycle_total = 0.0
    covered = 0
    for task, completed_at in completions:
        cycle_total += hours_between(task.created_at, completed_at)
        touched = 0.0
        for record in by_task.get(task.id, ()):
            started = max(record.started_at, task.created_at)
            ended = min(record.ended_at or now, completed_at)
            if ended > started:
                touched += hours_between(started, ended)
        if touched > 0:
            covered += 1
        touch_total += touched
    return TouchStats(
        completions=len(completions),
        covered=covered,
        touch_hours=touch_total,
        cycle_hours=cycle_total,
        efficiency=touch_total / cycle_total if cycle_total > 0 else None,
        mean_touch_hours=touch_total / len(completions),
    )


def forecast_backlog(
    active_count: int, weekly_completions: Sequence[int], now: datetime, sims: int = 500, seed: int = 0
) -> Forecast:
    """Project when the items currently on the line will be finished.

    Each simulation resamples the window's weekly completion counts (with
    replacement) until it has covered ``active_count`` items, then reports the
    P50 and P85 of the simulated durations. A window with no completions at
    all supports no forecast, so the quantiles stay None.
    """
    history = list(weekly_completions)
    forecast = Forecast(items=active_count, sims=sims, weeks_observed=len(history))
    if active_count <= 0:
        return Forecast(
            items=0,
            sims=sims,
            weeks_observed=len(history),
            p50_weeks=0.0,
            p85_weeks=0.0,
            p50_date=now,
            p85_date=now,
        )
    if not history or sum(history) == 0:
        return forecast
    rng = random.Random(seed)
    durations: list[int] = []
    for _ in range(sims):
        remaining = active_count
        weeks = 0
        while remaining > 0 and weeks < 520:
            weeks += 1
            remaining -= history[rng.randrange(len(history))]
        durations.append(weeks)
    median_weeks = quantile(durations, 0.5)
    slow_weeks = quantile(durations, 0.85)
    assert median_weeks is not None and slow_weeks is not None
    p50_weeks = float(median_weeks)
    p85_weeks = float(slow_weeks)
    return Forecast(
        items=active_count,
        sims=sims,
        weeks_observed=len(history),
        p50_weeks=p50_weeks,
        p85_weeks=p85_weeks,
        p50_date=now + timedelta(weeks=p50_weeks),
        p85_date=now + timedelta(weeks=p85_weeks),
    )


def outcomes(tasks: Sequence[TaskRecord], start: datetime, end: datetime) -> Outcomes:
    """Where the window's arrivals stand now, by current disposition."""
    created = done = archived = active = 0
    for task in tasks:
        if not start <= task.created_at <= end:
            continue
        created += 1
        stage = stage_of(task)
        if stage == DONE:
            done += 1
        elif stage == ARCHIVED:
            archived += 1
        else:
            active += 1
    return Outcomes(created=created, done=done, archived=archived, active=active)


def weekly_flow(
    tasks: Sequence[TaskRecord],
    completions: Sequence[tuple[TaskRecord, datetime]],
    start: datetime,
    end: datetime,
) -> list[FlowWeek]:
    """Arrivals and completions per week, anchored at the window start."""
    weeks: list[FlowWeek] = []
    for week_start, week_end in week_boundaries(start, end):
        weeks.append(
            FlowWeek(
                start=week_start,
                end=week_end,
                created=sum(1 for task in tasks if week_start <= task.created_at < week_end),
                completed=sum(1 for _, at in completions if week_start <= at < week_end),
            )
        )
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
    sessions: Sequence[TouchRecord] = (),
) -> ProcessReport:
    """Compute the whole production-line report for the window ending at ``now``."""
    start = now - timedelta(days=window_days)
    known = {task.id for task in tasks}
    transitions = [transition for transition in transitions if transition.task_id in known]
    completions = _completion_transitions(tasks, transitions, start, now)
    distribution = cycle_time_distribution(completions)
    weekly = weekly_flow(tasks, completions, start, now)
    active_count = sum(1 for task in tasks if stage_of(task) in ACTIVE_STAGES)
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
        weekly=weekly,
        littles=littles_law(tasks, transitions, completions, start, now),
        wait_shares=stage_wait_shares(tasks, transitions, completions),
        queue_pressure=queue_pressure(tasks, transitions, start, now),
        flow_samples=flow_samples(tasks, transitions, start, now),
        wip_items=wip_items(tasks, transitions, now),
        touch=touch_stats(sessions, completions, now),
        forecast=forecast_backlog(active_count, [week.completed for week in weekly], now),
        outcomes=outcomes(tasks, start, now),
    )


__all__ = [
    "ACTIVE_STAGES",
    "ARCHIVED",
    "BACKLOG",
    "BLOCKED",
    "DEFAULT_WINDOW_DAYS",
    "DONE",
    "DRAINING",
    "FILLING",
    "HISTOGRAM_BUCKETS",
    "IN_PROGRESS",
    "STAGES",
    "STAGE_LABELS",
    "STATUS_TO_STAGE",
    "STEADY",
    "Distribution",
    "FlowSample",
    "FlowWeek",
    "Forecast",
    "HistogramBucket",
    "LittlesLaw",
    "Outcomes",
    "ProcessReport",
    "QueuePressure",
    "StageDwell",
    "StageFlow",
    "StageStat",
    "StageWaitShare",
    "TaskRecord",
    "TouchRecord",
    "TouchStats",
    "Transition",
    "WipItem",
    "build_report",
    "cycle_time_distribution",
    "flow_samples",
    "forecast_backlog",
    "histogram_for",
    "hours_between",
    "littles_law",
    "outcomes",
    "quantile",
    "queue_pressure",
    "stage_dwell",
    "stage_flows",
    "stage_inventory",
    "stage_of",
    "stage_timeline",
    "stage_wait_shares",
    "summarize_durations",
    "touch_stats",
    "week_boundaries",
    "weekly_flow",
    "wip_items",
]
