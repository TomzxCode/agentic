---
id: "4"
title: "Tests and context artifacts"
status: draft
size: S
depends_on: [1, 2, 3, 5]
completed_date: null
blocker: null
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# Task 4: Tests and context artifacts

## Description

Cover the people feature with backend, CLI, and frontend tests, and update the project context to describe the new tables and terms.

## Acceptance Criteria

- [ ] Backend tests cover create, list counts, task and item links, idempotency, timeline events, and the task/person cascades.
- [ ] CLI tests cover the person commands and the client methods.
- [ ] Frontend tests cover the People view and the task People panel.
- [ ] `architecture.md`, `schema.dbml`, `vocabulary.md`, and `project-overview.md` mention people.

## Notes

Follow `backend/tests/test_metrics.py` and `frontend/src/__tests__/panels.test.js` for style.
