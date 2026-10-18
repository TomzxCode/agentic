"""Agent sessions recorded against a task, with their session links."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.settings_store import update_settings


def test_session_crud_records_timeline_and_task_detail():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "S"}).json()

        created = client.post(
            f"/api/tasks/{task['id']}/sessions",
            json={"session_id": "ses_abc", "cwd": "/work", "label": "first"},
        )
        assert created.status_code == 201
        session = created.json()
        assert session["session_id"] == "ses_abc"
        assert session["label"] == "first"
        assert session["cwd"] == "/work"

        listed = client.get(f"/api/tasks/{task['id']}/sessions").json()
        assert [row["id"] for row in listed] == [session["id"]]

        fetched = client.get(f"/api/tasks/{task['id']}/sessions/{session['id']}").json()
        assert fetched["session_id"] == "ses_abc"

        updated = client.patch(f"/api/tasks/{task['id']}/sessions/{session['id']}", json={"label": "renamed"}).json()
        assert updated["label"] == "renamed"

        detail = client.get(f"/api/tasks/{task['id']}").json()
        assert [row["id"] for row in detail["sessions"]] == [session["id"]]

        timeline = client.get(f"/api/tasks/{task['id']}/timeline").json()
        types = {event["type"] for event in timeline}
        assert {"session_added", "session_updated"} <= types

        assert client.delete(f"/api/tasks/{task['id']}/sessions/{session['id']}").status_code == 204
        assert client.get(f"/api/tasks/{task['id']}/sessions").json() == []
        assert any(
            event["type"] == "session_removed" for event in client.get(f"/api/tasks/{task['id']}/timeline").json()
        )

        client.delete(f"/api/tasks/{task['id']}")


def test_session_requires_an_id_and_valid_harness():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "S"}).json()
        assert client.post(f"/api/tasks/{task['id']}/sessions", json={"session_id": "  "}).status_code == 400
        assert (
            client.post(
                f"/api/tasks/{task['id']}/sessions", json={"session_id": "ses_x", "harness_id": "missing"}
            ).status_code
            == 404
        )
        assert client.get("/api/tasks/missing/sessions").status_code == 404
        client.delete(f"/api/tasks/{task['id']}")


def test_session_harness_defaults_to_the_task_and_builds_links():
    with TestClient(app) as client:
        harness = client.post(
            "/api/harnesses",
            json={"name": "Custom", "command": "custom-acp", "resume_command": "custom --session {session}"},
        ).json()
        task = client.post("/api/tasks", json={"title": "S", "harness_id": harness["id"]}).json()
        client.patch("/api/settings", json={"openchamber_url": "http://box:3001"})

        session = client.post(f"/api/tasks/{task['id']}/sessions", json={"session_id": "ses_42", "cwd": "/work"}).json()
        # The harness falls back to the task's harness.
        assert session["harness_id"] == harness["id"]
        by_id = {link["id"]: link for link in session["links"]}
        assert by_id["openchamber"]["url"] == "http://box:3001/?session=ses_42"
        assert by_id["command"]["command"] == "cd /work && custom --session ses_42"

        client.patch("/api/settings", json={"openchamber_url": ""})
        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/harnesses/{harness['id']}")


def test_session_belongs_to_one_task_and_survives_harness_deletion():
    with TestClient(app) as client:
        harness = client.post("/api/harnesses", json={"name": "H", "command": "h"}).json()
        first = client.post("/api/tasks", json={"title": "A"}).json()
        second = client.post("/api/tasks", json={"title": "B"}).json()
        session = client.post(
            f"/api/tasks/{first['id']}/sessions", json={"session_id": "ses_1", "harness_id": harness["id"]}
        ).json()

        # Addressed through the wrong task, the session is not found.
        assert client.get(f"/api/tasks/{second['id']}/sessions/{session['id']}").status_code == 404
        assert client.delete(f"/api/tasks/{second['id']}/sessions/{session['id']}").status_code == 404

        # Deleting the harness detaches the session rather than leaving it dangling.
        assert client.delete(f"/api/harnesses/{harness['id']}").status_code == 204
        assert client.get(f"/api/tasks/{first['id']}/sessions/{session['id']}").json()["harness_id"] is None

        client.delete(f"/api/tasks/{first['id']}")
        client.delete(f"/api/tasks/{second['id']}")


def test_deleting_a_task_removes_its_sessions():
    create_db_and_tables()
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "Gone"}).json()
        session = client.post(f"/api/tasks/{task['id']}/sessions", json={"session_id": "ses_gone"}).json()
        client.delete(f"/api/tasks/{task['id']}")
        assert client.get(f"/api/tasks/{task['id']}/sessions/{session['id']}").status_code == 404

    from agentic.models.agents import AgentSession

    with Session(engine) as db:
        assert db.get(AgentSession, session["id"]) is None


def test_session_links_are_empty_without_a_configured_target():
    create_db_and_tables()
    with TestClient(app) as client:
        with Session(engine) as db:
            update_settings(db, {"openchamber_url": "", "terminal_url_template": ""})
        task = client.post("/api/tasks", json={"title": "Bare"}).json()
        session = client.post(f"/api/tasks/{task['id']}/sessions", json={"session_id": "ses_bare"}).json()
        assert session["links"] == []
        client.delete(f"/api/tasks/{task['id']}")
