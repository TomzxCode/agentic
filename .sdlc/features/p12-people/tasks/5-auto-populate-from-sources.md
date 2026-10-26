---
id: "5"
title: "Auto-populate people from ghx and slackx"
status: done
size: M
depends_on: [1]
completed_date: "2026-10-13"
blocker: null
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# Task 5: Auto-populate people from ghx and slackx

## Description

Extract the people named by a GitHub issue/PR payload and a Slack thread payload, upsert them into the directory, and link them to the item; link an item's people to a task when the item is linked.

## Acceptance Criteria

- [ ] FR-11: A GitHub item brings its author, assignees, and comment authors, each keyed by login.
- [ ] FR-12: A Slack item brings the thread's distinct participants, each keyed by Slack user id.
- [ ] FR-13: Linking an item to a task links the item's people to the task and records `person_added` events.
- [ ] NFR-6: A missing or failing `ghx`/`slackx` still stores the item and creates no person.
- [ ] NFR-7: The same handle is one person across items.

## Notes

`fetch_source` gains a `people` list; `fetch_github_issue` includes one.
Slack names are resolved from `slackx users list --json` with the message's `user_name` as a fallback.
