# Product Overview

## Product

Agentic is a local-first work tracker for a developer who works alongside coding agents.
It organizes work as tasks, attaches the external sources that feed them (Slack threads, GitHub issues and pull requests, Drive docs, URLs, notes, commits, local paths), creates git worktrees per task, and runs coding agents over ACP to keep each task's summary and next steps current, so resuming work takes under a minute.
It also measures the workflow itself: an instrumented change lifecycle produces autonomy rate (the share of accepted changes with no human touch) and yield (the share that survived its observation window without a revert).
Delivery is one FastAPI + SQLModel backend with SQLite, a Vue 3 PWA designed for phones first, a scriptable HTTP CLI (`agentic`), a backend CLI (`agentic-server`), and an optional tray launcher with a global hotkey.

## Target Customer (ICP)

A single developer (the owner) who delegates coding to AI agents across several local repositories and works from both a desktop and a phone.
They run everything on their own machine, coordinate with no team, and want their work data to stay local under `~/.agentic`.

## Scope

- **In scope:**
  - Task tracking with status, priority, tags, deadlines, search, inline editing, and a timeline.
  - A focus stack with the current task on top, session timing, and parked states (waiting on a person, snoozed).
  - Source items with many-to-many task associations, source inference, and on-demand fetch.
  - People: a directory with aliases, merged duplicates, task and item links, and requester tracking.
  - Local repository registration, groups, worktrees, and a server-side directory picker.
  - ACP agent runs with a live persisted transcript, a durable queue with a worker process, model selection, and cancellation.
  - Agent-maintained context refresh (summary plus next steps) and session links.
  - GitHub issue and PR import through `ghx`; task creation from a Slack thread.
  - An inbox with PR reviewer-feedback triage (implement, decline, defer) and a review SLO flag.
  - Factory metrics over recorded changes, with metric baselines and trend direction.
  - Task graphs with executions, a dependency graph, a Gantt timeline, schedules for recurring agent work, and an on-call view.
  - A scriptable CLI covering the API, designed so agents can create and maintain content.
- **Out of scope:**
  - Multi-user access, authentication, or tenancy isolation.
  - OAuth flows, webhooks, or continuous two-way sync with external systems.
  - A hosted or cloud deployment.
  - Interactive agent permission approval (requests are auto-approved).

## Key Constraints

- Single-user and local-first; the database and worktrees live under `~/.agentic`.
- No authentication, so the app is only safe on a trusted network.
- SQLite via SQLModel; schema changes are created and migrated in place, not by a migration tool.
- Integrations are lightweight and metadata-only (`ghx` for GitHub, `slackx` for Slack).
- Agent runs execute in worker processes; a worker that dies stalls its runs until restarted.
- Requires Python 3.12+, Node 20+, pnpm, and at least one ACP harness on `PATH`.
- Every UI change must stay usable at phone widths.

## Key Stakeholders

| Stakeholder | Role | Interest |
|---|---|---|
| Sole user | Owner / developer | Track personal work, keep context current, see how much the agents do alone |
| Coding agent | Operator of a task | Consume task context and repositories, act on prompts, write summaries |
| ACP harness authors | Upstream (OpenCode, pi) | Speak ACP so the app drives any harness without app code changes |
| Skills library | Companion repo (`agents`) | Skills that file issues, run reviews, and post updates the app ingests |
