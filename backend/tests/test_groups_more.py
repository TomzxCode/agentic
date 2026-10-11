"""Repository group endpoints: validation, updates, and not-found handling."""

from fastapi.testclient import TestClient

from agentic.main import app


def test_group_validation_reads_and_updates():
    with TestClient(app) as client:
        assert client.post("/api/groups", json={"name": "   "}).status_code == 400
        assert client.get("/api/groups/missing").status_code == 404

        group = client.post("/api/groups", json={"name": "Core", "description": "d"}).json()
        assert any(item["id"] == group["id"] for item in client.get("/api/groups").json())
        assert client.get(f"/api/groups/{group['id']}").json()["name"] == "Core"

        updated = client.patch(f"/api/groups/{group['id']}", json={"name": "Renamed", "description": "new"}).json()
        assert updated["name"] == "Renamed" and updated["description"] == "new"

        assert client.patch("/api/groups/missing", json={"name": "x"}).status_code == 404
        assert client.delete("/api/groups/missing").status_code == 404

        client.delete(f"/api/groups/{group['id']}")
