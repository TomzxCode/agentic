<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Vocabulary

## Domain Terms

| Term | Definition |
|---|---|
| Aging WIP | The aging work-in-progress list: the items currently sitting in each station, each with how long it has been waiting (its queue age). |
| Agent event | One normalized update in a run's transcript (message, thought, tool_call, tool_update, plan, usage, status, or error). |
| Agent run | One prompt sent to a harness in a working directory, with its transcript and status. |
| Agent session | A coding-agent session recorded against a task: the session an agent run produced, or one attached by hand (for example one started in OpenChamber). |
| Association | A link between a source item and a task, carrying an optional note. |
| Autonomy rate | The share of accepted changes that reached production with no human intervention. One of the two primary factory metrics. |
| Change | A unit of factory output, recorded against a task with a lifecycle, a start and end time, and a human-intervened flag; the input the metrics are computed from. |
| Change class | The kind of a change: feature, bugfix, refactor, chore, docs, test, or trivial. |
| Colleague decision report | A daily Markdown report the extract-colleague-decisions skill writes under the notes tree, naming each colleague's decisions (Decided, Deferred, Open, or Committed), who supported or opposed them, and a Slack permalink. |
| Context refresh | A special agent run that reads a task and its items and rewrites the task's summary and next steps. |
| Cumulative flow diagram | A diagram plotted as stacked areas from daily snapshots of every station's inventory plus cumulative completions, showing work entering and leaving each station over time. |
| Current task | The task at the top of the stack (position 0); the one being worked on now. |
| Cycle time | How long work takes, derived from GitHub issue and pull request events: issue close (opening to closing), review wait (first review request to first review), and review to merge. |
| Deadline | The date and time by which a task should be done; a task without one has no due date. |
| Execution graph | A named DAG of agent runs, CLI commands, and forms that the app executes on demand or on a cron schedule; each execution creates a task, and every run node becomes an agent run attached to it. |
| Feedback decision | The outcome recorded on a reviewer-feedback item: `implement`, `decline`, or `defer`. A decision with no `executed_at` is awaiting a run. |
| Feedback item | One reviewer-comment analysis file the feedback skills write under the user-global store, triaged on the PR feedback page. |
| Follow-up date | The date and time to check back with the person a task waits on; when it passes, the task rejoins the focus stack. |
| Form answer | An answer someone gives in the web UI to a form node's fields; it unblocks the paused execution and flows downstream like a run output. |
| Graph edge | A connection that feeds one upstream output (an agent run's final answer, a command's stdout, or a form field value) into one downstream input. |
| Graph execution | One run of an execution graph, carrying its statuses, each run node's output, and the form answers; it pauses while a form node waits to be answered. |
| Graph node | One step of an execution graph: a run node (a prompt template reading named inputs), a cli node (an agentic CLI command line), or a form node (fields someone answers in the web UI). |
| Harness | A coding-agent command reachable over ACP, stored as a row (`command` plus `args`). |
| Human intervention | A recorded human touch on a change (question, correction, manual fix, rerun, or approval) that makes the change non-touchless. |
| Inbox suggestion | A suggestion of something to do, recomputed on each read from the tasks, their items and changes, their worktrees, the pull requests awaiting the user's review, and the user's own unreviewed pull requests; nothing is stored, so acting on it makes it disappear. |
| Item | A `SourceItem`: something external (Slack thread, GitHub issue or PR, Drive doc, URL, note, commit, or a local file or directory path) that can be associated to tasks. |
| Launcher | The optional native menu-bar/tray companion (`agentic-stack`) that adds a global hotkey and a Mark Done action a browser cannot provide. |
| Merge | Folding one person into another: the source's aliases and its task and item links move to the target, then the source is deleted. |
| Metric baseline | The stored value a metric's direction (improving, worsening, flat, or no-baseline) is measured against. |
| My pulls | The viewer's own open pull requests, with derived header counts, cached so a reload does not re-query GitHub; nothing is stored, so a merged pull request leaves the list on the next refresh. |
| Next steps | The agent-maintained list of concrete actions for a task, each with a `done` flag. |
| On-call scan | A scan of a Slack channel that collects what needs answering and prepares draft replies for the on-call view. |
| Operation | One audit-log row per mutating `/api` request, stamped with the client and actor behind it; it covers work that has no task to hang a timeline event off. |
| Parked | A task off the focus stack because it waits on a person or is snoozed. It is still in flight, and it returns when the deferral ends or the task is pushed. |
| Person | An individual a task or a source item involves: a name, a set of aliases, and optional notes. |
| Person alias | An identifier for a person (a handle such as a GitHub login or Slack user id, or an email), used to de-duplicate people across sources. |
| Process view | The SDLC process read as a production line: tasks move between stations, and the view reports inventory, cumulative flow, aging WIP, efficiency, forecast, and outcomes. |
| Provenance | The client (web, cli, or api) and actor (human or agent) declared in headers on each mutating request, stamped on records such as timeline events and the operations log. |
| Repository | A local git checkout registered with the app, from which worktrees are created. |
| Repository group | A named set of repositories that tells a task's agent which checkouts may be relevant. |
| Requester | A person recorded as having asked for a task, a link set separate from the people the task involves. |
| Review finding | A finding a review skill recorded for a pull request, with a severity of `must`, `should`, or `may`, plus a title, description, status, and the `first_seen_sha` it was recorded at; the reviewer marks each `include` or `skip`. |
| Review queue | The pull requests awaiting the user's review: the stored review-skill reports enriched with each pull request's own fields from ghx, cached briefly. |
| Review SLO | A duration a pull request may await the user's review before the inbox flags it, measured from when the review scan first saw it waiting. |
| Review nudge SLO | A duration a pull request authored by the user may wait without any review from anyone before the inbox offers to poke its reviewers, measured from when the pull request was opened. |
| Review scan | The GitHub search that finds pull requests awaiting the user's review (`review-requested:@me` and `reviewed-by:@me`), so the queue can show them before any review report exists. |
| Scheduled task | A user-defined shell command the scheduler runs when its 5-field cron expression is due; each execution is recorded as a `ScheduledTaskRun` with its exit code and output tail. |
| Session link | A way to reopen an agent session: an OpenChamber URL, a terminal URL, or a copyable resume command. |
| Snooze | A date and time a task is parked until, without changing its status or marking it done. |
| Source | The origin kind of an item: `slack`, `github`, `gdrive`, `url`, `note`, `commit`, or `file` (a local file or directory path). |
| Stack | The focus stack: an ordered list of tasks where the top task is current and the rest are queued. It is materialized from the in-flight tasks, so an open, in-progress, or blocked task joins automatically unless it is parked. |
| Stack entry | A task's presence on the stack, carrying its position, whether it is current, a soft-delete timestamp, and why it was deleted (popped, removed, or parked). A parked entry is restored when its deferral ends. |
| Station | A stage of the production-line view of the SDLC process: backlog is raw material, in progress is the work station, blocked is the rework and waiting area, done is finished goods, and archived goods have shipped. |
| Summary | The agent-maintained short current-state paragraph for a task. |
| Tag | A short label a task carries; stored as a list on the task, normalized on write, and usable to filter the task list. |
| Task | The unit of work everything hangs off. |
| Task dependency edge | A before/after edge between two tasks; the dependency graph must stay acyclic. |
| Task relation | A symmetric link between two tasks that says they are related, with no ordering and no place in the dependency graph. |
| Task session | A stretch of time a stack entry spent as the current task, with a start and an end; execution count and duration are derived from these. |
| Timeline event | A persisted record of a meaningful change to a task, shown as a chronological timeline. |
| Tool transport | How the app reaches ghx or slackx: `cli` (shell out per call), `rpc` (the URL and token of an already-running serve mode), or `managed` (the server starts and stops the serve-mode process). |
| Touchless | A change with no recorded human intervention; the numerator of the autonomy rate. |
| Waiting on | The person a task waits on. Setting one marks an open task blocked, and parks the task until its follow-up date (or until the person is cleared when there is no follow-up date). |
| Warm session pool | The one warm ACP session of the default harness the API holds open from startup, so the model picker answers in a single request; it is best effort, and runs still spawn their own session. |
| Worktree | An isolated `git worktree` created for a task from a registered repository. |
| Yield | The share of accepted changes that survived the observation window without being reverted. One of the two primary factory metrics. |

## Technical Terms

| Term | Definition |
|---|---|
| ACP | Agent Client Protocol; JSON-RPC over stdio used to drive coding-agent harnesses. |
| AG Grid | The community Vue data grid component used for table views such as repositories and people. |
| Context prompt | The prompt built from a task, its items, repositories, group, and worktrees for a context refresh. |
| Directory picker | The server-side filesystem browser (`GET /api/fs/list`) used to add repositories, confined to `AGENTIC_FS_ROOT`. |
| Event bus | The in-process asyncio publish/subscribe used to stream events to SSE subscribers. |
| Gantt view | A timeline page showing each task in flight as a bar with one marker per timeline event. |
| ghx | The cache-backed GitHub CLI the app shells out to for issue and pull request data; it has no search qualifiers, so searches still go through `gh`. |
| Mobile support | The application is designed with mobile in mind, so layouts and controls work on small phone screens as well as desktops. |
| People page | The SPA route (`/people`) listing people with the tasks and items each is linked to. |
| SAQ | Simple Async Queue, the durable job queue agent runs execute on, backed by a SQLite queue next to the application database. |
| slackx | The cache-backed Slack CLI the app shells out to; it names workspace users, reads threads and channels, and its serve mode offers a web UI and a JSON-RPC endpoint. |
| Source inference | Deriving an item's source, kind, and external id from a pasted value (URL, filesystem path, or plain text). |
| SSE | Server-Sent Events, used for the live run transcript and task-change streams. |

## Acronyms and Abbreviations

| Abbreviation | Expansion |
|---|---|
| ACP | Agent Client Protocol |
| API | Application Programming Interface |
| CLI | Command-Line Interface |
| CORS | Cross-Origin Resource Sharing |
| DAG | Directed Acyclic Graph |
| DB | Database |
| FK | Foreign Key |
| JSON | JavaScript Object Notation |
| ORM | Object-Relational Mapping |
| PK | Primary Key |
| PWA | Progressive Web App |
| RPC | Remote Procedure Call |
| SDLC | Software Development Life Cycle |
| SLO | Service Level Objective |
| SPA | Single-Page Application |
| SSE | Server-Sent Events |
| URL | Uniform Resource Locator |
| UUID | Universally Unique Identifier |
| WAL | Write-Ahead Logging |
| WIP | Work In Progress |
