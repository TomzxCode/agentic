from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic.config import settings
from agentic.main import app


@pytest.fixture
def browse_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("alpha", "beta", "notgit"):
        (tmp_path / name).mkdir()
    (tmp_path / "alpha" / ".git").mkdir()
    (tmp_path / "beta" / ".git").mkdir()
    (tmp_path / ".hidden").mkdir()
    monkeypatch.setattr(settings, "fs_root", tmp_path)
    return tmp_path


def test_lists_directories_with_git_flags(browse_root: Path):
    with TestClient(app) as client:
        data = client.get("/api/fs/list").json()
    assert data["path"] == str(browse_root)
    assert data["parent"] is None  # cannot go above the root
    names = [e["name"] for e in data["entries"]]
    assert names == ["alpha", "beta", "notgit"]  # hidden excluded, sorted
    git = {e["name"]: e["is_git"] for e in data["entries"]}
    assert git["alpha"] and git["beta"] and not git["notgit"]


def test_hidden_can_be_included(browse_root: Path):
    with TestClient(app) as client:
        names = [e["name"] for e in client.get("/api/fs/list", params={"hidden": True}).json()["entries"]]
    assert ".hidden" in names


def test_navigates_into_and_back_out(browse_root: Path):
    with TestClient(app) as client:
        listing = client.get("/api/fs/list", params={"path": str(browse_root / "alpha")}).json()
    assert listing["path"] == str(browse_root / "alpha")
    assert listing["parent"] == str(browse_root)
    assert listing["is_git"] is True


def test_refuses_outside_the_root(browse_root: Path, tmp_path_factory: pytest.TempPathFactory):
    outside = tmp_path_factory.mktemp("outside")
    with TestClient(app) as client:
        assert client.get("/api/fs/list", params={"path": str(outside)}).status_code == 403


def test_bulk_add_reports_per_path_errors(browse_root: Path):
    with TestClient(app) as client:
        result = client.post(
            "/api/repositories/bulk",
            json={"paths": [str(browse_root / "alpha"), str(browse_root / "beta"), str(browse_root / "notgit")]},
        ).json()
    assert {repo["name"] for repo in result["added"]} == {"alpha", "beta"}
    assert len(result["errors"]) == 1
    assert result["errors"][0]["path"].endswith("notgit")
