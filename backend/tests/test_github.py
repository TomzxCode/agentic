import json

from fastapi.testclient import TestClient

from agentic import services
from agentic.main import app
from agentic.models import SourceItem


def test_github_owner_repo():
    assert services.github_owner_repo("https://github.com/psf/requests/issues/1") == ("psf", "requests")
    assert services.github_owner_repo("https://github.com/psf/requests") == ("psf", "requests")
    assert services.github_owner_repo("git@github.com:psf/requests.git") == ("psf", "requests")
    assert services.github_owner_repo("https://gitlab.com/x/y") is None
    assert services.github_owner_repo(None) is None


def test_list_github_issues_parses(monkeypatch):
    payload = json.dumps(
        [
            {
                "number": 1,
                "title": "T",
                "url": "https://github.com/o/r/issues/1",
                "state": "OPEN",
                "author": {"login": "tom"},
                "labels": [{"name": "bug"}],
                "body": "B",
            }
        ]
    )
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: payload)
    issues = services.list_github_issues("o", "r")
    assert issues is not None
    assert issues[0]["number"] == 1
    assert issues[0]["author"] == "tom"
    assert issues[0]["labels"] == ["bug"]


def test_issues_endpoint(monkeypatch):
    payload = json.dumps([{"number": 5, "title": "Bug", "url": "http://x", "author": {"login": "a"}, "body": ""}])
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: payload)
    with TestClient(app) as client:
        assert client.get("/api/github/issues", params={"owner": "o", "repo": "r"}).json()[0]["number"] == 5
        # needs a repository or owner/repo
        assert client.get("/api/github/issues").status_code == 400


def test_fetch_github_issue(monkeypatch):
    payload = json.dumps(
        {
            "number": 7,
            "title": "Bug",
            "url": "https://github.com/o/r/issues/7",
            "state": "OPEN",
            "author": {"login": "a"},
            "labels": [{"name": "bug"}],
            "body": "body",
        }
    )
    seen: dict = {}

    def fake(cmd, timeout=60):
        seen["cmd"] = cmd
        return payload

    monkeypatch.setattr(services, "_run_cli", fake)
    issue = services.fetch_github_issue("o", "r", 7)
    assert issue is not None
    assert issue["title"] == "Bug"
    assert issue["labels"] == ["bug"]
    assert seen["cmd"][0] == "ghx" and seen["cmd"][1] == "issue"

    services.fetch_github_issue("o", "r", 7, kind="pull_request")
    assert seen["cmd"][1] == "pr"


def test_fetch_github_pull_request_carries_draft_and_state(monkeypatch):
    payload = json.dumps(
        {
            "number": 7,
            "title": "Draft PR",
            "url": "https://github.com/o/r/pull/7",
            "state": "OPEN",
            "isDraft": True,
            "author": {"login": "a"},
            "labels": [],
            "body": "wip",
        }
    )
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: payload)

    issue = services.fetch_github_issue("o", "r", 7, kind="pull_request")
    assert issue["state"] == "OPEN"
    assert issue["is_draft"] is True

    # The fetched metadata carries the state, draft flag, and author through to
    # the item.
    result = {"metadata": {}, "content": "", "title": "", "people": []}
    services._fetch_github("https://github.com/o/r/pull/7", result)
    assert result["metadata"]["kind"] == "pull_request"
    assert result["metadata"]["state"] == "OPEN"
    assert result["metadata"]["is_draft"] is True
    assert result["metadata"]["author"] == "a"


def test_issue_endpoint(monkeypatch):
    payload = json.dumps({"number": 9, "title": "Single", "url": "http://x", "author": {"login": "a"}, "body": "b"})
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: payload)
    with TestClient(app) as client:
        issue = client.get("/api/github/issue", params={"url": "https://github.com/o/r/issues/9"})
        assert issue.status_code == 200
        assert issue.json()["number"] == 9
        # not a GitHub issue URL
        assert client.get("/api/github/issue", params={"url": "https://example.com/x"}).status_code == 400

        monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: None)
        assert client.get("/api/github/issue", params={"url": "https://github.com/o/r/issues/9"}).status_code == 502


def test_create_task_from_github(monkeypatch):
    # Stub the item fetch so no network/gh is needed.
    from agentic.routers import tasks as tasks_router

    def fake_upsert(session, payload):
        item = SourceItem(source="github", kind="issue", url=payload.url, title="Imported issue", content="body text")
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    monkeypatch.setattr(tasks_router, "_upsert_item", fake_upsert)
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"github_url": "https://github.com/o/r/issues/9"}).json()
        assert task["title"] == "Imported issue"
        assert task["description"] == "body text"

        detail = client.get(f"/api/tasks/{task['id']}").json()
        assert len(detail["associations"]) == 1
        assert detail["associations"][0]["item"]["url"] == "https://github.com/o/r/issues/9"
        assert any(e["type"] == "item_added" for e in detail["timeline"])
        client.delete(f"/api/tasks/{task['id']}")
