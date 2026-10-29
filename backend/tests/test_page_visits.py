"""Recording page visits and reading the time report back."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session

from agentic.db import engine
from agentic.main import app
from agentic.models.system import PageVisit


def clear_visits() -> None:
    with Session(engine) as session:
        session.exec(sa_delete(PageVisit))
        session.commit()


def span(start: datetime, minutes: float, **overrides) -> dict:
    return {
        "path": "/",
        "route_name": "tasks",
        "title": "Tasks",
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(minutes=minutes)).isoformat(),
        **overrides,
    }


def test_record_and_report_group_time_by_page_and_place():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        clear_visits()
        task = client.post("/api/tasks", json={"title": "Time report task"}).json()
        visits = [
            span(now - timedelta(minutes=40), 12),
            span(now - timedelta(minutes=28), 25, path=f"/task/{task['id']}", route_name="task", title="Task"),
            span(now - timedelta(minutes=3), 3, path="/inbox", route_name="inbox", title="Inbox"),
        ]

        assert client.post("/api/page-visits", json={"visits": visits}).status_code == 204

        report = client.get("/api/page-visits/report", params={"days": 7}).json()
        assert report["visits"] == 3
        assert report["duration_ms"] == 40 * 60_000
        assert [(page["key"], page["duration_ms"]) for page in report["pages"]] == [
            ("task", 25 * 60_000),
            ("tasks", 12 * 60_000),
            ("inbox", 3 * 60_000),
        ]
        assert report["pages"][1]["label"] == "Tasks"
        assert report["places"][0]["path"] == f"/task/{task['id']}"
        assert report["places"][0]["detail"] == "Time report task"
        # Whole local days are returned, including the empty ones, and they add up.
        assert len(report["days"]) == 7
        assert sum(day["duration_ms"] for day in report["days"]) == report["duration_ms"]

        client.delete(f"/api/tasks/{task['id']}")


def test_short_and_overlong_visits_are_not_recorded():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        clear_visits()
        visits = [
            span(now, 0.003),
            {
                "path": "/",
                "route_name": "tasks",
                "title": "Tasks",
                "started_at": (now - timedelta(hours=25)).isoformat(),
                "ended_at": now.isoformat(),
            },
        ]

        assert client.post("/api/page-visits", json={"visits": visits}).status_code == 204
        report = client.get("/api/page-visits/report", params={"days": 7}).json()
        assert report["visits"] == 0
        assert report["duration_ms"] == 0
        assert report["pages"] == []


def test_report_leaves_out_visits_before_the_window():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        clear_visits()
        old = span(now - timedelta(days=40), 30)
        assert client.post("/api/page-visits", json={"visits": [old]}).status_code == 204

        assert client.get("/api/page-visits/report", params={"days": 7}).json()["visits"] == 0
        assert client.get("/api/page-visits/report", params={"days": 90}).json()["visits"] == 1


def test_a_pull_request_path_reads_as_its_reference():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        clear_visits()
        visit = span(
            now - timedelta(minutes=10),
            5,
            path="/pr/acme/api/42",
            route_name="pr",
            title="Pull request",
        )
        assert client.post("/api/page-visits", json={"visits": [visit]}).status_code == 204

        places = client.get("/api/page-visits/report", params={"days": 1}).json()["places"]
        assert places[0]["detail"] == "acme/api#42"


def test_a_deleted_task_keeps_its_history_without_a_detail():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        clear_visits()
        task = client.post("/api/tasks", json={"title": "Deleted task"}).json()
        visit = span(
            now - timedelta(minutes=10),
            5,
            path=f"/task/{task['id']}",
            route_name="task",
            title="Task",
        )
        client.post("/api/page-visits", json={"visits": [visit]})
        client.delete(f"/api/tasks/{task['id']}")

        places = client.get("/api/page-visits/report", params={"days": 1}).json()["places"]
        assert places[0]["path"] == f"/task/{task['id']}"
        assert places[0]["detail"] is None


def test_the_day_of_visits_follows_the_client_offset():
    # 23:30 UTC on the 5th is 01:30 on the 6th at UTC+2, so the same visit
    # belongs to a different local day when the client sits east of UTC.
    late = datetime(2026, 10, 5, 23, 30, tzinfo=UTC)
    with TestClient(app) as client:
        clear_visits()
        client.post("/api/page-visits", json={"visits": [span(late, 10, path="/inbox", route_name="inbox")]})

        west = client.get(
            "/api/page-visits/visits",
            params={"start": "2026-10-05T00:00:00Z", "end": "2026-10-06T00:00:00Z"},
        ).json()
        assert [row["path"] for row in west["visits"]] == ["/inbox"]
        assert west["start"] == "2026-10-05T00:00:00Z"

        next_day = client.get(
            "/api/page-visits/visits",
            params={"start": "2026-10-06T00:00:00Z", "end": "2026-10-07T00:00:00Z"},
        ).json()
        assert next_day["visits"] == []

        # At UTC+2 the visit falls on the 6th, whose local day starts at 22:00 UTC on the 5th.
        east = client.get(
            "/api/page-visits/visits",
            params={"start": "2026-10-05T22:00:00Z", "end": "2026-10-06T22:00:00Z"},
        ).json()
        assert [row["route_name"] for row in east["visits"]] == ["inbox"]


def test_a_visit_that_started_before_the_range_still_overlaps_it():
    start = datetime(2026, 10, 5, 23, 40, tzinfo=UTC)
    with TestClient(app) as client:
        clear_visits()
        client.post("/api/page-visits", json={"visits": [span(start, 40, path="/inbox", route_name="inbox")]})

        # 23:40 to 00:20; the 20 minutes after midnight are inside this range.
        rows = client.get(
            "/api/page-visits/visits",
            params={"start": "2026-10-06T00:00:00Z", "end": "2026-10-06T01:00:00Z"},
        ).json()["visits"]
        assert [row["path"] for row in rows] == ["/inbox"]


def test_an_invalid_range_is_refused():
    with TestClient(app) as client:
        backwards = client.get(
            "/api/page-visits/visits",
            params={"start": "2026-10-06T00:00:00Z", "end": "2026-10-05T00:00:00Z"},
        )
        assert backwards.status_code == 400

        too_long = client.get(
            "/api/page-visits/visits",
            params={"start": "2020-01-01T00:00:00Z", "end": "2026-10-06T00:00:00Z"},
        )
        assert too_long.status_code == 400


def test_page_visits_stay_out_of_the_operations_audit_log():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        clear_visits()
        client.post("/api/page-visits", json={"visits": [span(now - timedelta(minutes=5), 2)]})

        paths = {row["path"] for row in client.get("/api/operations", params={"limit": 500}).json()}
        assert "/api/page-visits" not in paths
