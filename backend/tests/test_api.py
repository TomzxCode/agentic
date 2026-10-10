from fastapi.testclient import TestClient

from agentic.main import app


def test_problem_lifecycle():
    with TestClient(app) as client:
        created = client.post("/api/problems", json={"title": "Investigate flakiness", "priority": 2})
        assert created.status_code == 201
        problem_id = created.json()["id"]

        listed = client.get("/api/problems").json()
        assert any(p["id"] == problem_id for p in listed)

        associated = client.post(
            f"/api/problems/{problem_id}/items",
            json={"item": {"source": "note", "title": "A note", "content": "hello", "fetch": False}},
        )
        assert associated.status_code == 201

        detail = client.get(f"/api/problems/{problem_id}").json()
        assert len(detail["associations"]) == 1
        assert detail["associations"][0]["item"]["title"] == "A note"
        assert detail["timeline"]

        updated = client.patch(f"/api/problems/{problem_id}", json={"status": "in_progress"})
        assert updated.json()["status"] == "in_progress"

        assert client.delete(f"/api/problems/{problem_id}").status_code == 204
        assert client.get(f"/api/problems/{problem_id}").status_code == 404


def test_timeline_records_before_and_after():
    with TestClient(app) as client:
        problem_id = client.post("/api/problems", json={"title": "T", "priority": 1}).json()["id"]

        client.patch(f"/api/problems/{problem_id}", json={"title": "T2", "priority": 3})
        updated = [e for e in client.get(f"/api/problems/{problem_id}/timeline").json() if e["type"] == "updated"]
        assert len(updated) == 1
        changes = updated[0]["data_json"]["changes"]
        assert changes["title"] == {"from": "T", "to": "T2"}
        assert changes["priority"] == {"from": 1, "to": 3}

        # A no-op update records nothing.
        client.patch(f"/api/problems/{problem_id}", json={"title": "T2"})
        updated = [e for e in client.get(f"/api/problems/{problem_id}/timeline").json() if e["type"] == "updated"]
        assert len(updated) == 1

        client.delete(f"/api/problems/{problem_id}")


def test_harnesses_are_seeded():
    with TestClient(app) as client:
        harnesses = client.get("/api/harnesses").json()
        names = {h["name"] for h in harnesses}
        assert "OpenCode" in names
        assert "pi" in names


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
