from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agentic.main import app


def test_deadline_lifecycle_and_upcoming_view():
    now = datetime.now(UTC)
    overdue = (now - timedelta(days=1)).isoformat()
    soon = (now + timedelta(hours=2)).isoformat()
    far = (now + timedelta(days=30)).isoformat()

    with TestClient(app) as client:
        overdue_task = client.post("/api/tasks", json={"title": "Overdue", "deadline": overdue}).json()
        soon_task = client.post("/api/tasks", json={"title": "Soon", "deadline": soon}).json()
        far_task = client.post("/api/tasks", json={"title": "Far", "deadline": far}).json()
        plain_task = client.post("/api/tasks", json={"title": "No deadline"}).json()

        # A deadline is stored and returned on create.
        assert overdue_task["deadline"] is not None

        # Setting a deadline later records it on the timeline.
        edited = client.patch(f"/api/tasks/{plain_task['id']}", json={"deadline": soon}).json()
        assert edited["deadline"] is not None
        event = next(e for e in client.get(f"/api/tasks/{plain_task['id']}/timeline").json() if e["type"] == "updated")
        assert "deadline" in event["data_json"]["changes"]

        # The upcoming view keeps near and overdue deadlines, drops the far and
        # deadline-less tasks, and sorts soonest first (overdue leads).
        upcoming = client.get("/api/tasks/deadlines?within_days=7").json()
        ids = [task["id"] for task in upcoming]
        assert overdue_task["id"] in ids
        assert soon_task["id"] in ids
        assert plain_task["id"] in ids
        assert far_task["id"] not in ids
        assert ids.index(overdue_task["id"]) < ids.index(soon_task["id"])
        deadlines = {task["id"]: task["deadline"] for task in upcoming}
        assert ids == sorted(ids, key=lambda task_id: deadlines[task_id])

        # A closed task leaves the view even with a near deadline.
        client.patch(f"/api/tasks/{soon_task['id']}", json={"status": "done"})
        assert soon_task["id"] not in [task["id"] for task in client.get("/api/tasks/deadlines").json()]

        # A deadline can be cleared with an explicit null.
        assert client.patch(f"/api/tasks/{overdue_task['id']}", json={"deadline": None}).json()["deadline"] is None

        for task_id in (overdue_task["id"], soon_task["id"], far_task["id"], plain_task["id"]):
            client.delete(f"/api/tasks/{task_id}")


def test_naive_deadline_is_treated_as_utc():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "Naive", "deadline": "2026-02-01T09:00:00"}).json()
        assert task["deadline"].startswith("2026-02-01T09:00:00")
        # An explicit null clears it; the naive form is normalized, not stored raw.
        assert client.patch(f"/api/tasks/{task['id']}", json={"deadline": None}).json()["deadline"] is None
        client.delete(f"/api/tasks/{task['id']}")


def test_deadlines_window_zero_keeps_only_overdue():
    now = datetime.now(UTC)
    with TestClient(app) as client:
        overdue = client.post(
            "/api/tasks", json={"title": "Overdue", "deadline": (now - timedelta(hours=1)).isoformat()}
        ).json()
        upcoming = client.post(
            "/api/tasks", json={"title": "Upcoming", "deadline": (now + timedelta(days=3)).isoformat()}
        ).json()

        ids = [task["id"] for task in client.get("/api/tasks/deadlines?within_days=0").json()]
        assert overdue["id"] in ids
        assert upcoming["id"] not in ids

        for task_id in (overdue["id"], upcoming["id"]):
            client.delete(f"/api/tasks/{task_id}")
