<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Vocabulary

## Domain Terms

| Term | Definition |
|---|---|
| Agent event | One normalized update in a run's transcript (message, thought, tool_call, tool_update, plan, usage, status, or error). |
| Agent run | One prompt sent to a harness in a working directory, with its transcript and status. |
| Association | A link between a source item and a task, carrying an optional note. |
| Autonomy rate | The share of accepted changes that reached production with no human intervention. One of the two primary factory metrics. |
| Change | A unit of factory output, recorded against a task with a lifecycle, a start and end time, and a human-intervened flag; the input the metrics are computed from. |
| Change class | The kind of a change: feature, bugfix, refactor, chore, docs, test, or trivial. |
| Context refresh | A special agent run that reads a task and its items and rewrites the task's summary and next steps. |
| Deadline | The date and time by which a task should be done; a task without one has no due date. |
| Feedback decision | The outcome recorded on a reviewer-feedback item: `implement`, `decline`, or `defer`. A decision with no `executed_at` is awaiting a run. |
| Feedback item | One reviewer-comment analysis file the feedback skills write under the user-global store, triaged on the PR feedback page. |
| Follow-up date | The date and time to check back with the person a task waits on; when it passes, the task rejoins the focus stack. |
| Harness | A coding-agent command reachable over ACP, stored as a row (`command` plus `args`). |
| Human intervention | A recorded human touch on a change (question, correction, manual fix, rerun, or approval) that makes the change non-touchless. |
| Item | A `SourceItem`: something external (Slack thread, GitHub issue or PR, Drive doc, URL, note, commit, file) that can be associated to tasks. |
| Merge | Folding one person into another: the source's aliases and its task and item links move to the target, then the source is deleted. |
| Metric baseline | The stored value a metric's direction (improving, worsening, flat, or no-baseline) is measured against. |
| Next steps | The agent-maintained list of concrete actions for a task, each with a `done` flag. |
| Parked | A task off the focus stack because it waits on a person or is snoozed. It is still in flight, and it returns when the deferral ends or the task is pushed. |
| Person | An individual a task or a source item involves: a name, a set of aliases, and optional notes. |
| Person alias | An identifier for a person (a handle such as a GitHub login or Slack user id, or an email), used to de-duplicate people across sources. |
| Repository | A local git checkout registered with the app, from which worktrees are created. |
| Repository group | A named set of repositories that tells a task's agent which checkouts may be relevant. |
| Requester | A person recorded as having asked for a task, a link set separate from the people the task involves. |
| Session link | A way to reopen an agent session: an OpenChamber URL, a terminal URL, or a copyable resume command. |
| Snooze | A date and time a task is parked until, without changing its status or marking it done. |
| Source | The origin kind of an item: `slack`, `github`, `gdrive`, `url`, `note`, `commit`, or `file`. |
| Stack | The focus queue of tasks: an ordered list where the top task is current and the rest are queued. It is materialized from the in-flight tasks, so an open, in-progress, or blocked task joins automatically unless it is parked. |
| Stack entry | A task's presence on the stack, carrying its position, whether it is current, a soft-delete timestamp, and why it was deleted (popped, removed, or parked). A parked entry is restored when its deferral ends. |
| Current task | The task at the top of the stack (position 0); the one being worked on now. |
| Task session | A stretch of time a stack entry spent as the current task, with a start and an end; execution count and duration are derived from these. |
| Launcher | The optional native menu-bar/tray companion (`agentic-stack`) that adds a global hotkey and a Mark Done action a browser cannot provide. |
| Summary | The agent-maintained short current-state paragraph for a task. |
| Tag | A short label a task carries; stored as a list on the task, normalized on write, and usable to filter the task list. |
| Task | The unit of work everything hangs off. |
| Timeline event | A persisted record of a meaningful change to a task, shown as a chronological timeline. |
| Touchless | A change with no recorded human intervention; the numerator of the autonomy rate. |
| Waiting on | The person a task waits on. Setting one marks an open task blocked, and parks the task until its follow-up date (or until the person is cleared when there is no follow-up date). |
| Worktree | An isolated `git worktree` created for a task from a registered repository. |
| Yield | The share of accepted changes that survived the observation window without being reverted. One of the two primary factory metrics. |

## Technical Terms

| Term | Definition |
|---|---|
| ACP | Agent Client Protocol; JSON-RPC over stdio used to drive coding-agent harnesses. |
| Context prompt | The prompt built from a task, its items, repositories, group, and worktrees for a context refresh. |
| Directory picker | The server-side filesystem browser (`GET /api/fs/list`) used to add repositories, confined to `AGENTIC_FS_ROOT`. |
| Event bus | The in-process asyncio publish/subscribe used to stream events to SSE subscribers. |
| Gantt view | A timeline page showing each task in flight as a bar with one marker per timeline event. |
| People page | The SPA route (`/people`) listing people with the tasks and items each is linked to. |
| Mobile support | The application is designed with mobile in mind, so layouts and controls work on small phone screens as well as desktops. |
| Source inference | Deriving an item's source, kind, and external id from a pasted value (URL or plain text). |
| SSE | Server-Sent Events, used for the live run transcript and task-change streams. |

## Acronyms and Abbreviations

| Abbreviation | Expansion |
|---|---|
| ACP | Agent Client Protocol |
| API | Application Programming Interface |
| CLI | Command-Line Interface |
| CORS | Cross-Origin Resource Sharing |
| DB | Database |
| FK | Foreign Key |
| JSON | JavaScript Object Notation |
| ORM | Object-Relational Mapping |
| PK | Primary Key |
| PWA | Progressive Web App |
| SPA | Single-Page Application |
| SSE | Server-Sent Events |
| URL | Uniform Resource Locator |
| UUID | Universally Unique Identifier |
| WAL | Write-Ahead Logging |
