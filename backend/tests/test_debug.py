from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentic import debug


def test_request_ids_are_unique_and_stable_across_snapshots(monkeypatch):
    monkeypatch.setattr(debug, "_recent_requests", [])
    app = FastAPI()
    app.add_middleware(debug.DebugMiddleware)

    @app.get("/api/tasks")
    def tasks():
        return []

    @app.get("/api/debug/requests")
    def requests():
        return debug.recent_requests()

    with TestClient(app) as client:
        client.get("/api/tasks")
        first = client.get("/api/debug/requests").json()
        client.get("/api/tasks")
        second = client.get("/api/debug/requests").json()
        assert len(second) == 2
        assert first[0]["id"] == second[1]["id"]
        assert second[0]["id"] != second[1]["id"]
