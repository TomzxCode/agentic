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


def test_create_worktree_with_explicit_repository_and_list(monkeypatch, tmp_path):
    monkeypatch.setattr(worktrees_router, "create_worktree", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        task = client.post("/api/tasks", json={"title": "T"}).json()

        response = client.post(
            f"/api/tasks/{task['id']}/worktrees",
            json={"repository_id": repo["id"], "branch": "feature", "base": "main"},
        )
        assert response.status_code == 201
        worktree = response.json()
        assert worktree["branch"] == "feature"

        listed = client.get(f"/api/tasks/{task['id']}/worktrees").json()
        assert any(item["id"] == worktree["id"] for item in listed)

        # Unknown task ids are rejected before listing.
        assert client.get("/api/tasks/missing/worktrees").status_code == 404

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_create_worktree_unknown_repository_is_404(monkeypatch):
    monkeypatch.setattr(worktrees_router, "create_worktree", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "T"}).json()
        response = client.post(f"/api/tasks/{task['id']}/worktrees", json={"repository_id": "nope"})
        assert response.status_code == 404
        client.delete(f"/api/tasks/{task['id']}")


def test_create_worktree_git_failure_is_a_400(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("git worktree add failed")

    monkeypatch.setattr(worktrees_router, "create_worktree", fail)
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        task = client.post("/api/tasks", json={"title": "T", "repository_ids": [repo["id"]]}).json()

        response = client.post(f"/api/tasks/{task['id']}/worktrees", json={})
        assert response.status_code == 400
        assert "failed" in response.json()["detail"]

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_delete_worktree_removes_it_from_disk_and_marks_removed(monkeypatch, tmp_path):
    monkeypatch.setattr(worktrees_router, "create_worktree", lambda *args, **kwargs: None)
    removed: dict = {}
    monkeypatch.setattr(
        worktrees_router,
        "remove_worktree",
        lambda repo_path, path: removed.update(repo_path=repo_path, path=path),
    )
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        task = client.post("/api/tasks", json={"title": "T", "repository_ids": [repo["id"]]}).json()
        worktree = client.post(f"/api/tasks/{task['id']}/worktrees", json={}).json()

        assert client.delete(f"/api/tasks/{task['id']}/worktrees/{worktree['id']}").status_code == 204
        assert removed["path"] == worktree["path"]

        listed = client.get(f"/api/tasks/{task['id']}/worktrees").json()
        row = next(item for item in listed if item["id"] == worktree["id"])
        assert row["status"] == "removed"

        assert client.delete(f"/api/tasks/{task['id']}/worktrees/nope").status_code == 404

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{repo['id']}")
