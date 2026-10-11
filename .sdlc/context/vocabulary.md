<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Vocabulary

## Domain Terms

| Term | Definition |
|---|---|
| Agent event | One normalized update in a run's transcript (message, thought, tool_call, tool_update, plan, usage, status, or error). |
| Agent run | One prompt sent to a harness in a working directory, with its transcript and status. |
| Association | A link between a source item and a task, carrying an optional note. |
| Context refresh | A special agent run that reads a task and its items and rewrites the task's summary and next steps. |
| Harness | A coding-agent command reachable over ACP, stored as a row (`command` plus `args`). |
| Item | A `SourceItem`: something external (Slack thread, GitHub issue or PR, Drive doc, URL, note, commit, file) that can be associated to tasks. |
| Next steps | The agent-maintained list of concrete actions for a task, each with a `done` flag. |
| Repository | A local git checkout registered with the app, from which worktrees are created. |
| Repository group | A named set of repositories that tells a task's agent which checkouts may be relevant. |
| Session link | A way to reopen an agent session: an OpenChamber URL, a terminal URL, or a copyable resume command. |
| Source | The origin kind of an item: `slack`, `github`, `gdrive`, `url`, `note`, `commit`, or `file`. |
| Summary | The agent-maintained short current-state paragraph for a task. |
| Task | The unit of work everything hangs off. |
| Timeline event | A persisted record of a meaningful change to a task, shown as a chronological timeline. |
| Worktree | An isolated `git worktree` created for a task from a registered repository. |

## Technical Terms

| Term | Definition |
|---|---|
| ACP | Agent Client Protocol; JSON-RPC over stdio used to drive coding-agent harnesses. |
| Context prompt | The prompt built from a task, its items, repositories, group, and worktrees for a context refresh. |
| Directory picker | The server-side filesystem browser (`GET /api/fs/list`) used to add repositories, confined to `AGENTIC_FS_ROOT`. |
| Event bus | The in-process asyncio publish/subscribe used to stream events to SSE subscribers. |
| Gantt view | A timeline page showing each task in flight as a bar with one marker per timeline event. |
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
