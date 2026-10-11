"""Worktrees: creating one resolves the repository from the task when not given."""

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.routers import worktrees as worktrees_router


def test_create_worktree_falls_back_to_task_repository(monkeypatch, tmp_path):
    calls: dict = {}

    def fake_create_worktree(repo_path, branch, path, base=None):
        calls.update(repo_path=repo_path, branch=branch, path=path, base=base)

    monkeypatch.setattr(worktrees_router, "create_worktree", fake_create_worktree)
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        task = client.post("/api/tasks", json={"title": "T", "repository_ids": [repo["id"]]}).json()

        # No repository_id in the payload: it resolves to the task's repository.
        response = client.post(f"/api/tasks/{task['id']}/worktrees", json={})
        assert response.status_code == 201
        assert response.json()["repository_id"] == repo["id"]
        assert calls["repo_path"] == str(repo_dir)

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_create_worktree_without_repository_is_rejected(monkeypatch):
    monkeypatch.setattr(worktrees_router, "create_worktree", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "T"}).json()
        response = client.post(f"/api/tasks/{task['id']}/worktrees", json={})
        assert response.status_code == 400
        client.delete(f"/api/tasks/{task['id']}")
