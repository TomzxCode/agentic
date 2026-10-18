"""Git helpers: remote/branch detection and worktree commands."""

import subprocess

import pytest

from agentic.services import git, shell


def test_detect_remote_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        shell,
        "_git",
        lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 0, "git@x:o/r.git\n", ""),
    )
    assert git.detect_remote_url(str(tmp_path)) == "git@x:o/r.git"

    monkeypatch.setattr(
        shell,
        "_git",
        lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 1, "", ""),
    )
    assert git.detect_remote_url(str(tmp_path)) is None


def test_detect_default_branch_prefers_origin_head(monkeypatch, tmp_path):
    monkeypatch.setattr(
        shell,
        "_git",
        lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 0, "origin/develop\n", ""),
    )
    assert git.detect_default_branch(str(tmp_path)) == "develop"


def test_detect_default_branch_falls_back_to_main_then_master(monkeypatch, tmp_path):
    def fake(args, cwd, timeout=15):
        if args[0] == "symbolic-ref":
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:3] == ["rev-parse", "--verify", "main"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:3] == ["rev-parse", "--verify", "master"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(shell, "_git", fake)
    assert git.detect_default_branch(str(tmp_path)) == "master"


def test_detect_default_branch_none_when_nothing_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(
        shell,
        "_git",
        lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 1, "", ""),
    )
    assert git.detect_default_branch(str(tmp_path)) is None


def test_create_worktree_reuses_an_existing_branch(monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(
        shell,
        "_git",
        lambda args, cwd, timeout=120: (calls.append(args), subprocess.CompletedProcess(args, 0, "", ""))[1],
    )
    git.create_worktree(str(tmp_path), "feature", str(tmp_path / "wt"))
    assert ["worktree", "add", str(tmp_path / "wt"), "feature"] in calls


def test_create_worktree_creates_a_new_branch_from_base(monkeypatch, tmp_path):
    calls: list = []

    def fake(args, cwd, timeout=120):
        calls.append(args)
        if args[:2] == ["rev-parse", "--verify"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(shell, "_git", fake)
    git.create_worktree(str(tmp_path), "new", str(tmp_path / "wt"), base="main")
    assert ["worktree", "add", "-b", "new", str(tmp_path / "wt"), "main"] in calls


def test_create_worktree_raises_on_git_failure(monkeypatch, tmp_path):
    def fake(args, cwd, timeout=120):
        if args[:2] == ["rev-parse", "--verify"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 2, "", "boom\n")

    monkeypatch.setattr(shell, "_git", fake)
    with pytest.raises(RuntimeError, match="boom"):
        git.create_worktree(str(tmp_path), "b", str(tmp_path / "wt"))


def test_remove_worktree_removes_and_prunes(monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(
        shell,
        "_git",
        lambda args, cwd, timeout=120: (calls.append(args), subprocess.CompletedProcess(args, 0, "", ""))[1],
    )
    git.remove_worktree(str(tmp_path), "/x/wt")
    assert ["worktree", "remove", "--force", "/x/wt"] in calls
    assert ["worktree", "prune"] in calls
