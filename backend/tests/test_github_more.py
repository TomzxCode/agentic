"""GitHub issue listing by registered repository, and its error paths."""

import json

from fastapi.testclient import TestClient

from agentic import services
from agentic.main import app


def test_issues_endpoint_by_repository(monkeypatch, tmp_path):
    payload = json.dumps([{"number": 1, "title": "T", "url": "u", "author": {"login": "a"}, "body": ""}])
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: payload)
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post(
            "/api/repositories", json={"path": str(repo_dir), "remote_url": "https://github.com/o/r"}
        ).json()
        assert client.get("/api/github/issues", params={"repository_id": repo["id"]}).json()[0]["number"] == 1

        assert client.get("/api/github/issues", params={"repository_id": "nope"}).status_code == 404

        # A repository without a GitHub remote cannot list issues.
        other_dir = tmp_path / "other"
        (other_dir / ".git").mkdir(parents=True)
        other = client.post(
            "/api/repositories", json={"path": str(other_dir), "remote_url": "https://gitlab.com/x/y"}
        ).json()
        assert client.get("/api/github/issues", params={"repository_id": other["id"]}).status_code == 400

        # ghx unavailable.
        monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: None)
        assert client.get("/api/github/issues", params={"owner": "o", "repo": "r"}).status_code == 502

        client.delete(f"/api/repositories/{repo['id']}")
        client.delete(f"/api/repositories/{other['id']}")
