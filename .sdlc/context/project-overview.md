<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Project Overview

## Purpose

Agentic is a local-first work tracker for a single developer who works alongside coding agents.
It organizes work as **tasks**, associates the external sources that feed them (Slack threads, GitHub issues and pull requests, Google Drive docs, generic URLs, and plain notes), creates isolated git worktrees to work in, and runs coding agents to keep a current summary and next-steps list so resuming a task takes under a minute.
It solves the problem of scattered context: the threads, issues, and checkouts relevant to a piece of work live in many systems, and re-reading them to resume is slow.

## Design Principles

- **Designed with mobile in mind:** the application works on phones, not only on a desktop.
  Layouts, navigation, and controls are checked at phone widths alongside larger screens.
  The web app collapses its sidebar to an off-canvas drawer below 760px, uses touch-friendly controls, and is installable as a PWA so it can be driven from a phone.

## Key Stakeholders

| Stakeholder | Role | Interest |
|---|---|---|
| Sole user | Owner / developer | Track personal work, keep context current, drive agents from one place |
| Coding agent | Operator of a task | Consume task context and repositories, act on prompts, write summaries |
| ACP harness authors | Upstream (OpenCode, pi) | Speak ACP so the app can drive any harness without app code changes |

## Scope

**In scope:**
- Task tracking (status, priority, tags, deadlines, inline editing, search, timeline).
- Checklists: reusable templates whose rules (status, priority, waiting on, tags, people, requesters, repositories, before/after/related tasks) decide which tasks receive their items; each task's items are editable and stay visible but disabled when the template no longer matches.
- A focus stack: an ordered queue of tasks with the current one on top, per-entry session timing (execution count, duration), and soft-deleted history.
- An optional native launcher (tray icon plus global hotkey) for the stack.
- An upcoming-deadlines view on the tasks page, in-flight tasks soonest first with overdue tasks leading.
- Waiting-on and snooze deferrals: link a task to a person with an optional check-back date, or snooze it until a date, and it leaves the focus stack and returns automatically when the date passes.
- A Gantt timeline view of tasks in flight, one marker per timeline event.
- Task dependencies: before/after links between tasks that form a DAG (the API refuses cycles), drawn on a Graph page.
- Factory metrics: an instrumented change lifecycle with autonomy rate and yield read against stored baselines.
- A process view of the pipeline: task statuses mapped to stations, with flow, queue pressure, and cycle times computed from timeline events.
- Source items and many-to-many associations, with source inference and on-demand fetch.
- A resources list of every item across sources, with search, refresh, and delete.
- Tiered item refresh: Slack threads and GitHub issues/PRs re-fetched on an age-based schedule, with a per-source policy.
- GitHub issue/PR import (paste a URL or pick from a repository) via `ghx`.
- A GitHub read surface: repository pages listing each repository's issues and pull requests fresh from GitHub, and a My PRs page for the user's own open pull requests (check rollup, review decision, approvers, open threads).
- A review queue: the review reports the review skills write locally, plus a background scan of pull requests awaiting review, shown one row per PR with per-step verdicts, a merge-readiness light, and must/should/may findings.
- PR reviewer-feedback triage: the per-comment analysis files the feedback skills write, read as a queue with implement / decline / defer decisions.
- A review SLO that flags pull requests past their review deadline in the inbox.
- A review nudge SLO that offers to poke the reviewers of the user's own pull requests that nobody has reviewed yet.
- A people directory, with people linked to tasks and to items.
- An inbox of derived suggestions (reviews overdue past the SLO, unreviewed pull requests to poke, closable tasks, missing change records, leftover worktrees), recomputed on every read.
- An events feed: every task's timeline as one stream, grouped by day with a timeline chart per day.
- A time page: the web app records its own foreground visits per page and shows where the hours went, as a day timeline, page shares, and a daily trend.
- A decisions page: colleague-decision reports read from the notes tree, read-only.
- An on-call view: a Slack channel scan that prepares replies to a channel's threads.
- ACP agent runs with a live, persisted transcript and cancellation.
- Agent-maintained context refresh (summary plus next steps).
- Harness management in Settings: ACP harness configs with a marked default and an optional per-harness model, plus a warm ACP session held by the API that feeds the run panel's model picker.
- Agent sessions recorded against a task, with reopen links (OpenChamber, terminal, resume command); sessions started elsewhere can be attached by hand.
- Managed local tools: `ghx serve` and `slackx serve` processes started with the server, so GitHub and Slack items link into those tools' UIs.
- Scheduled shell tasks on cron schedules, with a recorded run history.
- Execution graphs: an editor for graph definitions and durable executions that can pause for form answers and resume.
- An operations audit log of every mutating request, with the client it came from and whether a human or an agent performed it.
- A scriptable HTTP client CLI (`agentic`) and a backend CLI (`agentic-server`).
- An installable Vue 3 PWA served by the API, designed with mobile in mind.

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
- Requires Python 3.12+, uv, Node 22.12+, and pnpm, and at least one ACP harness on `PATH`.
- Agent runs are enqueued as SAQ jobs and executed by a separate worker process (`agentic-server worker`), so a run survives an API restart; a worker must be running for runs to make progress.
- The web app is designed with mobile in mind: every UI change must stay usable and legible at phone widths, so narrow viewports are checked before a change is considered done.
