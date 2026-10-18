"""CLI commands."""

from __future__ import annotations

from cyclopts import App

from .. import runtime
from ..render import _join
from ..runtime import (
    emit,
    safe,
)

repository_app = App(name="repository", help="Register local git repositories.")
worktree_app = App(name="worktree", help="Create isolated git worktrees for tasks.")


def register(app: App) -> None:
    app.command(repository_app)
    app.command(worktree_app)


@repository_app.command(name="list")
@safe
def repository_list() -> str:
    """List repositories."""
    with runtime._client() as client:
        repos = client.list_repositories()
    return emit(repos, _join(repos, lambda r: f"{r['id']}  {r['name']}  {r['path']}"))


@repository_app.command(name="add")
@safe
def repository_add(path: str, name: str | None = None) -> str:
    """Register a local git repository by path."""
    with runtime._client() as client:
        repo = client.add_repository(path, name=name)
    return emit(repo, f"added {repo['id']}  {repo['name']}  {repo['path']}")


@repository_app.command(name="remove")
@safe
def repository_remove(repository_id: str) -> str:
    """Remove a repository (files are not touched)."""
    with runtime._client() as client:
        client.remove_repository(repository_id)
    return emit({"removed": repository_id}, f"removed {repository_id}")


@worktree_app.command(name="list")
@safe
def worktree_list(task_id: str) -> str:
    """List a task's worktrees."""
    with runtime._client() as client:
        worktrees = client.list_worktrees(task_id)
    return emit(worktrees, _join(worktrees, lambda w: f"{w['id']}  [{w['status']}] {w['branch']}  {w['path']}"))


@worktree_app.command(name="create")
@safe
def worktree_create(
    task_id: str,
    repository_id: str | None = None,
    branch: str | None = None,
    base: str | None = None,
) -> str:
    """Create a worktree for a task."""
    with runtime._client() as client:
        worktree = client.create_worktree(task_id, repository_id=repository_id, branch=branch, base=base)
    return emit(worktree, f"created worktree {worktree['id']}  {worktree['branch']}  {worktree['path']}")


@worktree_app.command(name="remove")
@safe
def worktree_remove(task_id: str, worktree_id: str) -> str:
    """Remove a worktree from disk and stop tracking it."""
    with runtime._client() as client:
        client.remove_worktree(task_id, worktree_id)
    return emit({"removed": worktree_id}, f"removed worktree {worktree_id}")
