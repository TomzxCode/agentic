"""Cycle-time metrics derived from GitHub issue and pull request events.

These answer how long work takes, independently of the factory metrics
(autonomy rate and yield) that answer how much of it landed untouched:

- **Issue close** is the time from opening an issue to closing it.
- **Review wait** is the time from the first review request to the first review.
- **Review to merge** is the time from the first review to the merge.

Every function here is pure: it takes records already normalized from GitHub,
plus the reporting window, and returns intervals and their per-bucket medians,
so the arithmetic is deterministic and testable without a network or database.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

ISSUE_CLOSE = "issue_close"
REVIEW_WAIT = "review_wait"
REVIEW_TO_MERGE = "review_to_merge"

#: Order the metrics are presented in, with their display labels.
METRIC_LABELS: dict[str, str] = {
    ISSUE_CLOSE: "Issue close",
    REVIEW_WAIT: "Review request to review",
    REVIEW_TO_MERGE: "Review to merge",
}

#: Every cycle-time metric is a duration in hours.
DEFAULT_BUCKET_DAYS = 7
DEFAULT_WINDOW_DAYS = 90


@dataclass(frozen=True)
class IssueRecord:
    """A closed issue, reduced to the two times the metric needs."""

    number: int
    created_at: datetime
    closed_at: datetime


@dataclass(frozen=True)
class Review:
    """A submitted review."""

    author: str | None
    submitted_at: datetime


@dataclass(frozen=True)
class ReviewRequest:
    """A ``review_requested`` timeline event."""

    reviewer: str | None
    requested_at: datetime


@dataclass(frozen=True)
class PullRecord:
    """A pull request with the events the review metrics need."""

    number: int
    created_at: datetime
    merged_at: datetime | None = None
    reviews: tuple[Review, ...] = ()
    review_requests: tuple[ReviewRequest, ...] = ()


@dataclass(frozen=True)
class Interval:
    """One observation of a cycle time."""

    start: datetime
    end: datetime

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True)
class Bucket:
    """One period of a trend, holding the median of its observations."""

    start: datetime
    end: datetime
    median_hours: float | None
    count: int


@dataclass(frozen=True)
class MetricSeries:
    """A metric's overall median plus its trend."""

    metric: str
    label: str
    median_hours: float | None
    count: int
    buckets: tuple[Bucket, ...]


def issue_close_intervals(issues: Sequence[IssueRecord], since: datetime) -> list[Interval]:
    """Time from opening to closing, for issues closed at or after ``since``."""
    return [Interval(start=issue.created_at, end=issue.closed_at) for issue in issues if issue.closed_at >= since]


def first_review(pull: PullRecord) -> Review | None:
    """The earliest review submitted on a pull request."""
    return min(pull.reviews, key=lambda review: review.submitted_at) if pull.reviews else None


def review_wait_intervals(pulls: Sequence[PullRecord], since: datetime | None = None) -> list[Interval]:
    """Time from a pull request's first review request to its first review.

    A pull request with no explicit review request, or with no review after it,
    is skipped: it has no wait to measure. ``since`` keeps only waits that ended
    in the reporting window.
    """
    intervals: list[Interval] = []
    for pull in pulls:
        if not pull.review_requests:
            continue
        request = min(pull.review_requests, key=lambda event: event.requested_at)
        # A review that predates the request (or a re-request after an earlier
        # round) does not answer it, so take the first review after it.
        review = min(
            (review for review in pull.reviews if review.submitted_at >= request.requested_at),
            key=lambda review: review.submitted_at,
            default=None,
        )
        if review is None:
            continue
        if since is not None and review.submitted_at < since:
            continue
        intervals.append(Interval(start=request.requested_at, end=review.submitted_at))
    return intervals


def review_to_merge_intervals(pulls: Sequence[PullRecord], since: datetime | None = None) -> list[Interval]:
    """Time from a pull request's first review to its merge.

    Only merged pull requests that received a review before the merge count,
    and ``since`` keeps only merges in the reporting window.
    """
    intervals: list[Interval] = []
    for pull in pulls:
        if pull.merged_at is None:
            continue
        if since is not None and pull.merged_at < since:
            continue
        review = first_review(pull)
        if review is None or review.submitted_at > pull.merged_at:
            continue
        intervals.append(Interval(start=review.submitted_at, end=pull.merged_at))
    return intervals


def _median_hours(intervals: Sequence[Interval]) -> float | None:
    return median(interval.hours for interval in intervals) if intervals else None


def bucket_intervals(
    intervals: Sequence[Interval],
    start: datetime,
    end: datetime,
    bucket_days: int = DEFAULT_BUCKET_DAYS,
) -> list[Bucket]:
    """Split intervals into fixed buckets by their end time and take each median.

    Buckets are anchored at ``start`` and cover the window continuously, so an
    empty period still appears in the trend (with no value) rather than being
    dropped and making the series look denser than it is.
    """
    if bucket_days < 1:
        raise ValueError("bucket_days must be at least 1")
    if end <= start:
        return []
    width = timedelta(days=bucket_days)
    buckets: list[Bucket] = []
    bucket_start = start
    while bucket_start < end:
        bucket_end = min(bucket_start + width, end)
        members = [interval for interval in intervals if bucket_start <= interval.end < bucket_end]
        buckets.append(
            Bucket(
                start=bucket_start,
                end=bucket_end,
                median_hours=_median_hours(members),
                count=len(members),
            )
        )
        bucket_start = bucket_end
    return buckets


def build_series(
    metric: str,
    intervals: Sequence[Interval],
    start: datetime,
    end: datetime,
    bucket_days: int = DEFAULT_BUCKET_DAYS,
) -> MetricSeries:
    """Build one metric's overall median and its bucketed trend."""
    return MetricSeries(
        metric=metric,
        label=METRIC_LABELS[metric],
        median_hours=_median_hours(intervals),
        count=len(intervals),
        buckets=tuple(bucket_intervals(intervals, start, end, bucket_days)),
    )


def build_series_for(
    issues: Sequence[IssueRecord],
    pulls: Sequence[PullRecord],
    start: datetime,
    end: datetime,
    bucket_days: int = DEFAULT_BUCKET_DAYS,
) -> list[MetricSeries]:
    """Build all three cycle-time series from one repository's records."""
    return [
        build_series(ISSUE_CLOSE, issue_close_intervals(issues, start), start, end, bucket_days),
        build_series(REVIEW_WAIT, review_wait_intervals(pulls, start), start, end, bucket_days),
        build_series(REVIEW_TO_MERGE, review_to_merge_intervals(pulls, start), start, end, bucket_days),
    ]


__all__ = [
    "DEFAULT_BUCKET_DAYS",
    "DEFAULT_WINDOW_DAYS",
    "ISSUE_CLOSE",
    "METRIC_LABELS",
    "REVIEW_TO_MERGE",
    "REVIEW_WAIT",
    "Bucket",
    "Interval",
    "IssueRecord",
    "MetricSeries",
    "PullRecord",
    "Review",
    "ReviewRequest",
    "bucket_intervals",
    "build_series",
    "build_series_for",
    "first_review",
    "issue_close_intervals",
    "review_to_merge_intervals",
    "review_wait_intervals",
]
