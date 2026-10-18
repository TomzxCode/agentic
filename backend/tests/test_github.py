import json
import subprocess

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.models.items import SourceItem
from agentic.services import github, shell


def test_github_owner_repo():
    assert github.github_owner_repo("https://github.com/psf/requests/issues/1") == ("psf", "requests")
    assert github.github_owner_repo("https://github.com/psf/requests") == ("psf", "requests")
    assert github.github_owner_repo("git@github.com:psf/requests.git") == ("psf", "requests")
    assert github.github_owner_repo("https://gitlab.com/x/y") is None
    assert github.github_owner_repo(None) is None


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
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    issues = github.list_github_issues("o", "r")
    assert issues is not None
    assert issues[0]["number"] == 1
    assert issues[0]["author"] == "tom"
    assert issues[0]["labels"] == ["bug"]


def test_issues_endpoint(monkeypatch):
    payload = json.dumps([{"number": 5, "title": "Bug", "url": "http://x", "author": {"login": "a"}, "body": ""}])
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
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

    monkeypatch.setattr(shell, "_run_cli", fake)
    issue = github.fetch_github_issue("o", "r", 7)
    assert issue is not None
    assert issue["title"] == "Bug"
    assert issue["labels"] == ["bug"]
    assert seen["cmd"][0] == "ghx" and seen["cmd"][1] == "issue"

    github.fetch_github_issue("o", "r", 7, kind="pull_request")
    assert seen["cmd"][1] == "pr"


def test_fetch_github_pull_request_carries_draft_and_state(monkeypatch):
    payload = json.dumps(
        {
            "number": 7,
            "title": "Draft PR",
            "url": "https://github.com/o/r/pull/7",
            "state": "MERGED",
            "isDraft": False,
            "mergedAt": "2026-10-11T05:23:53Z",
            "author": {"login": "a"},
            "labels": [],
            "body": "wip",
        }
    )
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)

    issue = github.fetch_github_issue("o", "r", 7, kind="pull_request")
    assert issue is not None
    assert issue["state"] == "MERGED"
    assert issue["is_draft"] is False
    assert issue["merged_at"] == "2026-10-11T05:23:53Z"

    # The fetched metadata carries the state, draft flag, merge time, and author
    # through to the item.
    result = {"metadata": {}, "content": "", "title": "", "people": []}
    github._fetch_github("https://github.com/o/r/pull/7", result)
    assert result["metadata"]["kind"] == "pull_request"
    assert result["metadata"]["state"] == "MERGED"
    assert result["metadata"]["is_draft"] is False
    assert result["metadata"]["merged_at"] == "2026-10-11T05:23:53Z"
    assert result["metadata"]["author"] == "a"


def test_list_github_pulls_parses(monkeypatch):
    payload = json.dumps(
        [
            {
                "number": 6,
                "title": "Bump vite",
                "url": "https://github.com/o/r/pull/6",
                "state": "CLOSED",
                "isDraft": False,
                "mergedAt": None,
                "createdAt": "2026-10-11T03:53:08Z",
                "author": {"login": "dependabot"},
                "labels": [{"name": "dependencies"}],
            }
        ]
    )
    seen: dict = {}

    def fake(cmd, timeout=60):
        seen["cmd"] = cmd
        return payload

    monkeypatch.setattr(shell, "_run_cli", fake)
    pulls = github.list_github_pulls("o", "r", state="all")
    assert pulls is not None
    assert pulls[0]["kind"] == "pr"
    assert pulls[0]["state"] == "CLOSED"
    assert pulls[0]["author"] == "dependabot"
    assert seen["cmd"][1] == "pr"
    # The listing asks ghx for just the fields it renders, not the whole object.
    assert "--json" in seen["cmd"] and "isDraft" in seen["cmd"][seen["cmd"].index("--json") + 1]


def test_list_github_pulls_returns_none_when_cli_fails(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.list_github_pulls("o", "r") is None


def test_list_github_repo_items_combines_issues_and_pulls(monkeypatch):
    issue = json.dumps([{"number": 1, "title": "Bug", "url": "http://i/1", "state": "OPEN", "body": "long"}])
    pull = json.dumps([{"number": 2, "title": "Fix", "url": "http://p/2", "state": "MERGED", "isDraft": False}])

    def fake(cmd, timeout=60):
        return issue if cmd[1] == "issue" else pull

    monkeypatch.setattr(shell, "_run_cli", fake)
    listing = github.list_github_repo_items("o", "r")
    assert listing is not None
    assert listing["failed"] == []
    assert [item["kind"] for item in listing["items"]] == ["issue", "pr"]
    # The issue's body is dropped: the listing only needs metadata.
    assert "body" not in listing["items"][0]


def test_list_github_repo_items_returns_none_when_both_fail(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.list_github_repo_items("o", "r") is None


def test_list_github_repo_items_reports_a_one_kind_failure(monkeypatch):
    pull = json.dumps([{"number": 2, "title": "Fix", "url": "http://p/2", "state": "OPEN", "isDraft": False}])

    def fake(cmd, timeout=60):
        return None if cmd[1] == "issue" else pull

    monkeypatch.setattr(shell, "_run_cli", fake)
    listing = github.list_github_repo_items("o", "r")
    assert listing is not None
    assert listing["failed"] == ["issues"]
    assert [item["kind"] for item in listing["items"]] == ["pr"]


def test_refresh_github_cache(monkeypatch):
    seen: dict = {}

    def fake(cmd, timeout=60):
        seen["cmd"] = cmd
        return "cached"

    monkeypatch.setattr(shell, "_run_cli", fake)
    assert github.refresh_github_cache("o", "r") is True
    assert seen["cmd"][:2] == ["ghx", "cache"]
    assert "--force" in seen["cmd"]

    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.refresh_github_cache("o", "r") is False


def test_repository_endpoint(monkeypatch):
    issue = json.dumps([{"number": 1, "title": "Bug", "url": "http://i/1", "state": "OPEN", "body": "b"}])
    pull = json.dumps([{"number": 2, "title": "Fix", "url": "http://p/2", "state": "MERGED", "isDraft": False}])
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: issue if cmd[1] == "issue" else pull)
    with TestClient(app) as client:
        body = client.get("/api/github/repository", params={"owner": "o", "repo": "r"}).json()
        assert [(row["kind"], row["number"]) for row in body["items"]] == [("issue", 1), ("pr", 2)]
        assert body["failed"] == []
        # needs a repository or owner/repo
        assert client.get("/api/github/repository").status_code == 400

        monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
        assert client.get("/api/github/repository", params={"owner": "o", "repo": "r"}).status_code == 502


def test_repository_endpoint_forces_a_refresh(monkeypatch):
    seen: list[list[str]] = []

    def fake(cmd, timeout=60):
        seen.append(cmd)
        return "[]"

    monkeypatch.setattr(shell, "_run_cli", fake)
    with TestClient(app) as client:
        client.get("/api/github/repository", params={"owner": "o", "repo": "r", "refresh": "true"})
    assert seen and seen[0][:2] == ["ghx", "cache"]


def test_issue_endpoint(monkeypatch):
    payload = json.dumps({"number": 9, "title": "Single", "url": "http://x", "author": {"login": "a"}, "body": "b"})
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    with TestClient(app) as client:
        issue = client.get("/api/github/issue", params={"url": "https://github.com/o/r/issues/9"})
        assert issue.status_code == 200
        assert issue.json()["number"] == 9
        # not a GitHub issue URL
        assert client.get("/api/github/issue", params={"url": "https://example.com/x"}).status_code == 400

        monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
        assert client.get("/api/github/issue", params={"url": "https://github.com/o/r/issues/9"}).status_code == 502


def test_create_github_issue(monkeypatch):
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/o/r/issues/12\n", stderr="")

    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(shell.subprocess, "run", fake_run)

    issue = github.create_github_issue("o", "r", "A title", "A body")
    assert issue is not None
    assert issue["number"] == 12
    assert issue["url"] == "https://github.com/o/r/issues/12"
    assert issue["state"] == "OPEN"
    assert seen["cmd"][:2] == ["gh", "issue"]
    assert "o/r" in seen["cmd"]
    assert "A title" in seen["cmd"]
    assert "A body" in seen["cmd"]


def test_create_github_issue_none_on_failure(monkeypatch):
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        shell.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="nope"),
    )
    assert github.create_github_issue("o", "r", "T") is None

    # gh missing altogether.
    monkeypatch.setattr(shell.shutil, "which", lambda name: None)
    assert github.create_github_issue("o", "r", "T") is None


def test_create_issue_endpoint(monkeypatch):
    from agentic.routers import github as github_router

    created: dict = {}

    def fake_create(owner, repo, title, body=""):
        created.update(owner=owner, repo=repo, title=title, body=body)
        return {
            "number": 4,
            "title": title,
            "url": "https://github.com/o/r/issues/4",
            "state": "OPEN",
            "body": body,
        }

    monkeypatch.setattr(github_router, "create_github_issue", fake_create)
    with TestClient(app) as client:
        res = client.post("/api/github/issues", json={"owner": "o", "repo": "r", "title": "T", "body": "B"})
        assert res.status_code == 200
        assert res.json()["number"] == 4
        assert created == {"owner": "o", "repo": "r", "title": "T", "body": "B"}

        # A title is required, and a repository must resolve to owner/repo.
        assert client.post("/api/github/issues", json={"owner": "o", "repo": "r", "title": "   "}).status_code == 400
        assert client.post("/api/github/issues", json={"title": "T"}).status_code == 400

        # A failed `gh` call reads as a bad gateway, not a crash.
        monkeypatch.setattr(github_router, "create_github_issue", lambda *args, **kwargs: None)
        assert client.post("/api/github/issues", json={"owner": "o", "repo": "r", "title": "T"}).status_code == 502


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
