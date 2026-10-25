"""The production-line view of the SDLC process: queues, flow, and cycle times.

The router loads tasks and the status transitions recorded in their timelines
(``updated`` events carry a ``changes.status`` before/after pair), maps statuses
onto stations, and hands everything to the pure ``process_flow`` module.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, select

from .. import process_flow
from ..db import get_session
from ..models.base import utcnow
from ..models.tasks import StackEntry, Task, TaskSession, TimelineEvent
from ..schemas.process import (
    CycleHistogramBucket,
    CycleTimeSummary,
    FlowSample,
    FlowWeek,
    Forecast,
    LittlesLaw,
    Outcomes,
    ProcessReport,
    QueuePressure,
    StageDwell,
    StageFlow,
    StageInventory,
    StageWaitShare,
    TouchStats,
    WipItem,
)

router = APIRouter(prefix="/api/process", tags=["process"])


def _transitions_from_timeline(session: Session) -> list[process_flow.Transition]:
    """Every recorded status change, mapped onto stations.

    An ``updated`` timeline event lists the field diffs it applied under
    ``changes``; the status entry is ``{"from": "open", "to": "in_progress"}``.
    Events whose diff is missing, unparseable, or not a real station move are
    skipped rather than guessed at.
    """
    transitions: list[process_flow.Transition] = []
    events = session.exec(select(TimelineEvent).where(col(TimelineEvent.type) == "updated")).all()
    for event in events:
        changes = (event.data_json or {}).get("changes")
        status_change = changes.get("status") if isinstance(changes, dict) else None
        if not isinstance(status_change, dict):
            continue
        from_stage = process_flow.STATUS_TO_STAGE.get(str(status_change.get("from")))
        to_stage = process_flow.STATUS_TO_STAGE.get(str(status_change.get("to")))
        if from_stage is None or to_stage is None or from_stage == to_stage:
            continue
        transitions.append(
            process_flow.Transition(
                task_id=event.task_id, at=event.created_at, from_stage=from_stage, to_stage=to_stage
            )
        )
    return transitions


def _touch_records(session: Session) -> list[process_flow.TouchRecord]:
    """Every focus-stack session, attached back to its task.

    Sessions hang off stack entries, so the entry id is resolved through the
    entry table; a session whose entry is gone is skipped.
    """
    task_of_entry = {entry.id: entry.task_id for entry in session.exec(select(StackEntry)).all()}
    records: list[process_flow.TouchRecord] = []
    for row in session.exec(select(TaskSession)).all():
        task_id = task_of_entry.get(row.stack_entry_id)
        if task_id is not None:
            records.append(process_flow.TouchRecord(task_id=task_id, started_at=row.started_at, ended_at=row.ended_at))
    return records


@router.get("", response_model=ProcessReport)
def get_process(
    days: int = Query(default=process_flow.DEFAULT_WINDOW_DAYS, ge=1, le=730),
    session: Session = Depends(get_session),
) -> ProcessReport:
    """The production-line report: station inventory, flows, and cycle times."""
    now = utcnow()
    tasks = [
        process_flow.TaskRecord(id=task.id, created_at=task.created_at, status=str(task.status), title=task.title)
        for task in session.exec(select(Task)).all()
    ]
    sessions = _touch_records(session)
    report = process_flow.build_report(
        tasks, _transitions_from_timeline(session), now, window_days=days, sessions=sessions
    )
    return ProcessReport(
        generated_at=report.generated_at,
        window_days=report.window_days,
        stages=[
            StageInventory(
                stage=stage.stage,
                label=stage.label,
                count=stage.count,
                oldest_hours=stage.oldest_hours,
                median_age_hours=stage.median_age_hours,
                newest_hours=stage.newest_hours,
            )
            for stage in report.stages
        ],
        flows=[
            StageFlow(from_stage=flow.from_stage, to_stage=flow.to_stage, count=flow.count) for flow in report.flows
        ],
        arrivals=report.arrivals,
        completions=report.completions,
        cycle_time=CycleTimeSummary(
            count=report.cycle_time.count,
            mean_hours=report.cycle_time.mean_hours,
            median_hours=report.cycle_time.median_hours,
            p10_hours=report.cycle_time.p10_hours,
            p90_hours=report.cycle_time.p90_hours,
            fastest_hours=report.cycle_time.fastest_hours,
            slowest_hours=report.cycle_time.slowest_hours,
        ),
        histogram=[
            CycleHistogramBucket(
                label=bucket.label, from_hours=bucket.from_hours, to_hours=bucket.to_hours, count=bucket.count
            )
            for bucket in report.histogram
        ],
        dwell=[
            StageDwell(
                stage=dwell.stage,
                label=dwell.label,
                count=dwell.count,
                mean_hours=dwell.mean_hours,
                median_hours=dwell.median_hours,
            )
            for dwell in report.dwell
        ],
        weekly=[
            FlowWeek(start=week.start, end=week.end, created=week.created, completed=week.completed)
            for week in report.weekly
        ],
        littles=LittlesLaw(
            avg_wip=report.littles.avg_wip,
            throughput_per_day=report.littles.throughput_per_day,
            projected_cycle_hours=report.littles.projected_cycle_hours,
        ),
        wait_shares=[
            StageWaitShare(
                stage=share.stage,
                label=share.label,
                count=share.count,
                mean_hours=share.mean_hours,
                total_hours=share.total_hours,
                share=share.share,
            )
            for share in report.wait_shares
        ],
        queue_pressure=[
            QueuePressure(
                stage=pressure.stage,
                label=pressure.label,
                count=pressure.count,
                arrived=pressure.arrived,
                departed=pressure.departed,
                net=pressure.net,
                trend=pressure.trend,
                weekly_wip=pressure.weekly_wip,
            )
            for pressure in report.queue_pressure
        ],
        flow_samples=[
            FlowSample(
                at=sample.at,
                backlog=sample.backlog,
                in_progress=sample.in_progress,
                blocked=sample.blocked,
                completed=sample.completed,
            )
            for sample in report.flow_samples
        ],
        wip_items=[
            WipItem(
                id=item.id,
                title=item.title,
                stage=item.stage,
                entered_at=item.entered_at,
                age_hours=item.age_hours,
            )
            for item in report.wip_items
        ],
        touch=TouchStats(
            completions=report.touch.completions,
            covered=report.touch.covered,
            touch_hours=report.touch.touch_hours,
            cycle_hours=report.touch.cycle_hours,
            efficiency=report.touch.efficiency,
            mean_touch_hours=report.touch.mean_touch_hours,
        ),
        forecast=Forecast(
            items=report.forecast.items,
            sims=report.forecast.sims,
            weeks_observed=report.forecast.weeks_observed,
            p50_weeks=report.forecast.p50_weeks,
            p85_weeks=report.forecast.p85_weeks,
            p50_date=report.forecast.p50_date,
            p85_date=report.forecast.p85_date,
        ),
        outcomes=Outcomes(
            created=report.outcomes.created,
            done=report.outcomes.done,
            archived=report.outcomes.archived,
            active=report.outcomes.active,
        ),
    )


__all__ = ["router"]
