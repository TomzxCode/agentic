"""Repository endpoints: validation, metadata detection, and cascading delete."""

import subprocess

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.routers import repositories as repositories_router
from agentic.routers import worktrees as worktrees_router


def _git_dir(tmp_path, name: str):
    path = tmp_path / name
    (path / ".git").mkdir(parents=True)
    return path


def _git(path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)


def _listed(client, repository_id: str) -> dict:
    """The repository's row in the listing, which syncs it with its checkout."""
    return next(row for row in client.get("/api/repositories").json() if row["id"] == repository_id)


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
        assert repo["name"] == "o/r"
        client.delete(f"/api/repositories/{repo['id']}")


def test_listing_adopts_a_changed_origin(monkeypatch, tmp_path):
    monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: "git@github.com:o/r.git")
    with TestClient(app) as client:
        repo = client.post("/api/repositories", json={"path": str(_git_dir(tmp_path, "repo"))}).json()
        assert repo["name"] == "o/r"

        # The remote was retargeted after registration: both the URL and the
        # name derived from it follow on the next listing.
        monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: "git@github.com:new/r2.git")
        row = _listed(client, repo["id"])
        assert row["remote_url"] == "git@github.com:new/r2.git"
        assert row["name"] == "new/r2"
        client.delete(f"/api/repositories/{repo['id']}")


def test_listing_names_a_repository_once_its_origin_appears(monkeypatch, tmp_path):
    monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: None)
    with TestClient(app) as client:
        repo = client.post("/api/repositories", json={"path": str(_git_dir(tmp_path, "repo"))}).json()
        assert repo["name"] == "repo"
        assert repo["remote_url"] is None

        monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: "https://github.com/acme/api")
        row = _listed(client, repo["id"])
        assert row["remote_url"] == "https://github.com/acme/api"
        assert row["name"] == "acme/api"
        client.delete(f"/api/repositories/{repo['id']}")


def test_listing_keeps_a_hand_set_name_when_the_origin_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: "git@github.com:o/r.git")
    with TestClient(app) as client:
        repo = client.post(
            "/api/repositories",
            json={"path": str(_git_dir(tmp_path, "repo")), "name": "Custom"},
        ).json()

        monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: "git@github.com:new/r2.git")
        row = _listed(client, repo["id"])
        assert row["remote_url"] == "git@github.com:new/r2.git"
        assert row["name"] == "Custom"
        client.delete(f"/api/repositories/{repo['id']}")


def test_listing_repairs_a_folder_name_when_the_remote_is_github(monkeypatch, tmp_path):
    monkeypatch.setattr(repositories_router, "detect_remote_url", lambda path: "git@github.com:o/r.git")
    with TestClient(app) as client:
        repo = client.post(
            "/api/repositories",
            json={"path": str(_git_dir(tmp_path, "repo")), "name": "repo", "remote_url": "git@github.com:o/r.git"},
        ).json()
        assert repo["name"] == "repo"

        row = _listed(client, repo["id"])
        assert row["name"] == "o/r"
        client.delete(f"/api/repositories/{repo['id']}")


def test_listing_ignores_a_checkout_that_was_removed(monkeypatch, tmp_path):
    with TestClient(app) as client:
        repo_path = _git_dir(tmp_path, "repo")
        repo = client.post("/api/repositories", json={"path": str(repo_path)}).json()
        repo_path.rename(tmp_path / "gone")

        row = _listed(client, repo["id"])
        assert row["remote_url"] is None
        assert row["name"] == "repo"
        client.delete(f"/api/repositories/{repo['id']}")


def test_listing_follows_a_real_origin_change(tmp_path):
    repo_path = tmp_path / "checkout"
    repo_path.mkdir()
    _git(repo_path, "init", "-q")
    _git(repo_path, "remote", "add", "origin", "git@github.com:o/r.git")

    with TestClient(app) as client:
        repo = client.post("/api/repositories", json={"path": str(repo_path)}).json()
        assert repo["name"] == "o/r"

        _git(repo_path, "remote", "set-url", "origin", "git@github.com:new/r2.git")
        row = _listed(client, repo["id"])
        assert row["remote_url"] == "git@github.com:new/r2.git"
        assert row["name"] == "new/r2"
        client.delete(f"/api/repositories/{repo['id']}")


def test_associating_github_item_links_its_repository(tmp_path):
    with TestClient(app) as client:
        repo = client.post(
            "/api/repositories",
            json={"path": str(_git_dir(tmp_path, "repo")), "remote_url": "git@github.com:o/r.git"},
        ).json()
        task = client.post("/api/tasks", json={"title": "T"}).json()

        client.post(
            f"/api/tasks/{task['id']}/items",
            json={"item": {"url": "https://github.com/o/r/issues/5", "fetch": False}},
        )
        assert client.get(f"/api/tasks/{task['id']}").json()["repository_ids"] == [repo["id"]]

        client.delete(f"/api/tasks/{task['id']}")
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
