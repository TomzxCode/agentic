<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Project Overview

## Purpose

Agentic is a local-first work tracker for a single developer who works alongside coding agents.
It organizes work as **tasks**, associates the external sources that feed them (Slack threads, GitHub issues and pull requests, Google Drive docs, generic URLs, and plain notes), creates isolated git worktrees to work in, and runs coding agents to keep a current summary and next-steps list so resuming a task takes under a minute.
It solves the problem of scattered context: the threads, issues, and checkouts relevant to a piece of work live in many systems, and re-reading them to resume is slow.

## Key Stakeholders

| Stakeholder | Role | Interest |
|---|---|---|
| Sole user | Owner / developer | Track personal work, keep context current, drive agents from one place |
| Coding agent | Operator of a task | Consume task context and repositories, act on prompts, write summaries |
| ACP harness authors | Upstream (OpenCode, pi) | Speak ACP so the app can drive any harness without app code changes |

## Scope

**In scope:**
- Task tracking (status, priority, tags, inline editing, search, timeline).
- A Gantt timeline view of tasks in flight, one marker per timeline event.
- Source items and many-to-many associations, with source inference and on-demand fetch.
- A resources list of every item across sources, with search, refresh, and delete.
- GitHub issue/PR import (paste a URL or pick from a repository) via `ghx`.
- Local repository registration, repository groups, and a server-side directory picker.
- Git worktree creation and removal per task.
- ACP agent runs with a live, persisted transcript and cancellation.
- Agent-maintained context refresh (summary plus next steps).
- Session links (OpenChamber, terminal, resume command).
- A scriptable HTTP client CLI (`agentic`) and a backend CLI (`agentic-server`).
- An installable Vue 3 PWA served by the API.

**Out of scope:**
- Multi-user access, authentication, or tenancy isolation.
- OAuth flows, webhooks, or continuous two-way sync with external systems.
- A hosted or cloud deployment.
- Interactive agent permission approval (requests are auto-approved).

## Key Constraints

- Single-user and local-first: the default database and worktrees live under `~/.agentic`.
- No authentication; the app is only safe to expose on a trusted network.
- Persistence is SQLite via SQLModel; the schema is created and migrated in place, not by a migration tool.
- External integrations are lightweight and metadata-only; GitHub uses `ghx` and Slack uses `slackx` when those CLIs are on `PATH`.
- Requires Python 3.12+ and Node 20+, and at least one ACP harness on `PATH`.
- Agent runs are in-process; restarting the API drops in-flight runs.
