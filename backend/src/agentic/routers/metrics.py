"""Factory metrics: autonomy rate and yield, and the baselines they are read against.

The metric engine is pure (see ``metrics.py``); this router loads the change
rows, applies the optional work-scope filters, and turns the computation into a
report with one entry per metric plus the raw counts. Baselines are stored one
per metric so the direction (improving, worsening, flat) means something stable.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..cycle_time import (
    DEFAULT_BUCKET_DAYS,
    IssueRecord,
    PullRecord,
    Review,
    ReviewRequest,
    build_series_for,
)
from ..cycle_time import (
    DEFAULT_WINDOW_DAYS as DEFAULT_CYCLE_TIME_WINDOW_DAYS,
)
from ..db import get_session
from ..metrics import (
    DEFAULT_OBSERVATION_DAYS,
    DEFAULT_TOLERANCE,
    DEFAULT_WINDOW_DAYS,
    compute_metrics,
    direction,
)
from ..models.base import ChangeClass, utcnow
from ..models.changes import Change
from ..models.repositories import Repository
from ..models.system import MetricBaseline
from ..parallel import run_parallel
from ..schemas.metrics import (
    BaselineRead,
    BaselineSet,
    CycleTimeBucket,
    CycleTimeReport,
    CycleTimeSeries,
    MetricCounts,
    MetricResult,
    MetricsReport,
    RepositoryCycleTime,
)
from ..services.github import fetch_github_cycle_time, github_owner_repo

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


def _timestamp(value: object) -> datetime | None:
    """Parse a GitHub ISO timestamp, or None when it is missing or malformed."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed


def _issue_records(rows: list[dict]) -> list[IssueRecord]:
    records = []
    for row in rows:
        created, closed = _timestamp(row.get("created_at")), _timestamp(row.get("closed_at"))
        if created is None or closed is None or row.get("number") is None:
            continue
        records.append(IssueRecord(number=row["number"], created_at=created, closed_at=closed))
    return records


def _pull_records(rows: list[dict]) -> list[PullRecord]:
    records = []
    for row in rows:
        created, merged = _timestamp(row.get("created_at")), _timestamp(row.get("merged_at"))
        if created is None or merged is None or row.get("number") is None:
            continue
        reviews = tuple(
            Review(author=review.get("author"), submitted_at=submitted_at)
            for review in row.get("reviews") or []
            if (submitted_at := _timestamp(review.get("submitted_at"))) is not None
        )
        requests = tuple(
            ReviewRequest(reviewer=event.get("reviewer"), requested_at=requested_at)
            for event in row.get("review_requests") or []
            if (requested_at := _timestamp(event.get("requested_at"))) is not None
        )
        records.append(
            PullRecord(
                number=row["number"], created_at=created, merged_at=merged, reviews=reviews, review_requests=requests
            )
        )
    return records


@router.get("/cycle-time", response_model=CycleTimeReport)
def get_cycle_time(
    days: int = Query(default=DEFAULT_CYCLE_TIME_WINDOW_DAYS, ge=1, le=730),
    bucket_days: int = Query(default=DEFAULT_BUCKET_DAYS, ge=1, le=90),
    repository_id: str | None = None,
    refresh: bool = False,
    session: Session = Depends(get_session),
) -> CycleTimeReport:
    """Cycle-time trends per repository, read from GitHub.

    Without a ``repository_id`` every repository with a GitHub remote is
    included; those reads run a few at a time, so a wide selection costs
    several GitHub round trips.
    """
    now = utcnow()
    start = now - timedelta(days=days)
    query = select(Repository).order_by(col(Repository.name))
    if repository_id:
        repository = session.get(Repository, repository_id)
        if repository is None:
            raise HTTPException(status_code=404, detail=f"Unknown repository: {repository_id}")
        if github_owner_repo(repository.remote_url) is None:
            raise HTTPException(status_code=400, detail=f"Repository has no GitHub remote: {repository.name}")
        repositories = [repository]
    else:
        repositories = list(session.exec(query).all())

    targets = [(repository, github_owner_repo(repository.remote_url)) for repository in repositories]
    targets = [(repository, owner_repo) for repository, owner_repo in targets if owner_repo is not None]
    fetched = run_parallel(
        [
            lambda repository=repository, owner_repo=owner_repo: fetch_github_cycle_time(
                *owner_repo, start, refresh=refresh
            )
            for repository, owner_repo in targets
        ]
    )

    results: list[RepositoryCycleTime] = []
    for (repository, owner_repo), data in zip(targets, fetched, strict=True):
        owner, name = owner_repo
        if data is None:
            results.append(
                RepositoryCycleTime(
                    repository_id=repository.id,
                    name=repository.name,
                    full_name=f"{owner}/{name}",
                    error="GitHub could not be read (check gh auth status and the API rate limit)",
                )
            )
            continue
        series = build_series_for(
            _issue_records(data.get("issues") or []),
            _pull_records(data.get("pulls") or []),
            start,
            now,
            bucket_days,
        )
        results.append(
            RepositoryCycleTime(
                repository_id=repository.id,
                name=repository.name,
                full_name=f"{owner}/{name}",
                series=[
                    CycleTimeSeries(
                        metric=item.metric,
                        label=item.label,
                        median_hours=item.median_hours,
                        count=item.count,
                        buckets=[
                            CycleTimeBucket(
                                start=bucket.start,
                                end=bucket.end,
                                median_hours=bucket.median_hours,
                                count=bucket.count,
                            )
                            for bucket in item.buckets
                        ],
                    )
                    for item in series
                ],
            )
        )

    return CycleTimeReport(
        window_days=days,
        bucket_days=bucket_days,
        generated_at=now,
        repositories=results,
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
