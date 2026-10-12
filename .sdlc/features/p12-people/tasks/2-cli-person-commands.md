---
id: "2"
title: "CLI person commands"
status: draft
size: S
depends_on: [1]
completed_date: null
blocker: null
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# Task 2: CLI person commands

## Description

Add a `person` command group to the `agentic` CLI and the matching client methods, so the directory and the links are scriptable.

## Acceptance Criteria

- [ ] FR-5: `agentic person list`, `person get`, `person create`, `person update`, and `person delete` drive the API.
- [ ] FR-5: `agentic person link <person> --task <task>` and `--item <item>` link a person; `person unlink` removes the link.
- [ ] FR-5: `agentic task get <task>` shows the task's people.
- [ ] Errors print `error: ... (HTTP <status>)` to stderr and exit 1.

## Notes

Follow the `tag` command group and the `_task_text` renderer for style.
`client.py` methods use `_compact` so unset fields are not sent.
