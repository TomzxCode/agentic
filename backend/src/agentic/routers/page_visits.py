"""Page visits: the client's own record of where its time went.

The web app records one visit per stretch a page stays open and visible and
posts them here; this router stores them, ignores the ones too short or too long
to be time spent, and reads them back as a window report (per page, per place,
per day) plus the raw visits for one day, which is what the Time page's timeline
draws.

Paths are resolved against the records they point at (a task, a person, a
repository, an item, a pull request), so a place reads as "Fix the login timeout"
rather than as an opaque id. A resolve failure is not an error: a deleted task
still has history, so its path keeps its label and no detail.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from ..db import get_session
from ..models.items import Person, SourceItem
from ..models.repositories import Repository
from ..models.system import PageVisit
from ..models.tasks import Task
from ..page_time import (
    DEFAULT_WINDOW_DAYS,
    as_utc,
    clamp_visit,
    local_date,
    local_day_bounds,
    summarize,
    window_bounds,
)
from ..schemas.page_visits import (
    DayTotalRead,
    PageTimeReportRead,
    PageTotalRead,
    PlaceRead,
    VisitBatch,
    VisitList,
    VisitRead,
)

router = APIRouter(prefix="/api/page-visits", tags=["page-visits"])

MAX_BATCH = 200
PLACE_LIMIT = 20
# A range report returns every visit in it, so one request cannot ask for years.
MAX_RANGE_DAYS = 366

_TASK_PATH = re.compile(r"^/task/([^/?#]+)$")
_PERSON_PATH = re.compile(r"^/person/([^/?#]+)$")
_REPOSITORY_PATH = re.compile(r"^/repositories/([^/?#]+)$")
_ITEM_PATH = re.compile(r"^/items/([^/?#]+)$")
_CODEX_PATH = re.compile(r"^/(?:pr|issue)/([^/?#]+)/([^/?#]+)/([^/?#]+)$")


def _clean(path: str) -> str:
    return path.split("?", 1)[0].split("#", 1)[0]


def _share(duration_ms: int, total_ms: int) -> float:
    return round(duration_ms / total_ms, 4) if total_ms else 0.0


def _place_details(session: Session, paths: Sequence[str]) -> dict[str, str]:
    """Resolve each path to what it shows, in one query per kind of record.

    Paths that name nothing (a list page), a record that is gone, or a page
    outside the known routes resolve to nothing and keep their plain label.
    """
    targets: dict[str, tuple[str, str]] = {}
    details: dict[str, str] = {}
    for path in paths:
        clean = _clean(path)
        codex = _CODEX_PATH.match(clean)
        if codex:
            details[path] = f"{codex.group(1)}/{codex.group(2)}#{codex.group(3)}"
        elif match := _TASK_PATH.match(clean):
            targets[path] = ("task", match.group(1))
        elif match := _PERSON_PATH.match(clean):
            if match.group(1) != "new":
                targets[path] = ("person", match.group(1))
        elif match := _REPOSITORY_PATH.match(clean):
            targets[path] = ("repository", match.group(1))
        elif match := _ITEM_PATH.match(clean):
            targets[path] = ("item", match.group(1))

    lookups: dict[str, dict[str, str]] = {"task": {}, "person": {}, "repository": {}, "item": {}}
    queries = {
        "task": (Task, Task.title),
        "person": (Person, Person.name),
        "repository": (Repository, Repository.name),
        "item": (SourceItem, SourceItem.title),
    }
    for kind, (model, name_column) in queries.items():
        ids = {value for target, value in targets.values() if target == kind}
        if not ids:
            continue
        rows = session.exec(select(col(model.id), name_column).where(col(model.id).in_(ids))).all()
        lookups[kind] = {str(row[0]): str(row[1]) for row in rows if row[1]}

    for path, (kind, value) in targets.items():
        if value in lookups[kind]:
            details[path] = lookups[kind][value]
    return details


@router.post("", status_code=204)
def record_visits(payload: VisitBatch, session: Session = Depends(get_session)) -> None:
    """Store the visits a client reports; short and overlong ones are dropped."""
    rows: list[PageVisit] = []
    for item in payload.visits[:MAX_BATCH]:
        clamped = clamp_visit(item.started_at, item.ended_at)
        if clamped is None:
            continue
        started_at, ended_at, duration_ms = clamped
        rows.append(
            PageVisit(
                path=item.path,
                route_name=item.route_name,
                title=item.title,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )
        )
    if rows:
        session.add_all(rows)
        session.commit()


@router.get("/report", response_model=PageTimeReportRead)
def get_report(
    days: int = Query(default=DEFAULT_WINDOW_DAYS, ge=1, le=365),
    tz_offset: int = Query(default=0, ge=-840, le=840),
    session: Session = Depends(get_session),
) -> PageTimeReportRead:
    """Time per page, per place, and per local day over the window.

    ``tz_offset`` is the client's offset from UTC in minutes (east positive), so
    the day buckets match the calendar the user saw.
    """
    now = datetime.now(UTC)
    start, end = window_bounds(now, days, tz_offset)
    query = (
        select(PageVisit)
        .where(col(PageVisit.started_at) >= start)
        .where(col(PageVisit.started_at) < end)
        .order_by(col(PageVisit.started_at))
    )
    visits = list(session.exec(query).all())
    summary = summarize(visits, now, days, tz_offset)
    places = summary.places[:PLACE_LIMIT]
    details = _place_details(session, [place.path for place in places])

    return PageTimeReportRead(
        window_days=days,
        tz_offset=tz_offset,
        generated_at=now,
        start=summary.start,
        end=summary.end,
        duration_ms=summary.duration_ms,
        visits=summary.visits,
        pages=[
            PageTotalRead(
                key=page.key,
                label=page.label,
                duration_ms=page.duration_ms,
                visits=page.visits,
                share=_share(page.duration_ms, summary.duration_ms),
            )
            for page in summary.pages
        ],
        places=[
            PlaceRead(
                path=place.path,
                key=place.key,
                label=place.label,
                duration_ms=place.duration_ms,
                visits=place.visits,
                share=_share(place.duration_ms, summary.duration_ms),
                detail=details.get(place.path),
            )
            for place in places
        ],
        days=[DayTotalRead(date=day.day, duration_ms=day.duration_ms, visits=day.visits) for day in summary.days],
    )


@router.get("/visits", response_model=VisitList)
def list_visits(
    start: datetime | None = None,
    end: datetime | None = None,
    tz_offset: int = Query(default=0, ge=-840, le=840),
    session: Session = Depends(get_session),
) -> VisitList:
    """Every visit overlapping a time range, oldest first, for the timeline.

    Without ``start`` and ``end`` the range is today's local day. A visit that
    started before the range but was still open inside it is included, because
    the part inside the range is time spent there; the client clips its block to
    the range. ``tz_offset`` is only used for that default day.
    """
    if start is None or end is None:
        range_start, range_end = local_day_bounds(local_date(datetime.now(UTC), tz_offset), tz_offset)
    else:
        range_start, range_end = as_utc(start), as_utc(end)
    if range_end <= range_start:
        raise HTTPException(status_code=400, detail="The end of the range must come after its start")
    if range_end - range_start > timedelta(days=MAX_RANGE_DAYS):
        raise HTTPException(status_code=400, detail=f"A range can cover at most {MAX_RANGE_DAYS} days")

    query = (
        select(PageVisit)
        .where(col(PageVisit.started_at) < range_end)
        .where(col(PageVisit.ended_at) > range_start)
        .order_by(col(PageVisit.started_at))
    )
    visits = list(session.exec(query).all())
    details = _place_details(session, [visit.path for visit in visits])
    return VisitList(
        start=range_start,
        end=range_end,
        visits=[
            VisitRead(
                id=visit.id,
                path=visit.path,
                route_name=visit.route_name,
                title=visit.title,
                started_at=visit.started_at,
                ended_at=visit.ended_at,
                duration_ms=visit.duration_ms,
                detail=details.get(visit.path),
            )
            for visit in visits
        ],
    )


__all__ = ["router"]
