"""Factory metrics: autonomy rate and yield, computed from change records.

These are the two primary metrics from "Metrics for a Software Factory". Every
function here is pure, taking change rows plus a clock and the windows, so the
formulas are deterministic and can be tested without a database:

- **Autonomy rate** is the share of accepted changes that had no human
  intervention.
- **Yield** is the share of accepted changes that survived the observation
  window without being reverted.

Both are "higher is better", and both multiply into the rate of trustworthy
unattended work. A metric with no denominator reports no value rather than zero,
and its direction is read against a stored baseline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import Change, ChangeStatus

DEFAULT_WINDOW_DAYS = 30
DEFAULT_OBSERVATION_DAYS = 14
DEFAULT_TOLERANCE = 0.02

# Metrics for which a lower value is the improvement (none yet). Every metric
# here defaults to higher-is-better, which is true for autonomy rate and yield.
LOWER_IS_BETTER: set[str] = set()

ACCEPTED_STATUSES = (ChangeStatus.accepted, ChangeStatus.reverted)


@dataclass(frozen=True)
class MetricValue:
    """A metric's value plus the counts that produced it."""

    value: float | None
    numerator: int
    denominator: int


@dataclass
class ChangeCounts:
    """Raw counts behind the metrics, so the report is auditable."""

    accepted: int = 0
    touchless: int = 0
    reverted: int = 0
    rejected: int = 0
    pending_observation: int = 0
    open: int = 0


@dataclass
class MetricComputation:
    """The computed metrics plus their shared counts."""

    autonomy_rate: MetricValue
    yield_: MetricValue
    counts: ChangeCounts = field(default_factory=ChangeCounts)


def _accepted_in_window(changes: Sequence[Change], now: datetime, window_days: int) -> list[Change]:
    cutoff = now - timedelta(days=window_days)
    return [
        change
        for change in changes
        if change.accepted_at is not None and change.accepted_at >= cutoff and change.status in ACCEPTED_STATUSES
    ]


def _is_observed(change: Change, now: datetime, observation_days: int) -> bool:
    if change.status == ChangeStatus.reverted:
        return True
    assert change.accepted_at is not None  # guaranteed by _accepted_in_window
    return change.accepted_at <= now - timedelta(days=observation_days)


def compute_autonomy_rate(changes: Sequence[Change], now: datetime, window_days: int) -> MetricValue:
    """Share of accepted changes that had no human intervention."""
    accepted = _accepted_in_window(changes, now, window_days)
    touchless = [change for change in accepted if not change.human_intervened]
    denominator = len(accepted)
    value = len(touchless) / denominator if denominator else None
    return MetricValue(value=value, numerator=len(touchless), denominator=denominator)


def compute_yield(changes: Sequence[Change], now: datetime, window_days: int, observation_days: int) -> MetricValue:
    """Share of observed accepted changes that survived without being reverted."""
    accepted = _accepted_in_window(changes, now, window_days)
    observed = [change for change in accepted if _is_observed(change, now, observation_days)]
    survived = [change for change in observed if change.status == ChangeStatus.accepted]
    denominator = len(observed)
    value = len(survived) / denominator if denominator else None
    return MetricValue(value=value, numerator=len(survived), denominator=denominator)


def compute_counts(changes: Sequence[Change], now: datetime, window_days: int, observation_days: int) -> ChangeCounts:
    accepted = _accepted_in_window(changes, now, window_days)
    cutoff = now - timedelta(days=window_days)
    counts = ChangeCounts(
        accepted=len(accepted),
        touchless=len([change for change in accepted if not change.human_intervened]),
        reverted=len([change for change in accepted if change.status == ChangeStatus.reverted]),
        rejected=len(
            [
                change
                for change in changes
                if change.status == ChangeStatus.rejected
                and change.closed_at is not None
                and change.closed_at >= cutoff
            ]
        ),
        pending_observation=len([change for change in accepted if not _is_observed(change, now, observation_days)]),
        open=len([change for change in changes if change.status in (ChangeStatus.proposed, ChangeStatus.verified)]),
    )
    return counts


def compute_metrics(
    changes: Sequence[Change], now: datetime, window_days: int, observation_days: int
) -> MetricComputation:
    """Compute both metrics and the counts, from one pass over the changes."""
    return MetricComputation(
        autonomy_rate=compute_autonomy_rate(changes, now, window_days),
        yield_=compute_yield(changes, now, window_days, observation_days),
        counts=compute_counts(changes, now, window_days, observation_days),
    )


def direction(
    value: float | None,
    baseline: float | None,
    *,
    metric: str | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> str:
    """Classify a metric against its baseline: improving, worsening, flat, or absent.

    ``no-data`` means the metric has no value; ``no-baseline`` means no baseline
    was recorded. The tolerance is the flat band around the baseline.
    """
    if value is None:
        return "no-data"
    if baseline is None:
        return "no-baseline"
    higher_is_better = metric not in LOWER_IS_BETTER if metric else True
    delta = value - baseline
    if delta > tolerance:
        return "improving" if higher_is_better else "worsening"
    if delta < -tolerance:
        return "worsening" if higher_is_better else "improving"
    return "flat"


__all__ = [
    "DEFAULT_OBSERVATION_DAYS",
    "DEFAULT_TOLERANCE",
    "DEFAULT_WINDOW_DAYS",
    "ChangeCounts",
    "MetricComputation",
    "MetricValue",
    "compute_autonomy_rate",
    "compute_counts",
    "compute_metrics",
    "compute_yield",
    "direction",
]
