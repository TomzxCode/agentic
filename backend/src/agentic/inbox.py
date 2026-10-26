"""Inbox: suggestions of things to do, derived from the current state.

The inbox stores nothing. Every suggestion is recomputed from the tasks, the
items they link, the changes recorded against them, their worktrees, the pull
requests the review scan found awaiting the user's review, and the user's own
open pull requests that nobody has reviewed yet, so acting on one changes that
state and the suggestion disappears on the next read.

Each function here is pure and database-free, taking already-loaded rows, so the
rules can be tested in isolation the way ``metrics.py`` is.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from .models.base import TaskStatus, WorktreeStatus
from .models.changes import Change
from .models.items import SourceItem
from .models.repositories import Worktree
from .models.reviews import ReviewRequest, ReviewScanSource
from .models.tasks import Task
from .services.parsing import parse_github

# Suggestion kinds. The rank drives the display order, so a review that is past
# its SLO leads, then the user's own pull request waiting for anyone's review,
# starting with the ones whose requested reviewers can be poked and then the
# ones with no reviewer asked at all, then a finished task is offered for
# closing before its bookkeeping (a change record) or its cleanup (a leftover
# worktree).
REVIEW_PR_PAST_SLO = "review_pr_past_slo"
POKE_PR_NO_REVIEWS = "poke_pr_no_reviews"
FIND_PR_REVIEWER = "find_pr_reviewer"
CLOSE_TASK_FINISHED_ITEMS = "close_task_finished_items"
RECORD_CHANGE_MERGED_PR = "record_change_merged_pr"
REMOVE_WORKTREE_DONE_TASK = "remove_worktree_done_task"

KIND_RANK = {
    REVIEW_PR_PAST_SLO: 0,
    POKE_PR_NO_REVIEWS: 1,
    FIND_PR_REVIEWER: 2,
    CLOSE_TASK_FINISHED_ITEMS: 3,
    RECORD_CHANGE_MERGED_PR: 4,
    REMOVE_WORKTREE_DONE_TASK: 5,
}

# A task is closed when its status leaves it out of the in-flight set.
CLOSED_STATUSES = (TaskStatus.done, TaskStatus.archived)

_NUMBER_RE = re.compile(r"#(\d+)$")
_ITEM_REF_RE = re.compile(r"^(?P<owner>[^/\s]+)/(?P<repo>[^#\s]+)#\d+$")


def is_pull_request(item: SourceItem) -> bool:
    """True when the item is a GitHub pull request, by its URL or stored kind."""
    parsed = parse_github(item.url or "")
    if parsed is not None:
        return parsed["kind"] == "pull_request"
    return str(item.kind or "").lower() in ("pull_request", "pr", "pull")


def is_issue(item: SourceItem) -> bool:
    """True when the item is a GitHub issue, by its URL or stored kind."""
    parsed = parse_github(item.url or "")
    if parsed is not None:
        return parsed["kind"] == "issue"
    return str(item.kind or "").lower() == "issue"


def is_github_item(item: SourceItem) -> bool:
    """True when the item is a GitHub issue or pull request."""
    return is_pull_request(item) or is_issue(item)


def is_merged_pr(item: SourceItem) -> bool:
    """True when the item is a pull request GitHub reports as merged."""
    if not is_pull_request(item):
        return False
    return str((item.metadata_json or {}).get("state") or "").upper() == "MERGED"


def is_finished_item(item: SourceItem) -> bool:
    """True when GitHub shows the item as wrapped up: a closed issue or a closed or merged PR.

    A pull request closed without being merged counts, since GitHub reports it
    as closed; the task is still offered for closing, and you decide.
    """
    if is_github_item(item):
        return str((item.metadata_json or {}).get("state") or "").upper() in ("CLOSED", "MERGED")
    return False


def is_authored_by(item: SourceItem, login: str) -> bool:
    """True when the item's stored GitHub author matches ``login`` (case-insensitive)."""
    author = str((item.metadata_json or {}).get("author") or "").strip()
    return bool(author) and author.lower() == login.strip().lower()


def _item_number(item: SourceItem) -> str | None:
    """The item's GitHub number, from its URL or its stored external id."""
    parsed = parse_github(item.url or "")
    number = parsed["number"] if parsed is not None else None
    if number is None:
        match = _NUMBER_RE.search(item.external_id or "")
        number = match.group(1) if match else None
    return number


def _item_repository(item: SourceItem) -> str | None:
    """The owner/repository the item belongs to, from its URL or external id."""
    parsed = parse_github(item.url or "")
    if parsed is not None:
        return f"{parsed['owner']}/{parsed['repo']}"
    match = _ITEM_REF_RE.match(item.external_id or "")
    if match:
        return f"{match.group('owner')}/{match.group('repo')}"
    return None


def _pr_label(item: SourceItem) -> str:
    """A short way to name a PR: its number and repository when known, else its title."""
    number = _item_number(item)
    if not number:
        return item.title or "The pull request"
    repository = _item_repository(item)
    return f"PR {repository}#{number}" if repository else f"PR #{number}"


def _issue_label(item: SourceItem) -> str:
    """A short way to name an issue: its number when known, else its title."""
    number = _item_number(item)
    return f"Issue #{number}" if number else (item.title or "The issue")


def change_references(changes: Sequence[Change], item: SourceItem) -> bool:
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


def _close_reason(items: Sequence[SourceItem]) -> str:
    """Why the task is offered for closing: the one item, or that all of them are done."""
    if len(items) == 1:
        item = items[0]
        if is_pull_request(item):
            return f"{_pr_label(item)} is merged." if is_merged_pr(item) else f"{_pr_label(item)} is closed."
        return f"{_issue_label(item)} is closed."
    return f"All {len(items)} linked issues and pull requests are closed or merged."


def _close_suggestion(task: Task, items: Sequence[SourceItem]) -> dict[str, Any]:
    return _suggestion(
        task,
        CLOSE_TASK_FINISHED_ITEMS,
        _close_reason(items),
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


def _as_utc(value: datetime) -> datetime:
    """A stored timestamp as an aware UTC datetime (SQLite drops the zone)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _format_duration(value: timedelta) -> str:
    """A duration as the compact text the inbox reason reads, e.g. ``1d 4h``."""
    seconds = max(int(value.total_seconds()), 0)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m" if minutes else "less than a minute"


def _review_suggestion(request: ReviewRequest, waited: timedelta, slo: timedelta) -> dict[str, Any]:
    label = f"PR {request.repository}#{request.number}"
    url = request.url or f"https://github.com/{request.repository}/pull/{request.number}"
    return {
        "id": f"{REVIEW_PR_PAST_SLO}:{request.repository.lower()}:{request.number}",
        "kind": REVIEW_PR_PAST_SLO,
        "reason": f"Has awaited your review for {_format_duration(waited)}; the SLO is {_format_duration(slo)}.",
        "task_id": None,
        "task_title": "",
        "task_status": "",
        "repository": request.repository,
        "number": request.number,
        "title": request.title or label,
        "url": url,
        "actions": [
            {
                "id": f"open:{request.repository.lower()}:{request.number}",
                "kind": "open_url",
                "label": "Review PR",
                "url": url,
            }
        ],
    }


def build_review_suggestions(
    requests: Sequence[ReviewRequest],
    slo: timedelta | None,
    now: datetime,
) -> list[dict[str, Any]]:
    """Pull requests that have awaited the user's review past its SLO.

    Only a review the scan found requested from the user counts: a pull request
    they already reviewed is not waiting on them, and one that is a draft or no
    longer open is not ready. The wait runs from ``first_seen_at``, the moment
    the scan first saw the pull request awaiting a review, so a pull request the
    app has just found is not immediately overdue. With no SLO configured, every
    pull request is left alone.
    """
    if slo is None:
        return []
    reference = _as_utc(now)
    suggestions: list[dict[str, Any]] = []
    for request in requests:
        if request.source != ReviewScanSource.requested.value:
            continue
        if request.draft or str(request.state or "").upper() not in ("", "OPEN"):
            continue
        waited = reference - _as_utc(request.first_seen_at)
        if waited <= slo:
            continue
        suggestions.append(_review_suggestion(request, waited, slo))
    return suggestions


def _parse_utc_text(value: Any) -> datetime | None:
    """An ISO timestamp string (GitHub's ``...Z`` form included) as aware UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _unreviewed_suggestion(pull: dict[str, Any], waited: timedelta, threshold: timedelta) -> dict[str, Any]:
    """One of the user's own unreviewed pull requests, as an inbox suggestion.

    A pull request with requested reviewers is offered under ``poke_pr_no_reviews``:
    the reviewers ride on the suggestion so the row can list them with their own
    poke actions. One with no reviewer requested has nobody to poke, so it is
    offered under ``find_pr_reviewer`` instead, with only the PR page to open.
    """
    repository = str(pull.get("repository") or "")
    number = int(pull.get("number") or 0)
    url = str(pull.get("url") or "") or f"https://github.com/{repository}/pull/{number}"
    title = str(pull.get("title") or "") or f"{repository}#{number}"
    reason = f"No reviews after {_format_duration(waited)}; the nudge threshold is {_format_duration(threshold)}."
    reviewers = [str(name) for name in (pull.get("requested_reviewers") or [])]
    kind = POKE_PR_NO_REVIEWS if reviewers else FIND_PR_REVIEWER
    if not reviewers:
        reason += " No reviewer is requested."
    return {
        "id": f"{kind}:{repository.lower()}:{number}",
        "kind": kind,
        "reason": reason,
        "task_id": None,
        "task_title": "",
        "task_status": "",
        "repository": repository,
        "number": number,
        "title": title,
        "url": url,
        "reviewers": reviewers,
        "actions": [
            {
                # The app's own PR page, not GitHub: the inbox row should keep
                # you in the app, and the page links out to GitHub where needed.
                "id": f"open:{repository.lower()}:{number}",
                "kind": "open_pr",
                "label": "Open PR",
                "repository": repository,
                "number": number,
                "title": title,
            }
        ],
    }


def build_poke_suggestions(
    pulls: Sequence[dict[str, Any]],
    threshold: timedelta | None,
    now: datetime,
) -> list[dict[str, Any]]:
    """The user's own pull requests that nobody has reviewed, past the threshold.

    ``pulls`` is the My PRs read (one dict per open pull request the configured
    GitHub login authored). A pull request counts while nobody but its author
    has submitted a review (a comment review counts as a review; the author's
    own comments do not) and it is not a draft, since a draft is not asking for
    reviews yet. The wait runs from when GitHub says the pull request was
    opened, which is exact here: a pull request without reviews has never had
    one. With no threshold configured, every pull request is left alone.
    """
    if threshold is None:
        return []
    reference = _as_utc(now)
    suggestions: list[dict[str, Any]] = []
    for pull in pulls:
        if pull.get("draft") or pull.get("reviewed"):
            continue
        opened = _parse_utc_text(pull.get("created_at"))
        if opened is None:
            continue
        waited = reference - _as_utc(opened)
        if waited <= threshold:
            continue
        suggestions.append(_unreviewed_suggestion(pull, waited, threshold))
    return suggestions


def build_suggestions(
    tasks: Sequence[Task],
    items_by_id: dict[str, SourceItem],
    task_item_ids: dict[str, list[str]],
    task_worktrees: dict[str, list[Worktree]],
    task_changes: dict[str, list[Change]],
    viewer_login: str | None = None,
) -> list[dict[str, Any]]:
    """Turn the current rows into an ordered list of actionable suggestions.

    ``tasks`` is expected newest-first; the stable sort by kind rank keeps that
    order within each kind. Rules:

    - A task that links at least one GitHub issue or pull request, and every one
      of them is wrapped up (closed, or merged for a pull request), is offered
      for closing. A task with no linked GitHub issue or PR is left alone.
    - A merged PR with no change recorded against it is offered for recording,
      unless the task is archived. Only PRs authored by ``viewer_login`` are
      offered (a PR someone else wrote is not the viewer's change to record);
      with no login known, the author is not filtered.
    - A closed task (done or archived) with an active worktree is offered for
      pruning.
    """
    suggestions: list[dict[str, Any]] = []
    for task in tasks:
        items = [items_by_id[item_id] for item_id in task_item_ids.get(task.id, []) if item_id in items_by_id]
        pulls = [item for item in items if is_pull_request(item)]
        merged = [item for item in pulls if is_merged_pr(item)]
        links = [item for item in items if is_github_item(item)]
        changes = task_changes.get(task.id, [])
        closed = task.status in CLOSED_STATUSES

        if not closed and links and all(is_finished_item(item) for item in links):
            suggestions.append(_close_suggestion(task, links))

        if task.status != TaskStatus.archived:
            for item in merged:
                if viewer_login and not is_authored_by(item, viewer_login):
                    continue
                if not change_references(changes, item):
                    suggestions.append(_record_change_suggestion(task, item))

        if closed:
            for worktree in task_worktrees.get(task.id, []):
                if worktree.status == WorktreeStatus.active:
                    suggestions.append(_remove_worktree_suggestion(task, worktree))

    suggestions.sort(key=lambda suggestion: KIND_RANK.get(suggestion["kind"], 99))
    return suggestions


__all__ = [
    "CLOSE_TASK_FINISHED_ITEMS",
    "FIND_PR_REVIEWER",
    "KIND_RANK",
    "POKE_PR_NO_REVIEWS",
    "RECORD_CHANGE_MERGED_PR",
    "REMOVE_WORKTREE_DONE_TASK",
    "REVIEW_PR_PAST_SLO",
    "build_poke_suggestions",
    "build_review_suggestions",
    "build_suggestions",
    "change_references",
    "is_authored_by",
    "is_finished_item",
    "is_github_item",
    "is_issue",
    "is_merged_pr",
    "is_pull_request",
]
