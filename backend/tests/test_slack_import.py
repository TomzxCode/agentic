"""Creating a task from a Slack thread, delegated to an agent for its title and summary."""

from fastapi.testclient import TestClient
from sqlmodel import select

from agentic.main import app
from agentic.models.items import SourceItem
from agentic.routers import agent_runs as agents_router
from agentic.routers import tasks as tasks_router
from agentic.services import prompts

SLACK_URL = "https://acme.slack.com/archives/C123/p1700000000000000"
EXTERNAL_ID = "C123:1700000000000000"
THREAD = "Ada: fix the flaky ingest\nBob: agreed, let's do it"


async def _no_enqueue(run_id: str) -> None:
    """Skip the queue write; tests never start a worker."""
    return None


def _recorder(sink: list) -> object:
    async def record(run_id: str) -> None:
        sink.append(run_id)

    return record


def test_extract_summary_json_reads_title_and_summary():
    data = prompts.extract_summary_json('{"title": "Fix ingest", "summary": "They discussed it."}')
    assert data == {"title": "Fix ingest", "summary": "They discussed it."}

    fenced = prompts.extract_summary_json('Here you go:\n```json\n{"title": "T", "summary": "S"}\n```')
    assert fenced == {"title": "T", "summary": "S"}

    # Either key is enough: a summary-only reply still earns its summary.
    assert prompts.extract_summary_json('{"summary": "only"}') == {"title": "", "summary": "only"}

    # Nothing usable at all.
    assert prompts.extract_summary_json('{"title": "", "summary": "  "}') is None
    assert prompts.extract_summary_json("no json here") is None


def test_build_summary_prompt_includes_the_thread():
    prompt = prompts.build_summary_prompt("Ada: should we ship?\nBob: yes")
    assert "Ada: should we ship?" in prompt
    assert "title" in prompt and "summary" in prompt


def _fake_upsert(content: str = THREAD):
    """An idempotent stand-in for ``_upsert_item`` (the real one de-dupes by external id)."""

    def fake(session, payload):
        item = session.exec(
            select(SourceItem).where(SourceItem.source == "slack", SourceItem.external_id == EXTERNAL_ID)
        ).first()
        if item is None:
            item = SourceItem(source="slack", kind="thread", external_id=EXTERNAL_ID)
            session.add(item)
        item.url = payload.url
        item.content = content
        session.commit()
        session.refresh(item)
        return item

    return fake


def test_create_task_from_slack_enqueues_a_summary_run(monkeypatch):
    enqueued: list = []
    monkeypatch.setattr(agents_router, "enqueue_run", _recorder(enqueued))
    monkeypatch.setattr(tasks_router, "_upsert_item", _fake_upsert())

    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"slack_url": SLACK_URL}).json()
        # The agent names it, so a placeholder holds its place until the run ends.
        assert task["title"] == "Slack thread"

        detail = client.get(f"/api/tasks/{task['id']}").json()
        assert len(detail["associations"]) == 1
        assert detail["associations"][0]["item"]["url"] == SLACK_URL
        types = [event["type"] for event in detail["timeline"]]
        assert "item_added" in types
        assert "summary_requested" in types

        runs = client.get(f"/api/tasks/{task['id']}/runs").json()
        assert runs and runs[0]["kind"] == "summarize_slack"
        # The gathered conversation is handed to the agent in the prompt.
        assert "Ada: fix the flaky ingest" in runs[0]["prompt"]
        assert enqueued == [runs[0]["id"]]

        client.delete(f"/api/tasks/{task['id']}")


def test_create_task_from_slack_keeps_a_given_title(monkeypatch):
    monkeypatch.setattr(agents_router, "enqueue_run", _no_enqueue)
    monkeypatch.setattr(tasks_router, "_upsert_item", _fake_upsert())

    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"slack_url": SLACK_URL, "title": "My title"}).json()
        assert task["title"] == "My title"
        client.delete(f"/api/tasks/{task['id']}")


def test_create_task_from_slack_records_a_fetch_failure(monkeypatch):
    # No slackx output: the item exists but carries no conversation.
    monkeypatch.setattr(agents_router, "enqueue_run", _no_enqueue)
    monkeypatch.setattr(tasks_router, "_upsert_item", _fake_upsert(content=""))

    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"slack_url": SLACK_URL}).json()
        assert task["title"] == "Slack thread"

        detail = client.get(f"/api/tasks/{task['id']}").json()
        types = [event["type"] for event in detail["timeline"]]
        assert "summary_failed" in types
        # Nothing to summarize, so no run is queued.
        assert client.get(f"/api/tasks/{task['id']}/runs").json() == []

        client.delete(f"/api/tasks/{task['id']}")


def test_create_task_requires_a_title_url_or_slack_url():
    with TestClient(app) as client:
        assert client.post("/api/tasks", json={}).status_code == 400


def test_refresh_summary_enqueues_another_run(monkeypatch):
    enqueued: list = []
    monkeypatch.setattr(agents_router, "enqueue_run", _recorder(enqueued))
    monkeypatch.setattr(tasks_router, "_upsert_item", _fake_upsert())

    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"slack_url": SLACK_URL}).json()
        run = client.post(f"/api/tasks/{task['id']}/summary/refresh").json()
        assert run["kind"] == "summarize_slack"
        assert "Ada: fix the flaky ingest" in run["prompt"]
        # The original import run stays; the retry is a second run (and a second job).
        assert len(client.get(f"/api/tasks/{task['id']}/runs").json()) == 2
        assert len(enqueued) == 2
        client.delete(f"/api/tasks/{task['id']}")


def test_refresh_summary_without_a_slack_thread_is_rejected():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "No slack thread"}).json()
        assert client.post(f"/api/tasks/{task['id']}/summary/refresh").status_code == 400
        client.delete(f"/api/tasks/{task['id']}")
