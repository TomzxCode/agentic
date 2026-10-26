---
id: "6"
title: "Merge duplicate people"
status: done
size: S
depends_on: [1, 2, 3]
completed_date: "2026-10-13"
blocker: null
session_link: null
---

# Task 6: Merge duplicate people

## Description

Add a merge that folds a source person into a target person: move the source's aliases and its task and item links to the target, drop what the target already holds, record a `person_added` event on each task that gains the target, and delete the source.
Expose it over HTTP, through the CLI, and on the person page.

## Acceptance Criteria

- [ ] FR-14: A source person can be merged into a target over HTTP; the target survives and the source is deleted.
- [ ] FR-15: The source's aliases move to the target; a shared alias is dropped, not duplicated.
- [ ] FR-16: The source's task and item links move to the target; a shared link is dropped, not duplicated.
- [ ] FR-17: Each task that gains the target records a `person_added` timeline event; getting the source afterwards returns 404.
- [ ] FR-18: `agentic person merge SOURCE --into TARGET` and the person page's merge picker drive the endpoint; the page shows the target afterwards.
- [ ] NFR-8: No duplicate link or alias survives a merge; the unique constraints hold.
- [ ] NFR-9: The merge is a confirmed, destructive action that names both people, and it fits a phone width.
- [ ] Guards: a self-merge is 400 and an unknown source or target is 404.

## Notes

`merge_people` in `routers/people.py` checks the target's links before moving each row, so `uq_person_alias`, `uq_task_person`, and `uq_item_person` are never violated.
No new table or column is needed, so `create_all` and `_ensure_columns` are untouched.
The SPA reuses `SearchSelect` for the target picker and `store.loadPeople` to refresh the directory.
