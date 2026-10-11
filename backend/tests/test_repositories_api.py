"""Repository endpoints: validation, metadata detection, and cascading delete."""

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.routers import repositories as repositories_router
from agentic.routers import worktrees as worktrees_router


def _git_dir(tmp_path, name: str):
    path = tmp_path / name
    (path / ".git").mkdir(parents=True)
    return path


def test_create_repository_validates_and_reads_back(tmp_path):
    with TestClient(app) as client:
        plain = tmp_path / "plain"
        plain.mkdir()
        assert client.post("/api/repositories", json={"path": str(plain)}).status_code == 400

        repo_dir = _git_dir(tmp_path, "repo")
        created = client.post(
            "/api/repositories",
            json={
                "path": str(repo_dir),
                "name": "Custom",
                "remote_url": "https://github.com/o/r",
                "default_branch": "main",
            },
        ).json()
        assert created["name"] == "Custom"
        assert created["remote_url"] == "https://github.com/o/r"
        assert created["default_branch"] == "main"

        assert any(item["id"] == created["id"] for item in client.get("/api/repositories").json())
        assert client.get(f"/api/repositories/{created['id']}").json()["id"] == created["id"]
        assert client.get("/api/repositories/missing").status_code == 404

        client.delete(f"/api/repositories/{created['id']}")


def test_create_repository_detects_remote_and_branch(monkeypatch, tmp_path):
    monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: "git@github.com:o/r.git")
    monkeypatch.setattr(repositories_router, "detect_default_branch", lambda path: "develop")
    with TestClient(app) as client:
        repo = client.post("/api/repositories", json={"path": str(_git_dir(tmp_path, "repo"))}).json()
        assert repo["remote_url"] == "git@github.com:o/r.git"
        assert repo["default_branch"] == "develop"
        client.delete(f"/api/repositories/{repo['id']}")


def test_delete_repository_removes_worktrees_and_memberships(monkeypatch, tmp_path):
    monkeypatch.setattr(worktrees_router, "create_worktree", lambda *args, **kwargs: None)
    removed: list = []
    monkeypatch.setattr(repositories_router, "remove_worktree", lambda repo_path, path: removed.append(path))
    with TestClient(app) as client:
        repo = client.post("/api/repositories", json={"path": str(_git_dir(tmp_path, "repo"))}).json()
        task = client.post("/api/tasks", json={"title": "T", "repository_ids": [repo["id"]]}).json()
        worktree = client.post(f"/api/tasks/{task['id']}/worktrees", json={"repository_id": repo["id"]}).json()

        assert client.delete(f"/api/repositories/{repo['id']}").status_code == 204
        assert removed == [worktree["path"]]
        # The worktree row and the task association are gone with the repository.
        assert client.get(f"/api/tasks/{task['id']}").json()["worktrees"] == []
        assert client.get(f"/api/tasks/{task['id']}").json()["repository_ids"] == []

        assert client.delete("/api/repositories/missing").status_code == 404
        client.delete(f"/api/tasks/{task['id']}")
