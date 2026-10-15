"""Inbox: suggestions of things to do, derived from the current state.

The inbox stores nothing. Every suggestion is recomputed from the tasks, the
items they link, the changes recorded against them, and their worktrees, so
acting on one changes that state and the suggestion disappears on the next read.

Each function here is pure and database-free, taking already-loaded rows, so the
rules can be tested in isolation the way ``metrics.py`` is.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .models import Change, SourceItem, Task, TaskStatus, Worktree, WorktreeStatus
from .services import parse_github

# Suggestion kinds. The rank drives the display order, so a finished task is
# offered for closing before its bookkeeping (a change record) or its cleanup
# (a leftover worktree).
CLOSE_TASK_MERGED_PR = "close_task_merged_pr"
RECORD_CHANGE_MERGED_PR = "record_change_merged_pr"
REMOVE_WORKTREE_DONE_TASK = "remove_worktree_done_task"

KIND_RANK = {
    CLOSE_TASK_MERGED_PR: 0,
    RECORD_CHANGE_MERGED_PR: 1,
    REMOVE_WORKTREE_DONE_TASK: 2,
}

# A task is closed when its status leaves it out of the in-flight set.
CLOSED_STATUSES = (TaskStatus.done, TaskStatus.archived)

_PR_NUMBER_RE = re.compile(r"#(\d+)$")


def is_pull_request(item: SourceItem) -> bool:
    """True when the item is a GitHub pull request, by its URL or stored kind."""
    parsed = parse_github(item.url or "")
    if parsed is not None:
        return parsed["kind"] == "pull_request"
    return str(item.kind or "").lower() in ("pull_request", "pr", "pull")


def is_merged_pr(item: SourceItem) -> bool:
    """True when the item is a pull request GitHub reports as merged."""
    if not is_pull_request(item):
        return False
    return str((item.metadata_json or {}).get("state") or "").upper() == "MERGED"


def _pr_label(item: SourceItem) -> str:
    """A short way to name a PR: its number when known, else its title."""
    parsed = parse_github(item.url or "")
    number = parsed["number"] if parsed is not None else None
    if number is None:
        match = _PR_NUMBER_RE.search(item.external_id or "")
        number = match.group(1) if match else None
    return f"PR #{number}" if number else (item.title or "The pull request")


def _change_references(changes: Sequence[Change], item: SourceItem) -> bool:
    """True when any change already names the item via its external ref."""
    refs = {value.strip() for value in (item.url, item.external_id) if value}
    return any((change.external_ref or "").strip() in refs for change in changes)


def _suggestion(task: Task, kind: str, reason: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": f"{kind}:{task.id}:{actions[0]['id']}",
        "kind": kind,
        "reason": reason,
        "task_id": task.id,
        "task_title": task.title,
        "task_status": task.status.value,
        "actions": actions,
    }


def _close_suggestion(task: Task, item: SourceItem) -> dict[str, Any]:
    return _suggestion(
        task,
        CLOSE_TASK_MERGED_PR,
        f"{_pr_label(item)} is merged.",
        [
            {
                "id": "close",
                "kind": "set_task_status",
                "label": "Close task",
                "task_id": task.id,
                "status": TaskStatus.done.value,
            }
        ],
    )


def _record_change_suggestion(task: Task, item: SourceItem) -> dict[str, Any]:
    return _suggestion(
        task,
        RECORD_CHANGE_MERGED_PR,
        f"{_pr_label(item)} is merged and has no change recorded.",
        [
            {
                "id": f"record:{item.id}",
                "kind": "create_change",
                "label": "Record change",
                "task_id": task.id,
                "item_id": item.id,
            }
        ],
    )


def _remove_worktree_suggestion(task: Task, worktree: Worktree) -> dict[str, Any]:
    return _suggestion(
        task,
        REMOVE_WORKTREE_DONE_TASK,
        f"Worktree {worktree.branch} is still checked out.",
        [
            {
                "id": f"prune:{worktree.id}",
                "kind": "remove_worktree",
                "label": "Remove worktree",
                "task_id": task.id,
                "worktree_id": worktree.id,
            }
        ],
    )


def build_suggestions(
    tasks: Sequence[Task],
    items_by_id: dict[str, SourceItem],
    task_item_ids: dict[str, list[str]],
    task_worktrees: dict[str, list[Worktree]],
    task_changes: dict[str, list[Change]],
) -> list[dict[str, Any]]:
    """Turn the current rows into an ordered list of actionable suggestions.

    ``tasks`` is expected newest-first; the stable sort by kind rank keeps that
    order within each kind. Rules:

    - A task with exactly one linked pull request, and that PR is merged, is
      offered for closing.
    - A merged PR with no change recorded against it is offered for recording,
      unless the task is archived.
    - A closed task (done or archived) with an active worktree is offered for
      pruning.
    """
    suggestions: list[dict[str, Any]] = []
    for task in tasks:
        items = [items_by_id[item_id] for item_id in task_item_ids.get(task.id, []) if item_id in items_by_id]
        pulls = [item for item in items if is_pull_request(item)]
        merged = [item for item in pulls if is_merged_pr(item)]
        changes = task_changes.get(task.id, [])
        closed = task.status in CLOSED_STATUSES

        if not closed and len(pulls) == 1 and merged:
            suggestions.append(_close_suggestion(task, pulls[0]))

        if task.status != TaskStatus.archived:
            for item in merged:
                if not _change_references(changes, item):
                    suggestions.append(_record_change_suggestion(task, item))

        if closed:
            for worktree in task_worktrees.get(task.id, []):
                if worktree.status == WorktreeStatus.active:
                    suggestions.append(_remove_worktree_suggestion(task, worktree))

    suggestions.sort(key=lambda suggestion: KIND_RANK.get(suggestion["kind"], 99))
    return suggestions


__all__ = [
    "CLOSE_TASK_MERGED_PR",
    "KIND_RANK",
    "RECORD_CHANGE_MERGED_PR",
    "REMOVE_WORKTREE_DONE_TASK",
    "build_suggestions",
    "is_merged_pr",
    "is_pull_request",
]
