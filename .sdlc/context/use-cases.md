<!-- session_link: omitted -->
# Use Cases

<!--
This file records why actors use the project, so requirements, specifications,
and prioritization can reason about the goals behind a change. An entry is a
reason an actor has for reaching for the project, not an operation the project
exposes: "read a conversation offline" is a use case, "run the cache status
command" is not. Each entry names the actor, the goal, and how the project
serves it today. Keep IDs stable: reuse an existing UC-N for the same goal, and
only add a new one for a genuinely new goal. Put not-yet-built goals under
"Wanted", each with a signal (an issue, feature, or roadmap item). Record
deliberate non-goals under "Out of scope".
-->

## Supported

| ID | Use case | Actor | Description |
|---|---|---|---|
| UC-1 | Resume a task quickly | Sole user | Each task page holds the agent-maintained summary and next steps, its associated items, its timeline, and its agent sessions with session links, so picking the work back up means opening one place. |
| UC-2 | Decide what to work on next | Sole user | The stack keeps an ordered queue with the current task on top, the inbox recomputes suggestions (reviews overdue past the review SLO, closable tasks, missing change records, leftover worktrees) on every read, the tasks page orders in-flight tasks by deadline, and the launcher exposes the stack from the tray with a global hotkey. |
| UC-3 | Capture scattered work as a task with its context | Sole user | Pasting a GitHub issue or pull request URL (or picking from a repository) imports it, any pasted value or path becomes an item with source inference, and items associate many-to-many with tasks and fetch their content on demand. |
| UC-4 | Keep task context current without fetching it by hand | Sole user | Tiered item refresh re-fetches Slack threads and GitHub issues and pull requests on an age-based schedule with a per-source policy, and the resources list offers search, refresh, and delete across every item. |
| UC-5 | Delegate a task's coding work to an agent and watch it | Sole user | A task run is enqueued as a durable SAQ job, works in an isolated worktree created from a registered repository, streams a live persisted transcript over SSE, and can be cancelled, with the harness and model picked in the run panel. |
| UC-6 | Keep pull requests moving | Sole user | The review queue lists pull requests awaiting review with per-step verdicts, a merge-readiness light, and must/should/may findings, My pulls tracks the user's own open pull requests (check rollup, review decision, approvers, open threads), the PR feedback page triages feedback items with implement, decline, or defer decisions, and the inbox flags pull requests past the review SLO. |
| UC-7 | See everything that happened on the work | Sole user | Each task keeps a chronological timeline, the events feed groups every task's timeline into one stream by day with a chart, and the operations log records every mutating request with its client and human-or-agent provenance. |
| UC-8 | Plan and sequence work | Sole user | The Gantt view shows each task in flight as a bar with one marker per timeline event, and before/after dependency edges form a DAG (the API refuses cycles) drawn on the graph page. |
| UC-9 | Measure output and flow | Sole user | Factory metrics compute autonomy rate and yield for recorded changes against stored metric baselines, and the process view reports stations, cumulative flow, aging WIP, and cycle times derived from timeline events. |
| UC-10 | Keep recurring maintenance running on a schedule | Sole user | Scheduled tasks run user-defined shell commands when their 5-field cron expression is due, recording each run's exit code and output tail. |
| UC-11 | Orchestrate multi-step agent work | Sole user | Execution graphs chain run nodes, CLI commands, and form nodes; a graph execution pauses at a form node until someone answers it in the web UI, then flows the answer downstream and resumes. |
| UC-12 | Prepare replies while on call | Sole user | The on-call view runs an on-call scan of a Slack channel that collects what needs answering and prepares draft replies. |
| UC-13 | Catch up on what colleagues decided | Sole user | The decisions page reads the colleague decision reports under the notes tree, read-only. |
| UC-14 | Track who and which checkouts a piece of work involves | Sole user | The people directory links people and their aliases to tasks and items, repositories register local checkouts with repository groups that tell a task's agent which checkouts may be relevant, and a requester records who asked for a task. |
| UC-15 | Drive the tracker from a phone | Sole user | The web app is an installable Vue 3 PWA whose layouts collapse to an off-canvas drawer below 760px with touch-friendly controls and safe-area handling, so it stays usable at phone widths. |
| UC-16 | Work a task with its full context as the task's operator | Coding agent | The context prompt built for a run carries the task, its items, repositories, group, and worktrees, the agent works in an isolated worktree, and its summary and next steps are written back to the task. |
| UC-17 | Integrate a coding harness without changing the app | ACP harness authors | Any harness reachable over ACP can be added under Settings → Harnesses (one marked default, an optional per-harness model, and a warm session pool for the model picker), and the runner drives it through the same client. |

## Wanted

| ID | Use case | Actor | Description | Signal |
|---|---|---|---|---|

None recorded yet.

## Out of scope

- Multi-user access, authentication, or tenancy isolation.
- OAuth flows, webhooks, or continuous two-way sync with external systems.
- A hosted or cloud deployment (the app is local-first and only safe to expose on a trusted network).
- Interactive agent permission approval (run requests are auto-approved).
