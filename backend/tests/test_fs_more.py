"""Filesystem browsing edge cases: missing paths, files, and symlinks."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic.config import settings
from agentic.main import app


@pytest.fixture
def browse_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "alpha" / ".git").mkdir(parents=True)
    (tmp_path / "file.txt").write_text("x")
    monkeypatch.setattr(settings, "fs_root", tmp_path)
    return tmp_path


def test_missing_and_non_directory_paths(browse_root: Path):
    with TestClient(app) as client:
        assert client.get("/api/fs/list", params={"path": str(browse_root / "nope")}).status_code == 404
        assert client.get("/api/fs/list", params={"path": str(browse_root / "file.txt")}).status_code == 400


def test_symlinks_are_followed_only_when_they_resolve(browse_root: Path):
    (browse_root / "link").symlink_to(browse_root / "alpha", target_is_directory=True)
    (browse_root / "broken").symlink_to(browse_root / "gone")
    with TestClient(app) as client:
        names = [entry["name"] for entry in client.get("/api/fs/list").json()["entries"]]
    assert "link" in names
    assert "broken" not in names


def test_default_path_is_the_root(browse_root: Path):
    with TestClient(app) as client:
        listing = client.get("/api/fs/list").json()
    assert listing["path"] == str(browse_root)
    assert listing["parent"] is None
