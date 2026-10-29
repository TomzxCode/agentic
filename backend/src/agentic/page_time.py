"""Page time: where a client's foreground time went, bucketed by page and day.

The web client records one ``PageVisit`` for each stretch a page stays open and
visible, so the sum of the visits is the time the app was in front of the user
rather than the time a tab existed. Every function here is pure, taking the
visits plus a clock, the window, and the client's UTC offset, so the buckets are
deterministic and can be tested without a database.

A day means the client's local day: the browser sends its offset with each
report, because a visit that starts at 23:00 belongs to the day the user saw,
not to the UTC date.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from .models.system import PageVisit

DEFAULT_WINDOW_DAYS = 7
WINDOW_OPTIONS = (1, 7, 30, 90)

# A visit shorter than this is a redirect or a double navigation, not time
# spent; one longer than a day means a client lost track of the tab.
MIN_VISIT_MS = 1_000
MAX_VISIT_MS = 24 * 60 * 60 * 1_000


def as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC, so comparisons never mix aware and naive."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def clamp_visit(started_at: datetime, ended_at: datetime) -> tuple[datetime, datetime, int] | None:
    """The visit's bounds and duration in milliseconds, or None when it is not a visit."""
    start, end = as_utc(started_at), as_utc(ended_at)
    if end < start:
        return None
    duration = int((end - start).total_seconds() * 1_000)
    if duration < MIN_VISIT_MS or duration > MAX_VISIT_MS:
        return None
    return start, end, duration


def local_date(value: datetime, tz_offset_minutes: int) -> date:
    """The client's local date for a UTC instant."""
    return (as_utc(value) + timedelta(minutes=tz_offset_minutes)).date()


def local_day_start(day: date, tz_offset_minutes: int) -> datetime:
    """The UTC instant a client's local day begins."""
    return datetime.combine(day, time.min, tzinfo=UTC) - timedelta(minutes=tz_offset_minutes)


def local_day_bounds(day: date, tz_offset_minutes: int) -> tuple[datetime, datetime]:
    start = local_day_start(day, tz_offset_minutes)
    return start, start + timedelta(days=1)


def window_dates(now: datetime, days: int, tz_offset_minutes: int) -> list[date]:
    """The local dates the window covers, oldest first, ending today."""
    today = local_date(now, tz_offset_minutes)
    span = max(1, days)
    return [today - timedelta(days=offset) for offset in range(span - 1, -1, -1)]


def window_bounds(now: datetime, days: int, tz_offset_minutes: int) -> tuple[datetime, datetime]:
    """The UTC range of the window: whole local days, ending at the start of tomorrow."""
    dates = window_dates(now, days, tz_offset_minutes)
    start = local_day_start(dates[0], tz_offset_minutes)
    end = local_day_start(dates[-1], tz_offset_minutes) + timedelta(days=1)
    return start, end


@dataclass(frozen=True)
class PageTotal:
    """Time on one route, across every path the route served."""

    key: str
    label: str
    duration_ms: int
    visits: int


@dataclass(frozen=True)
class PlaceTotal:
    """Time on one path, such as a single task page."""

    path: str
    key: str
    label: str
    duration_ms: int
    visits: int


@dataclass(frozen=True)
class DayTotal:
    """Time in the app on one local day."""

    day: date
    duration_ms: int
    visits: int


@dataclass
class PageTimeSummary:
    """The window's totals plus the groupings a report renders."""

    start: datetime
    end: datetime
    duration_ms: int = 0
    visits: int = 0
    pages: list[PageTotal] = field(default_factory=list)
    places: list[PlaceTotal] = field(default_factory=list)
    days: list[DayTotal] = field(default_factory=list)


def in_window(visits: Sequence[PageVisit], start: datetime, end: datetime) -> list[PageVisit]:
    """Visits that began inside the window, oldest first."""
    rows = [visit for visit in visits if start <= as_utc(visit.started_at) < end]
    return sorted(rows, key=lambda visit: as_utc(visit.started_at))


def _label(visits: Sequence[PageVisit], fallback: str) -> str:
    """The newest title the route reported, so a renamed page shows its new name."""
    titled = [visit for visit in visits if visit.title]
    if not titled:
        return fallback
    return max(titled, key=lambda visit: as_utc(visit.started_at)).title


def group_pages(visits: Sequence[PageVisit]) -> list[PageTotal]:
    """Total time per route, biggest first."""
    groups: dict[str, list[PageVisit]] = {}
    for visit in visits:
        key = visit.route_name or visit.path
        groups.setdefault(key, []).append(visit)
    totals = [
        PageTotal(
            key=key,
            label=_label(rows, key),
            duration_ms=sum(row.duration_ms for row in rows),
            visits=len(rows),
        )
        for key, rows in groups.items()
    ]
    return sorted(totals, key=lambda total: (-total.duration_ms, total.label.lower()))


def group_places(visits: Sequence[PageVisit]) -> list[PlaceTotal]:
    """Total time per path, biggest first; the caller attaches what each path shows."""
    groups: dict[str, list[PageVisit]] = {}
    for visit in visits:
        groups.setdefault(visit.path, []).append(visit)
    totals = [
        PlaceTotal(
            path=path,
            key=rows[0].route_name or path,
            label=_label(rows, rows[0].route_name or path),
            duration_ms=sum(row.duration_ms for row in rows),
            visits=len(rows),
        )
        for path, rows in groups.items()
    ]
    return sorted(totals, key=lambda total: (-total.duration_ms, total.path))


def daily_totals(visits: Sequence[PageVisit], dates: Sequence[date], tz_offset_minutes: int) -> list[DayTotal]:
    """One entry per day in the window, including days with no visits."""
    buckets: dict[date, list[PageVisit]] = {day: [] for day in dates}
    for visit in visits:
        day = local_date(visit.started_at, tz_offset_minutes)
        if day in buckets:
            buckets[day].append(visit)
    return [
        DayTotal(
            day=day,
            duration_ms=sum(row.duration_ms for row in rows),
            visits=len(rows),
        )
        for day, rows in buckets.items()
    ]


def summarize(visits: Sequence[PageVisit], now: datetime, days: int, tz_offset_minutes: int) -> PageTimeSummary:
    """Everything a report needs, computed from the window's visits."""
    start, end = window_bounds(now, days, tz_offset_minutes)
    rows = in_window(visits, start, end)
    return PageTimeSummary(
        start=start,
        end=end,
        duration_ms=sum(row.duration_ms for row in rows),
        visits=len(rows),
        pages=group_pages(rows),
        places=group_places(rows),
        days=daily_totals(rows, window_dates(now, days, tz_offset_minutes), tz_offset_minutes),
    )
