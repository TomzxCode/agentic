"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

from pathlib import Path

from . import shell


def detect_remote_url(repo_path: str) -> str | None:
    result = shell._git(["remote", "get-url", "origin"], cwd=repo_path, timeout=15)
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def detect_default_branch(repo_path: str) -> str | None:
    result = shell._git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_path, timeout=15)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().removeprefix("origin/")
    for candidate in ("main", "master"):
        check = shell._git(["rev-parse", "--verify", candidate], cwd=repo_path, timeout=15)
        if check.returncode == 0:
            return candidate
    return None


def create_worktree(repo_path: str, branch: str, path: str, base: str | None = None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    existing = shell._git(["rev-parse", "--verify", branch], cwd=repo_path, timeout=15)
    if existing.returncode == 0:
        result = shell._git(["worktree", "add", path, branch], cwd=repo_path)
    else:
        args = ["worktree", "add", "-b", branch, path]
        if base:
            args.append(base)
        result = shell._git(args, cwd=repo_path)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git worktree add failed")


def remove_worktree(repo_path: str, path: str) -> None:
    shell._git(["worktree", "remove", "--force", path], cwd=repo_path)
    shell._git(["worktree", "prune"], cwd=repo_path, timeout=15)
