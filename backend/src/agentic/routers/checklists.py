"""Checklist templates and the checklist items on a task.

Templates live under ``/api/checklist-templates``; the item endpoints sit under
``/api/tasks/{task_id}/checklist`` because an item always belongs to a task.
The matching and application logic lives in ``agentic.checklists``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, col, select

from ..checklists import (
    apply_task_templates,
    apply_template_to_matching_tasks,
    checklist_item_read,
    delete_template_checklist,
    item_done,
    next_position,
    rule_error,
)
from ..crud import get_or_404, get_task_or_404
from ..db import get_session
from ..events import bus
from ..models.base import utcnow
from ..models.checklists import ChecklistItem, ChecklistTemplate, ChecklistTemplateApplication
from ..schemas.checklists import (
    ChecklistApplyResult,
    ChecklistItemCreate,
    ChecklistItemRead,
    ChecklistItemUpdate,
    ChecklistTemplateCreate,
    ChecklistTemplateRead,
    ChecklistTemplateUpdate,
)

router = APIRouter(prefix="/api", tags=["checklists"])


def _normalized_items(items: list[str]) -> list[str]:
    """Trim, drop empty entries, and de-duplicate while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _validated_rules(payload_rules: list) -> list[dict]:
    rules = [rule.model_dump() if hasattr(rule, "model_dump") else dict(rule) for rule in payload_rules]
    for rule in rules:
        error = rule_error(rule)
        if error is not None:
            raise HTTPException(status_code=400, detail=error)
    return rules


def _template_read(session: Session, template: ChecklistTemplate) -> ChecklistTemplateRead:
    applied = session.exec(
        select(func.count())
        .select_from(ChecklistTemplateApplication)
        .where(ChecklistTemplateApplication.template_id == template.id)
    ).one()
    data = ChecklistTemplateRead.model_validate(template)
    data.applied_count = int(applied or 0)
    return data


@router.get("/checklist-templates", response_model=list[ChecklistTemplateRead])
def list_checklist_templates(session: Session = Depends(get_session)) -> list[ChecklistTemplateRead]:
    """List every checklist template, oldest first, with how many tasks use it."""
    templates = session.exec(select(ChecklistTemplate).order_by(col(ChecklistTemplate.created_at))).all()
    return [_template_read(session, template) for template in templates]


@router.post("/checklist-templates", response_model=ChecklistTemplateRead, status_code=201)
def create_checklist_template(
    payload: ChecklistTemplateCreate, session: Session = Depends(get_session)
) -> ChecklistTemplateRead:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    template = ChecklistTemplate(
        name=name,
        description=payload.description.strip(),
        rules=_validated_rules(payload.rules),
        items=_normalized_items(payload.items),
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    # A new template takes effect on the tasks that already match it, so the
    # user sees it without editing every task first.
    apply_template_to_matching_tasks(session, template)
    return _template_read(session, template)


@router.patch("/checklist-templates/{template_id}", response_model=ChecklistTemplateRead)
def update_checklist_template(
    template_id: str, payload: ChecklistTemplateUpdate, session: Session = Depends(get_session)
) -> ChecklistTemplateRead:
    template = get_or_404(session, ChecklistTemplate, template_id, "Checklist template not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        data["name"] = name
    if "description" in data:
        data["description"] = str(data["description"] or "").strip()
    if "rules" in data:
        data["rules"] = _validated_rules(data["rules"] or [])
    if "items" in data:
        data["items"] = _normalized_items(data["items"] or [])
    for key, value in data.items():
        setattr(template, key, value)
    template.updated_at = utcnow()
    session.add(template)
    session.commit()
    session.refresh(template)
    return _template_read(session, template)


@router.delete("/checklist-templates/{template_id}", status_code=204)
def delete_checklist_template(template_id: str, session: Session = Depends(get_session)) -> None:
    """Delete a template and the items it put on tasks."""
    template = get_or_404(session, ChecklistTemplate, template_id, "Checklist template not found")
    delete_template_checklist(session, template_id)
    session.delete(template)
    session.commit()


@router.post("/checklist-templates/{template_id}/apply", response_model=ChecklistApplyResult)
def apply_checklist_template(template_id: str, session: Session = Depends(get_session)) -> ChecklistApplyResult:
    """Add the template's missing items to every task that currently matches it."""
    template = get_or_404(session, ChecklistTemplate, template_id, "Checklist template not found")
    return ChecklistApplyResult(applied=apply_template_to_matching_tasks(session, template))


@router.post("/tasks/{task_id}/checklist", response_model=ChecklistItemRead, status_code=201)
async def add_checklist_item(
    task_id: str, payload: ChecklistItemCreate, session: Session = Depends(get_session)
) -> ChecklistItemRead:
    task = get_task_or_404(session, task_id)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Item text is required")
    position = payload.position if payload.position is not None else next_position(session, task.id)
    item = ChecklistItem(task_id=task.id, text=text, position=position)
    session.add(item)
    session.commit()
    session.refresh(item)
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "checklist_changed"})
    return checklist_item_read(session, task, item)


@router.post("/tasks/{task_id}/checklist/apply", response_model=ChecklistApplyResult)
async def apply_task_checklists(task_id: str, session: Session = Depends(get_session)) -> ChecklistApplyResult:
    """Re-run matching for this task, adding missing items from templates already applied."""
    task = get_task_or_404(session, task_id)
    applied = apply_task_templates(session, task, include_applied=True)
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "checklist_changed"})
    return ChecklistApplyResult(applied=applied)


@router.patch("/tasks/{task_id}/checklist/{item_id}", response_model=ChecklistItemRead)
async def update_checklist_item(
    task_id: str, item_id: str, payload: ChecklistItemUpdate, session: Session = Depends(get_session)
) -> ChecklistItemRead:
    task = get_task_or_404(session, task_id)
    item = get_or_404(session, ChecklistItem, item_id, "Checklist item not found")
    if item.task_id != task.id:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    data = payload.model_dump(exclude_unset=True)
    if "text" in data:
        text = str(data["text"] or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Item text is required")
        item.text = text
    if "done" in data and data["done"] is not None:
        item_done(item, bool(data["done"]))
    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "checklist_changed"})
    return checklist_item_read(session, task, item)


@router.delete("/tasks/{task_id}/checklist/{item_id}", status_code=204)
async def delete_checklist_item(task_id: str, item_id: str, session: Session = Depends(get_session)) -> None:
    task = get_task_or_404(session, task_id)
    item = get_or_404(session, ChecklistItem, item_id, "Checklist item not found")
    if item.task_id != task.id:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    session.delete(item)
    session.commit()
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "checklist_changed"})


__all__ = ["router"]
