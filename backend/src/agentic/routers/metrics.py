"""Factory metrics: autonomy rate and yield, and the baselines they are read against.

The metric engine is pure (see ``metrics.py``); this router loads the change
rows, applies the optional work-scope filters, and turns the computation into a
report with one entry per metric plus the raw counts. Baselines are stored one
per metric so the direction (improving, worsening, flat) means something stable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..db import get_session
from ..metrics import (
    DEFAULT_OBSERVATION_DAYS,
    DEFAULT_TOLERANCE,
    DEFAULT_WINDOW_DAYS,
    compute_metrics,
    direction,
)
from ..models import Change, ChangeClass, MetricBaseline, utcnow
from ..schemas import BaselineRead, BaselineSet, MetricCounts, MetricResult, MetricsReport

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

METRIC_LABELS = {"autonomy_rate": "Autonomy rate", "yield": "Yield"}


def _metric_or_404(metric: str) -> str:
    if metric not in METRIC_LABELS:
        raise HTTPException(status_code=404, detail=f"Unknown metric: {metric}")
    return metric


@router.get("", response_model=MetricsReport)
def get_metrics(
    window_days: int = Query(default=DEFAULT_WINDOW_DAYS, ge=1),
    observation_days: int = Query(default=DEFAULT_OBSERVATION_DAYS, ge=0),
    tolerance: float = Query(default=DEFAULT_TOLERANCE, ge=0),
    task_id: str | None = None,
    change_class: str | None = None,
    session: Session = Depends(get_session),
) -> MetricsReport:
    """Compute autonomy rate and yield over the window, with their counts and directions."""
    query = select(Change)
    if task_id:
        query = query.where(Change.task_id == task_id)
    if change_class:
        try:
            query = query.where(Change.change_class == ChangeClass(change_class))
        except ValueError as exc:
            allowed = ", ".join(member.value for member in ChangeClass)
            raise HTTPException(status_code=400, detail=f"Unknown class: {change_class} (allowed: {allowed})") from exc
    changes = list(session.exec(query).all())
    now = utcnow()
    computed = compute_metrics(changes, now, window_days, observation_days)
    baselines = {baseline.metric: baseline for baseline in session.exec(select(MetricBaseline)).all()}

    results: list[MetricResult] = []
    for metric, value in (("autonomy_rate", computed.autonomy_rate), ("yield", computed.yield_)):
        baseline = baselines.get(metric)
        baseline_value = baseline.value if baseline is not None else None
        delta = value.value - baseline_value if value.value is not None and baseline_value is not None else None
        results.append(
            MetricResult(
                metric=metric,
                label=METRIC_LABELS[metric],
                value=value.value,
                numerator=value.numerator,
                denominator=value.denominator,
                baseline=baseline_value,
                delta=delta,
                direction=direction(value.value, baseline_value, metric=metric, tolerance=tolerance),
            )
        )

    return MetricsReport(
        window_days=window_days,
        observation_days=observation_days,
        tolerance=tolerance,
        generated_at=now,
        metrics=results,
        counts=MetricCounts(**vars(computed.counts)),
    )


@router.get("/baselines", response_model=list[BaselineRead])
def list_baselines(session: Session = Depends(get_session)) -> list[MetricBaseline]:
    return list(session.exec(select(MetricBaseline).order_by(col(MetricBaseline.metric))).all())


@router.put("/baselines/{metric}", response_model=BaselineRead)
def set_baseline(metric: str, payload: BaselineSet, session: Session = Depends(get_session)) -> MetricBaseline:
    """Create or replace a metric's baseline (a value in [0, 1])."""
    _metric_or_404(metric)
    if not 0 <= payload.value <= 1:
        raise HTTPException(status_code=400, detail="A ratio baseline must be between 0 and 1")
    baseline = session.get(MetricBaseline, metric)
    if baseline is None:
        baseline = MetricBaseline(metric=metric, value=payload.value)
    baseline.value = payload.value
    baseline.window_days = payload.window_days
    baseline.observation_days = payload.observation_days
    baseline.note = payload.note
    baseline.captured_at = payload.captured_at or utcnow()
    session.add(baseline)
    session.commit()
    session.refresh(baseline)
    return baseline


@router.delete("/baselines/{metric}", status_code=204)
def delete_baseline(metric: str, session: Session = Depends(get_session)) -> None:
    _metric_or_404(metric)
    session.exec(sa_delete(MetricBaseline).where(col(MetricBaseline.metric) == metric))
    session.commit()


__all__ = ["router", "METRIC_LABELS"]
