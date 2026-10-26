---
id: "1"
title: "Backend people model and API"
status: done
size: M
depends_on: []
completed_date: "2026-10-13"
blocker: null
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# Task 1: Backend people model and API

## Description

Add the `Person`, `TaskPerson`, and `ItemPerson` tables, the person schemas, and a `people` router that owns the directory and the task-side and item-side links.
Expose `people` on `TaskDetail` and `person_ids` on `ItemRead`, and cascade the links when a task or an item is deleted.

## Acceptance Criteria

- [ ] FR-1: A person is created with a name and optional email, handle, and notes; a blank name is rejected with 400.
- [ ] FR-2: A person can be linked to and unlinked from a task; the task detail lists the task's people.
- [ ] FR-3: A person can be linked to and unlinked from an item; the item lists `person_ids`.
- [ ] FR-4: `GET /api/people` returns each person with `task_count` and `item_count`.
- [ ] FR-9: A task link writes a `person_added` event and an unlink writes a `person_removed` event.
- [ ] FR-10: Deleting a person removes their links; deleting a task or an item removes its people links.
- [ ] NFR-1: The links are unique rows (`uq_task_person`, `uq_item_person`); a fresh database gets all three tables.
- [ ] NFR-4: Linking an already-linked person returns the existing association and adds no row.

## Notes

Mirror `TaskRepository` (join table) and `_link_item` (idempotent link) in `routers/tasks.py`.
Use explicit ordered `sa_delete` calls, not ORM cascade ordering.
