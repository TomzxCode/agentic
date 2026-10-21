"""Record changes automatically for authored, task-linked merged pull requests.

Recording a change after every merge is the one bookkeeping step the inbox could
only suggest, which left autonomy rate and yield as complete as the user's
memory. A merged pull request the viewer authored and that a task already links
is a landed change, so this module records it the way the manual "Record
change" action does: accepted, dated to the merge.

Nothing is inferred from a run or a commit; only a merge the app has already
observed (the same stored state the inbox reads) produces a record. The pass is
idempotent, so it can run after every fetch, listing sync, or link without
duplicating a change, and it silently does nothing when no GitHub login is
known (recording someone else's PR would corrupt the metrics).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import structlog
from sqlmodel import Session, select

from .crud import add_timeline
from .inbox import change_references, is_authored_by, is_merged_pr, is_pull_request
from .models.base import ChangeClass, ChangeStatus, TaskStatus, utcnow
from .models.changes import Change
from .models.items import Association, SourceItem
from .models.tasks import Task
from .settings_store import resolve_github_login

log = structlog.get_logger(__name__)

AUTO_CHANGE_NOTES = "Recorded automatically from a merged pull request."


def _parse_merged_at(value: object) -> datetime | None:
    """A PR's ``merged_at`` metadata as an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _merged_at(item: SourceItem, now: datetime) -> datetime:
    """The merge time GitHub reported, falling back to now when it is unknown."""
    return _parse_merged_at((item.metadata_json or {}).get("merged_at")) or now


def record_merged_pr_changes(
    session: Session,
    *,
    item_ids: Iterable[str] | None = None,
    viewer_login: str | None = None,
    now: datetime | None = None,
) -> list[Change]:
    """Record a change for each authored, task-linked merged PR that lacks one.

    ``item_ids`` narrows the pass to specific items; without it every stored
    GitHub item is considered. A change is created only for a pull request
    GitHub reports as merged, the viewer authored, and a non-archived task
    links. An item a change on that task already references is left alone, so
    the pass is idempotent. Returns the changes created.
    """
    now = now or utcnow()
    login = (viewer_login if viewer_login is not None else resolve_github_login(session)).strip()
    if not login:
        return []

    wanted = set(item_ids) if item_ids is not None else None
    candidates = [
        item
        for item in session.exec(select(SourceItem).where(SourceItem.source == "github")).all()
        if (wanted is None or item.id in wanted)
        and is_pull_request(item)
        and is_merged_pr(item)
        and is_authored_by(item, login)
    ]
    if not candidates:
        return []

    tasks = {task.id: task for task in session.exec(select(Task)).all()}
    task_ids_by_item: dict[str, list[str]] = {}
    for assoc in session.exec(select(Association)).all():
        task_ids_by_item.setdefault(assoc.item_id, []).append(assoc.task_id)
    changes_by_task: dict[str, list[Change]] = {}
    for change in session.exec(select(Change)).all():
        changes_by_task.setdefault(change.task_id, []).append(change)

    created: list[Change] = []
    for item in candidates:
        for task_id in task_ids_by_item.get(item.id, []):
            task = tasks.get(task_id)
            if task is None or task.status == TaskStatus.archived:
                continue
            recorded = changes_by_task.setdefault(task_id, [])
            if change_references(recorded, item):
                continue
            merged_at = _merged_at(item, now)
            title = item.title or item.url or item.id
            change = Change(
                task_id=task_id,
                title=title,
                change_class=ChangeClass.feature,
                status=ChangeStatus.accepted,
                external_ref=item.url or item.external_id or None,
                opened_at=merged_at,
                accepted_at=merged_at,
                notes=AUTO_CHANGE_NOTES,
            )
            session.add(change)
            # add_timeline commits, which persists the change with it.
            add_timeline(
                session,
                task_id,
                "change_opened",
                f"Change recorded automatically: {title}",
                {"change_id": change.id, "change_class": change.change_class.value, "auto": True},
            )
            recorded.append(change)
            created.append(change)
    if created:
        log.info("recorded changes for merged pull requests", count=len(created))
    return created


__all__ = ["AUTO_CHANGE_NOTES", "record_merged_pr_changes"]
