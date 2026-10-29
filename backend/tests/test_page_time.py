"""The page-time bucketing, without a database."""

from datetime import UTC, date, datetime, timedelta

from agentic.models.system import PageVisit
from agentic.page_time import (
    clamp_visit,
    daily_totals,
    group_pages,
    group_places,
    local_date,
    local_day_bounds,
    summarize,
    window_bounds,
    window_dates,
)


def visit(path: str, route: str, title: str, start: datetime, minutes: float) -> PageVisit:
    return PageVisit(
        path=path,
        route_name=route,
        title=title,
        started_at=start,
        ended_at=start + timedelta(minutes=minutes),
        duration_ms=int(minutes * 60_000),
    )


def test_clamp_visit_drops_flashes_and_runaway_spans():
    start = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    assert clamp_visit(start, start + timedelta(milliseconds=200)) is None
    assert clamp_visit(start, start + timedelta(hours=25)) is None
    assert clamp_visit(start, start - timedelta(minutes=1)) is None

    clamped = clamp_visit(start, start + timedelta(minutes=2))
    assert clamped is not None
    assert clamped[2] == 120_000


def test_clamp_visit_treats_a_naive_time_as_utc():
    start = datetime(2026, 10, 29, 12, 0)
    clamped = clamp_visit(start, start + timedelta(minutes=1))
    assert clamped is not None
    assert clamped[0] == datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def test_a_negative_offset_moves_the_window_to_the_local_day():
    now = datetime(2026, 10, 29, 3, 0, tzinfo=UTC)  # 22:00 the previous day in UTC-5
    assert local_date(now, -300) == date(2026, 10, 28)
    start, end = window_bounds(now, 7, -300)
    assert start == datetime(2026, 10, 22, 5, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 29, 5, 0, tzinfo=UTC)
    assert window_dates(now, 7, -300)[-1] == date(2026, 10, 28)


def test_local_day_bounds_are_the_inverse_of_the_offset():
    start, end = local_day_bounds(date(2026, 10, 6), 120)
    assert start == datetime(2026, 10, 5, 22, 0, tzinfo=UTC)
    assert end - start == timedelta(days=1)


def test_group_pages_sums_by_route_and_keeps_the_newest_title():
    noon = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    rows = [
        visit("/task/a", "task", "Old task label", noon, 10),
        visit("/task/b", "task", "Task", noon + timedelta(minutes=20), 5),
        visit("/", "tasks", "Tasks", noon + timedelta(minutes=30), 12),
        visit("/", "tasks", "Tasks", noon + timedelta(minutes=45), 8),
    ]

    pages = group_pages(rows)
    assert [(page.key, page.duration_ms, page.visits) for page in pages] == [
        ("tasks", 1_200_000, 2),
        ("task", 900_000, 2),
    ]
    assert pages[1].label == "Task"


def test_group_places_sums_each_path():
    noon = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    rows = [
        visit("/task/a", "task", "Task", noon, 10),
        visit("/task/a", "task", "Task", noon + timedelta(hours=1), 5),
        visit("/task/b", "task", "Task", noon + timedelta(hours=2), 3),
    ]

    places = group_places(rows)
    assert [(place.path, place.duration_ms) for place in places] == [
        ("/task/a", 900_000),
        ("/task/b", 180_000),
    ]


def test_daily_totals_cover_every_day_and_use_the_local_date():
    # 23:30 UTC on the 5th is 01:30 on the 6th at UTC+2.
    late = datetime(2026, 10, 5, 23, 30, tzinfo=UTC)
    rows = [visit("/inbox", "inbox", "Inbox", late, 20)]
    dates = [date(2026, 10, 5), date(2026, 10, 6)]

    assert [day.duration_ms for day in daily_totals(rows, dates, 120)] == [0, 1_200_000]
    assert [day.duration_ms for day in daily_totals(rows, dates, 0)] == [1_200_000, 0]


def test_summarize_reads_only_the_window_and_totals_its_parts():
    now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    rows = [
        visit("/", "tasks", "Tasks", now - timedelta(days=1), 30),
        visit("/inbox", "inbox", "Inbox", now - timedelta(days=2), 10),
        visit("/", "tasks", "Tasks", now - timedelta(days=30), 60),
    ]

    summary = summarize(rows, now, 7, 0)
    assert summary.visits == 2
    assert summary.duration_ms == 2_400_000
    assert [page.key for page in summary.pages] == ["tasks", "inbox"]
    assert [day.duration_ms for day in summary.days] == [0, 0, 0, 0, 600_000, 1_800_000, 0]
