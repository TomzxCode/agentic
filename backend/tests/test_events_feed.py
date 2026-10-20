"""The cross-task events feed."""

from fastapi.testclient import TestClient

from agentic.main import app


def test_events_stream_activity_across_tasks_with_the_task_context():
    with TestClient(app) as client:
        first = client.post("/api/tasks", json={"title": "Events feed alpha"}).json()["id"]
        second = client.post(
            "/api/tasks",
            json={"title": "Events feed beta"},
            headers={"X-Agentic-Client": "cli", "X-Agentic-Actor": "agent"},
        ).json()["id"]
        client.patch(f"/api/tasks/{first}", json={"status": "in_progress"})

        rows = client.get("/api/events", params={"q": "Events feed"}).json()
        assert {row["task_id"] for row in rows} == {first, second}
        created = next(row for row in rows if row["task_id"] == second and row["type"] == "created")
        assert created["task_title"] == "Events feed beta"
        assert created["task_status"] == "open"
        assert (created["client"], created["actor"]) == ("cli", "agent")
        # Newest first.
        assert [row["created_at"] for row in rows] == sorted((row["created_at"] for row in rows), reverse=True)

        client.delete(f"/api/tasks/{first}")
        client.delete(f"/api/tasks/{second}")


def test_events_filter_by_task_type_actor_and_client():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Events filters"}).json()["id"]
        client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "blocked"},
            headers={"X-Agentic-Client": "cli", "X-Agentic-Actor": "agent"},
        )

        by_task = client.get("/api/events", params={"task_id": task_id}).json()
        assert by_task
        assert all(row["task_id"] == task_id for row in by_task)

        updated = client.get("/api/events", params={"task_id": task_id, "type": "updated"}).json()
        assert updated and all(row["type"] == "updated" for row in updated)

        agent_rows = client.get("/api/events", params={"task_id": task_id, "actor": "agent", "client": "cli"}).json()
        assert agent_rows and all(row["actor"] == "agent" and row["client"] == "cli" for row in agent_rows)

        no_match = client.get("/api/events", params={"task_id": task_id, "q": "nothing matches this"}).json()
        assert no_match == []

        client.delete(f"/api/tasks/{task_id}")


def test_events_page_with_the_before_cursor_without_repeating_rows():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Events paging"}).json()["id"]
        for index in range(4):
            client.patch(f"/api/tasks/{task_id}", json={"title": f"Events paging {index}"})

        first_page = client.get("/api/events", params={"task_id": task_id, "limit": 2}).json()
        assert len(first_page) == 2
        last = first_page[-1]
        second_page = client.get(
            "/api/events",
            params={
                "task_id": task_id,
                "limit": 10,
                "before": last["created_at"],
                "before_id": last["id"],
            },
        ).json()
        assert second_page
        assert {row["id"] for row in first_page}.isdisjoint({row["id"] for row in second_page})
        # The pages continue where the first stopped, newest first.
        assert second_page[0]["created_at"] <= last["created_at"]

        client.delete(f"/api/tasks/{task_id}")
