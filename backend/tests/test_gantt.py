from fastapi.testclient import TestClient

from agentic.main import app


def test_gantt_lists_active_tasks_with_markers():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Ship the Gantt page"}).json()["id"]
        client.patch(f"/api/tasks/{task_id}", json={"status": "in_progress"})

        rows = client.get("/api/gantt").json()
        row = next(r for r in rows if r["id"] == task_id)
        assert row["status"] == "in_progress"
        assert "created_at" in row and "updated_at" in row
        types = {marker["type"] for marker in row["markers"]}
        assert "created" in types
        assert "updated" in types
        # markers are ordered oldest first
        assert [m["created_at"] for m in row["markers"]] == sorted(m["created_at"] for m in row["markers"])

        client.delete(f"/api/tasks/{task_id}")


def test_gantt_hides_done_unless_asked():
    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"title": "Finished work"}).json()["id"]
        client.patch(f"/api/tasks/{task_id}", json={"status": "done"})

        assert all(r["id"] != task_id for r in client.get("/api/gantt").json())

        rows = client.get("/api/gantt", params={"include_done": "true"}).json()
        assert any(r["id"] == task_id for r in rows)

        client.delete(f"/api/tasks/{task_id}")
