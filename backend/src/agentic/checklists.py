"""Checklist templates: matching tasks, applying items, and reading a task's list.

A template is a reusable list of items plus rules that all have to match a task.
The first time a task matches, the template's items are copied onto the task and
a ``ChecklistTemplateApplication`` row records that it happened. The items then
belong to the task: they can be checked, edited, added to, and removed without
changing the template.

Whether a template still matches is evaluated at read time, not stored. A task
that stops matching therefore keeps its items (shown disabled by the UI), and a
task that matches again shows them enabled without re-adding what was deleted.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from .dependencies import dependencies, related_ids
from .models.base import utcnow
from .models.checklists import (
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateApplication,
)
from .models.items import TaskPerson, TaskRequester
from .models.repositories import TaskRepository
from .models.tasks import Task
from .schemas.checklists import ChecklistItemRead

# The rule vocabulary. An unknown field or operator fails to match rather than
# raising, so a rule written by a newer version stays readable here.
LIST_FIELDS = ("tags", "people", "requested_by", "repositories", "before", "after", "related")
FIELD_OPERATORS: dict[str, tuple[str, ...]] = {
    "status": ("is_any", "is_not_any"),
    "priority": ("is_any", "is_not_any"),
    "waiting_on": ("is_any", "is_not_any", "is_set", "is_not_set"),
    **{field: ("has_any", "has_all", "has_none") for field in LIST_FIELDS},
}


def rule_error(rule: dict[str, Any]) -> str | None:
    """Why a rule cannot be used, or None when it is valid."""
    field = str(rule.get("field") or "")
    op = str(rule.get("op") or "")
    operators = FIELD_OPERATORS.get(field)
    if operators is None:
        return f"Unknown rule field: {field or '(empty)'}"
    if op not in operators:
        return f"Unknown operator for {field}: {op or '(empty)'}"
    if op not in ("is_set", "is_not_set") and not rule.get("values"):
        return f"Rule for {field} needs at least one value"
    return None


def _task_status(task: Task) -> str:
    return str(getattr(task.status, "value", task.status))


def task_context(session: Session, task: Task) -> dict[str, Any]:
    """The task properties a rule can match, gathered in one pass."""
    before_ids, after_ids = dependencies(session, task.id)
    return {
        "status": _task_status(task),
        "priority": str(task.priority),
        "waiting_on": task.waiting_on_person_id,
        "tags": {str(tag) for tag in (task.tags or [])},
        "people": {
            row.person_id for row in session.exec(select(TaskPerson).where(TaskPerson.task_id == task.id)).all()
        },
        "requested_by": {
            row.person_id for row in session.exec(select(TaskRequester).where(TaskRequester.task_id == task.id)).all()
        },
        "repositories": {
            row.repository_id
            for row in session.exec(select(TaskRepository).where(TaskRepository.task_id == task.id)).all()
        },
        "before": set(before_ids),
        "after": set(after_ids),
        "related": set(related_ids(session, task.id)),
    }


def _rule_matches(context: dict[str, Any], rule: dict[str, Any]) -> bool:
    field = str(rule.get("field") or "")
    op = str(rule.get("op") or "")
    values = {str(value) for value in (rule.get("values") or [])}
    if op not in FIELD_OPERATORS.get(field, ()):
        return False
    if field in LIST_FIELDS:
        actual = context.get(field) or set()
        if op == "has_any":
            return bool(actual & values)
        if op == "has_all":
            return bool(values) and values <= actual
        return not (actual & values)  # has_none
    if field == "waiting_on":
        if op == "is_set":
            return bool(context["waiting_on"])
        if op == "is_not_set":
            return not context["waiting_on"]
    actual = str(context.get(field) or "")
    if op == "is_any":
        return bool(values) and actual in values
    return actual not in values  # is_not_any


def template_matches(context: dict[str, Any], template: ChecklistTemplate) -> bool:
    """True when every rule matches. A template with no rules matches nothing."""
    rules = template.rules or []
    return bool(rules) and all(_rule_matches(context, rule) for rule in rules)


def _application_exists(session: Session, task_id: str, template_id: str) -> bool:
    return (
        session.exec(
            select(ChecklistTemplateApplication).where(
                ChecklistTemplateApplication.task_id == task_id,
                ChecklistTemplateApplication.template_id == template_id,
            )
        ).first()
        is not None
    )


def next_position(session: Session, task_id: str) -> int:
    positions = [
        item.position for item in session.exec(select(ChecklistItem).where(ChecklistItem.task_id == task_id)).all()
    ]
    return (max(positions) + 1) if positions else 0


def _add_missing_items(session: Session, task_id: str, template: ChecklistTemplate) -> int:
    """Copy the template's items the task does not already hold. Returns the count added."""
    existing = {
        item.text.strip().casefold()
        for item in session.exec(
            select(ChecklistItem).where(
                ChecklistItem.task_id == task_id,
                ChecklistItem.template_id == template.id,
            )
        ).all()
    }
    position = next_position(session, task_id)
    added = 0
    for raw in template.items or []:
        text = str(raw).strip()
        if not text or text.casefold() in existing:
            continue
        session.add(ChecklistItem(task_id=task_id, template_id=template.id, text=text, position=position))
        existing.add(text.casefold())
        position += 1
        added += 1
    return added


def _record_application(session: Session, task_id: str, template_id: str) -> None:
    if not _application_exists(session, task_id, template_id):
        session.add(ChecklistTemplateApplication(task_id=task_id, template_id=template_id))


def apply_task_templates(
    session: Session,
    task: Task,
    *,
    template: ChecklistTemplate | None = None,
    include_applied: bool = False,
) -> int:
    """Apply every matching template the task has not had yet.

    ``template`` limits the pass to one template; ``include_applied`` adds any
    missing items to a template that was applied before (the explicit "apply
    now" action). Returns the number of templates that changed the task.
    """
    context = task_context(session, task)
    templates = [template] if template is not None else list(session.exec(select(ChecklistTemplate)).all())
    changed = 0
    for candidate in templates:
        if not include_applied and _application_exists(session, task.id, candidate.id):
            continue
        if not template_matches(context, candidate):
            continue
        _add_missing_items(session, task.id, candidate)
        _record_application(session, task.id, candidate.id)
        changed += 1
    if changed:
        session.commit()
    return changed


def apply_template_to_matching_tasks(session: Session, template: ChecklistTemplate) -> int:
    """Add a template's missing items to every currently matching task."""
    changed = 0
    for task in session.exec(select(Task)).all():
        if not template_matches(task_context(session, task), template):
            continue
        added = _add_missing_items(session, task.id, template)
        _record_application(session, task.id, template.id)
        if added:
            changed += 1
    session.commit()
    return changed


def checklist_items(session: Session, task: Task) -> list[ChecklistItemRead]:
    """A task's checklist in display order, with each item's current applicability."""
    rows = list(
        session.exec(
            select(ChecklistItem)
            .where(ChecklistItem.task_id == task.id)
            .order_by(col(ChecklistItem.position), col(ChecklistItem.created_at))
        ).all()
    )
    if not rows:
        return []
    template_ids = {row.template_id for row in rows if row.template_id}
    templates = {
        template.id: template
        for template in (session.get(ChecklistTemplate, template_id) for template_id in template_ids)
        if template is not None
    }
    context = task_context(session, task) if template_ids else {}
    applicability = {template_id: template_matches(context, template) for template_id, template in templates.items()}
    return [
        ChecklistItemRead(
            id=row.id,
            task_id=row.task_id,
            template_id=row.template_id,
            template_name=templates[row.template_id].name if row.template_id in templates else None,
            text=row.text,
            position=row.position,
            done=row.done,
            done_at=row.done_at,
            # A derived item follows its template; a manual item always applies.
            applicable=applicability.get(row.template_id, True) if row.template_id else True,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def checklist_item_read(session: Session, task: Task, item: ChecklistItem) -> ChecklistItemRead:
    """One item in the same shape as the task detail's checklist."""
    for read in checklist_items(session, task):
        if read.id == item.id:
            return read
    # The item was just created and is not in the list yet; fall back to a read
    # without the template lookup.
    template = session.get(ChecklistTemplate, item.template_id) if item.template_id else None
    context = task_context(session, task)
    return ChecklistItemRead(
        id=item.id,
        task_id=item.task_id,
        template_id=item.template_id,
        template_name=template.name if template is not None else None,
        text=item.text,
        position=item.position,
        done=item.done,
        done_at=item.done_at,
        applicable=template_matches(context, template) if template is not None else True,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def item_done(item: ChecklistItem, done: bool) -> None:
    """Set an item's done state and its completion time together."""
    item.done = done
    item.done_at = utcnow() if done else None
    item.updated_at = utcnow()


def delete_task_checklist(session: Session, task_id: str) -> None:
    """Drop every checklist row a task owns (and the templates it applied)."""
    session.exec(sa_delete(ChecklistItem).where(col(ChecklistItem.task_id) == task_id))
    session.exec(sa_delete(ChecklistTemplateApplication).where(col(ChecklistTemplateApplication.task_id) == task_id))


def delete_template_checklist(session: Session, template_id: str) -> None:
    """Drop a template's items and application records before the template row."""
    session.exec(sa_delete(ChecklistItem).where(col(ChecklistItem.template_id) == template_id))
    session.exec(
        sa_delete(ChecklistTemplateApplication).where(col(ChecklistTemplateApplication.template_id) == template_id)
    )


__all__ = [
    "FIELD_OPERATORS",
    "LIST_FIELDS",
    "apply_task_templates",
    "apply_template_to_matching_tasks",
    "checklist_item_read",
    "checklist_items",
    "delete_task_checklist",
    "delete_template_checklist",
    "item_done",
    "next_position",
    "rule_error",
    "task_context",
    "template_matches",
]
