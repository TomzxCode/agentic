"""Session-link helpers and the run serializer that attaches them."""

from fastapi.testclient import TestClient

from agentic.db import create_db_and_tables
from agentic.links import _fill, _join
from agentic.main import app


def test_fill_and_join_helpers():
    assert _fill("a {x} b {y}", {"x": "1", "y": "2"}) == "a 1 b 2"
    assert _join("http://h/", "/p") == "http://h/p"
    assert _join("http://h", "p") == "http://h/p"
    assert _join("http://h", "") == "http://h"


def test_run_read_attaches_openchamber_and_resume_links():
    create_db_and_tables()
    with TestClient(app) as client:
        harness = client.post(
            "/api/harnesses", json={"name": "H", "command": "h", "resume_command": "go --session {session}"}
        ).json()
        task = client.post("/api/tasks", json={"title": "t", "harness_id": harness["id"]}).json()

        # Point OpenChamber at a reachable base, then create a run with a session.
        client.patch("/api/settings", json={"openchamber_url": "http://oc/", "terminal_url_template": ""})
        from sqlmodel import Session

        from agentic.db import engine
        from agentic.models.agents import AgentRun

        with Session(engine) as session:
            run = AgentRun(task_id=task["id"], harness_id=harness["id"], cwd="/w", session_id="ses")
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

        read = client.get(f"/api/runs/{run_id}").json()
        links = {link["id"]: link for link in read["links"]}
        assert links["openchamber"]["url"] == "http://oc/?session=ses"
        assert links["command"]["command"] == "cd /w && go --session ses"

        client.patch("/api/settings", json={"openchamber_url": ""})
        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/harnesses/{harness['id']}")
