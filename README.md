# Agentic

Track work as **tasks**, associate the Slack threads, GitHub issues/PRs, and
Google Drive docs that feed them, spin up git worktrees to work on them, and let
a coding agent keep a current summary and next-steps list so resuming is quick.

Documentation: <https://tomzxcode.github.io/agentic/>

- **Backend**: FastAPI + SQLModel (SQLite), single-user and local-first.
- **Agents**: any [ACP](https://agentclientprotocol.com/) harness. OpenCode
  (`opencode acp` / `opencode2 acp`) and pi (`pi-acp`) are preconfigured; add
  more in Settings.
- **Frontend**: Vue 3 + Vite, built as an installable PWA and served by the API.
  Responsive down to phones: the task list becomes an off-canvas drawer and
  the detail view stacks into a single column.
- **CLI**: `agentic` drives the whole API (tasks, links, worktrees, runs,
  context) with JSON output, so agents can create and maintain the content.
  `agentic-server` runs and inspects the backend itself.

## Layout

A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) with
two Python packages and the SPA:

| Path | Package | Command | Role |
| --- | --- | --- | --- |
| `backend/` | `agentic` | `agentic-server` | FastAPI API, ACP agent runner, DB |
| `cli/` | `agentic-cli` | `agentic` | HTTP client that drives the API |
| `launcher/` | `agentic-launcher` | `agentic-stack` | Menu-bar/tray companion: global hotkey + Mark Done (pop) |
| `frontend/` | — | — | Vue 3 + Vite PWA served by the API |

`uv sync` at the root installs all three packages and their console scripts into
one virtualenv.

## Concepts

| Concept | What it is |
| --- | --- |
| **Task** | The unit of work. Everything hangs off it. Carries an agent-maintained `summary` and `next_steps`. |
| **Item** | Something external: a Slack thread, GitHub issue/PR, Drive doc, URL, note, commit, or a local file/directory path. Items are deduplicated by URL / external id. |
| **Association** | A link between an item and a task (many-to-many), with a note. |
| **Person** | An individual a task or an item involves: a name plus optional email, handle, and notes. Linked to tasks and items many-to-many. |
| **Worktree** | An isolated `git worktree` created for a task from a registered repository. |
| **Repository group** | A named set of repositories. Picking one on a task tells the agent those checkouts may hold information relevant to it. |
| **Agent run** | One prompt sent to a harness in a working directory, delivered to the worker through the run queue. Events stream live to the UI. |
| **Agent session** | An agent session recorded against a task: its session id, harness, working directory, and a label. A run records the session it produced; this records one you attach by hand (for example one opened in OpenChamber), and both build the links that reopen it. |
| **Context refresh** | A special agent run that reads the task + its items and writes the `summary` and `next_steps`. |
| **Scheduled task** | A user-defined shell script the API runs on a cron schedule, with a recorded history of runs. |
| **Change** | A unit of factory output recorded against a task: a class, a lifecycle, a start/end time, and a human-intervened flag. Autonomy rate and yield are computed from changes. |
| **Stack entry** | A task's place on the focus stack: its position (0 is current), whether it is current, a soft-delete timestamp, and why it was deleted (popped, removed, or parked). |
| **Waiting on** | The person a task waits on, plus an optional check-back date. The task is blocked and off the stack until the date passes or the person is cleared. |
| **Snooze** | A date a task is parked until, without changing its status; it returns to the stack when the date passes. |
| **Task session** | A stretch of time a stack entry spent as the current task; execution count and duration are derived from these. |
| **Operation** | An audit record of a mutating request: its method, path, and status, plus which client sent it (web UI, CLI, or raw API) and whether a human or a coding agent was behind it. |

Every meaningful change writes a **Timeline event**, so a task's evolution is
visible at a glance. Each timeline event also carries its **provenance**: the
client it came from and whether a person or an agent performed it. The web UI
sends `web`/`human`; the CLI sends `cli` plus whatever actor its environment
declares, and the ACP runner sets `AGENTIC_ACTOR=agent` for a harness, so agent
work is told apart from human work. Every mutating request is also recorded in
the operations log (`GET /api/operations`).

## How agents are wired

The backend speaks **ACP (Agent Client Protocol) over stdio**. That is the
abstraction that lets you switch harnesses without touching app code: each
harness is just a command row in the `harness` table.

Each agent run is a **job on a queue** (SAQ, backed by SQLite by default), not an
in-process task. The API only enqueues; one or more worker processes dequeue and
run the harness. That way a long agent turn survives an API restart and can be
retried, and workers scale independently of the API. The queue has a built-in
monitor at `/saq` (SAQ's web UI): it lists queued, active, and finished jobs and
can retry or abort one.

```
FastAPI ──enqueue──▶ queue (SQLite) ◀──dequeue── worker ──spawn──▶ opencode acp   ┐
   ▲                                                                 pi-acp        ├── ACP JSON-RPC over stdio ──▶ agent
   │                                                               (your harness)  ┘
   └── SSE ◀── normalized events (message / thought / tool_call / plan / usage)
```

Default harnesses (seeded automatically):

| Id | Command | Notes |
| --- | --- | --- |
| `opencode2` | `opencode2 acp` | OpenCode v2. Seeded as the default when installed. |
| `opencode` | `opencode acp` | OpenCode v1. Default when v2 is not installed. |
| `pi` | `pi-acp` | `pi` via the pi-acp adapter. |

The default harness runs when a task does not pick one; change it under
Settings → Agent harnesses (the default is marked with a badge). Each harness can
also carry a **model**: set it under Settings → Agent harnesses, and the runner
selects it over ACP (`session/set_config_option`) after the session is created. A
blank model uses the harness's own default, which the settings page shows as the
field's placeholder: the server reads it from the harness's config file
(`default_model_source`, for example `~/.config/opencode/opencode.json#model` for
OpenCode and `~/.pi/agent/settings.json#{defaultProvider}/{defaultModel}` for
`pi`) instead of spawning the harness to ask.

The task view's agent panel has its own **model** picker beside the harness
picker, so a single run can answer with a different model without changing the
harness. Its choices are the ones the harness's ACP session offers; the server
holds one session open for the default harness from startup
(`AGENTIC_WARM_HARNESS_SESSION`), so the list arrives in one request. A run's
choice applies to that run only; leaving the picker on its default uses the
harness's own model.

## Quickstart

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22.12+,
[pnpm](https://pnpm.io/), and at least one harness on your `PATH`
(`opencode`/`opencode2` and/or `pi-acp`).

```bash
# 1. Backend + CLI (API on :8600), from the repository root
uv sync
uv run agentic-server serve --host 0.0.0.0 --port 8600 --reload

# 2. Worker (processes queued agent runs; run it alongside the API)
uv run agentic-server worker

# 3. Frontend (dev server on :5173, proxies /api to :8600)
cd frontend
pnpm install
pnpm run dev
```

Open http://localhost:5173.
`make run` starts the API, the worker, and the frontend together.

### Single-app mode

Build the SPA into `backend/static` and let FastAPI serve everything:

```bash
cd frontend && pnpm run build      # writes ../backend/static
uv run agentic-server serve --host 0.0.0.0 --port 8600   # from the repo root
uv run agentic-server worker                             # in another shell
```

Open http://127.0.0.1:8600. The PWA installs from there.

### Remote access

Both servers bind `0.0.0.0`, so you can open them from another device on the
same network (or over a VPN such as Tailscale):

- Frontend dev server: `http://<host>:5173` (the Vite config exposes `host: true`).
- Backend / built app: `http://<host>:8600`.

Vite only accepts Host headers listed in `server.allowedHosts` (add your
hostname there); IP addresses are always allowed. There is no authentication, so
only expose this on a trusted network.

## Using it

1. **Create a task** (the `+` in the sidebar). To **import**, paste a GitHub
   issue/PR URL or a Slack thread URL into the import field, which detects the
   source: a GitHub URL prefills the title and description and links the issue,
   while a Slack URL is gathered with `slackx` so an agent can name the task and
   summarize the discussion (if that run fails, use **Name & summarize** in the
   task's Context panel to retry). You can also expand "or pick from a repository",
   choose a registered repo, and pick an issue (filterable, newest first).
   Optionally pick a **repository group** so the agent knows which checkouts to
   consider, add **tags** to label the task, and set a **deadline** (a date; the
   time defaults to 17:00, so you usually only pick the date). Tags show as pills
   on the task and in the sidebar; pick one in the sidebar or on the Tasks page
   to see only the tasks that carry it. A task with a deadline shows a Due badge
   on its row, and the Tasks page lists the ones coming up under
   **Upcoming deadlines** (overdue first, with a window selector). Each row on
   the Tasks page also shows its priority as a colored dot (low/medium/high/urgent).
   To defer a task, set **Waiting on** to a person (with an optional **check
   back** date) or pick a **Snooze** date on its page: the task stays on the
   Tasks page but leaves the focus stack until the date passes, then rejoins it.
   Waiting marks an open task blocked and names the person on its row; a snooze
   leaves the status alone.
2. **Associate items**: paste a Slack thread permalink, a GitHub issue/PR URL, a
   Drive doc, a path to a local file or directory, or write a note. The source
   (Slack/GitHub/Drive/URL/path/note) is inferred from what you paste. GitHub and
   Slack/URL items are fetched on demand (via `ghx` for GitHub and `slackx` for
   Slack); a path stays a reference to the file or directory, with its preview
   read live when opened and never stored. Text files are shown in full, and a
   Markdown file is rendered as Markdown; you can also paste content directly.
3. **Add repositories** in Settings. Use **Browse…** to pick folders on the
   machine (select several at once); git repositories are marked. Group related
   repositories (**Repository groups**) so a task can point the agent at
   them. A task can also be associated with 0..n repositories directly (the
   `repositories:` chips on its header). Then create a **worktree** for the task.
   A task's **Create GitHub issue** button files its title and description as an
   issue: it uses the task's only repository directly, or asks which repository
   when none or several are linked, then links the new issue back to the task.
4. **Refresh with agent** to generate the current summary and next steps.
5. **Run an agent** against the task; the transcript streams live.

Press **Ctrl/Cmd+K** (or the ⌘K button) for a command palette to jump to any
task or action from the keyboard. On a task page it also lists that task's
fields (**This task**: edit title/description, set status/priority/deadline,
repository group, add repository, set tags), so you can jump straight into editing any of
them without tabbing across the page. It also lists every tag in use under
**Tags**, so you can filter the task list by a tag (and clear the filter) from
the keyboard.

The task list on the left is sizeable: drag its right edge (with the keyboard,
the arrow keys nudge it, **Home**/**End** jump to the bounds, **Enter** resets,
and a double-click restores the default). The panel icon at the left of the page
title, or **Ctrl/Cmd+B** (which works anywhere on the page), hides it entirely
and gives the page the full width; the same icon or shortcut brings it back. Both
the width and the hidden state are remembered per device. On a narrow screen the
task list is a drawer instead, opened with the panel button in the corner or a
right swipe.

The row of page icons at the bottom of the sidebar is yours to arrange: under
**Settings → Sidebar**, uncheck a page to hide its icon and drag the grip to move
it in the order. The choice is remembered per device, and every page stays
reachable from the command palette even when its icon is hidden.

The **Tasks in flight** page also lists the people linked to the current
in-flight work, so you can narrow the list (and its status counts and upcoming
deadlines) to a single person's tasks. The status badges at the top (Open,
In progress, Blocked, Done) are filters: click one to show only the tasks in
that status, including Done, which the in-flight list otherwise hides; click it
again to go back. The **Group by** control splits the list into sections by
status, priority, person, tag, or repository; repository groups by the first
repository linked to a task (its main repository), and a task with none falls
into a "No repository" group. The choice is remembered per device.

The **Items** page lists every resource the app tracks (Slack threads, GitHub
issues/PRs, Drive docs, URLs, notes) with per-source filters, search, and links
to the tasks each one is used by. Each item opens a page laid out for its type
(a GitHub issue/PR with its state and author, a Slack thread as a transcript, a
note's text, or a fetched link) with its linked tasks and people. A Slack thread
can be marked **Done** from either its row or its page. A message that arrives
after that is flagged as **new messages** on the item, and the thread keeps its
done state: **Reopen** is an explicit choice, not something a reply does.
When a ghx or slackx web server is configured under **Settings → Local tools**, a
GitHub or Slack item also links into that tool's local UI.

The **Events** page (`/events`, the stream icon) is one stream of every task's
timeline, newest first: task creation, edits, status moves, items, people,
worktrees, runs, changes, and stack moves. Events are grouped by day, and each
day renders the timeline component over that day's events: a chart with one
marker per event, then the events themselves. Each row names the task it
happened to (and links back to it), the event type, and whether a person or an
agent did it through the web, the CLI, or the API. Search filters the
server-side history by message or task title, and the actor and client selects
narrow it to one kind of activity. The page loads the newest 50 events and pages
backwards on demand.

People are linked to both tasks and items. A task page has a **People** panel to
link someone from the directory (or add a new person), and a **Requested by**
panel next to it that names the people who asked for the task, a separate link
set from the people it involves. The **People** page lists everyone with the
tasks and items each is attached to, and tags each task with how the person is
attached (one of its people, its requester, or both). People are also
auto-populated when an item is fetched: a GitHub issue/PR brings its author,
assignees, and commenters, and a Slack thread brings its participants; linking
that item to a task links those people to the task too.

Each task page has a **Changes** panel: record a change against the task, move
it through verify, accept, or revert, and record an intervention whenever you
touch it. The **Metrics** page then tracks the two primary factory metrics
derived from those changes: **autonomy rate** (the share of accepted changes
that had no human intervention) and **yield** (the share of accepted changes
that survived the observation window without a revert). Each metric is shown
against a stored baseline with a direction (improving, worsening, or flat).

Recording is automatic for the common case: when the app observes one of your
pull requests merge and a task already links it, it records the change as
**accepted**, dated to the merge, so autonomy rate and yield do not depend on
remembering to log it. You can still record, edit, or revert a change by hand.

The **Inbox** page (`/inbox`, the envelope icon in the sidebar, with a count
badge) suggests things to do, derived from the current state rather than stored:
it recomputes on every read, so acting on a suggestion makes it disappear. It
groups suggestions by intent: review a pull request the scan has seen awaiting
your review longer than the SLO set in Settings → Review requests, close a task
whose linked GitHub issues and pull requests are all wrapped up (every issue
closed, every pull request closed or merged), record a change for a merged PR
that has none, and remove a worktree left behind by a closed task. A task with no
linked issue or PR is left alone.
A merged PR is only offered a change record when you authored it (the login in
Settings → Identity, else the authenticated `gh` account); a PR someone else
wrote is not your change to record. A merged PR you authored and a task links is
recorded automatically, so the suggestion only remains for a PR the app could not
record on its own (no known login, or no stored author). Each suggestion
names the task it is about and offers the action as a button that calls the
same endpoint the rest of the app uses.

The **Review queue** page (`/reviews`, the clipboard icon) reads the review
reports the review skills write under `~/.sdlc/{owner}/{repo}/pull-requests/`
and shows one row per pull request, grouped by repository, with its author, age,
last comment, reviewed commit, and the time of its last review event, then a
column per review step (Behavior, Risk, Coverage, Validate, Verify, Review).
Each cell shows the step's verdict, in red when its report does not cover the
newest reviewed commit, and opens the report when clicked. A step that is
running right now shows a spinner until it writes its report. A merge-readiness light
beside each PR number summarizes the signals: green when the PR could be
approved automatically, yellow when something still needs attention, red when a
verdict blocks approval. The page mirrors the `review_requested_prs` script's
table: the review-step state comes from the store, each PR's own fields (title,
state, author, age) come from `ghx`, and fields that would need a read it does
not make (the diff size, the approvers, the PRs an open PR blocks) are left out.
A **📝** before each PR's readiness light links to the task its item is
associated to, opening it in its **PR** view (`/task/{id}?view=pr`); when no
task is linked, a **➕** imports the PR into a new task, the same way the
repository view's "New task" does.
The queue filters by pull request status, one or more repositories, one or more
authors, and a text search over the row's fields. Draft pull requests are left
out unless the **Drafts** chip is turned on.
**Refresh** re-reads the store and bypasses the short cache of those `ghx`
lookups.

The queue also shows what GitHub says is still waiting on you, which the report
store alone cannot: a background scan searches for pull requests with a review
requested from you and for open ones you have already reviewed, and lists them
even before any review report exists. A **📨** or **👀** mark beside the number says
which search found it (a review is requested from you, or you already reviewed it
and it is still open). **Settings → Review requests** sets how
often the scan runs (a duration such as `1h`; blank stops it), the **Review
SLO** (a duration such as `1d`; blank turns it off, and a pull request past it
is flagged in the inbox), whether a repository with no policy of its own is
included or excluded, and each registered repository's own Include / Exclude /
Default choice; **Scan now** runs it immediately.

The **My PRs** page (`/my-pulls`, the pull-request icon) lists the open pull
requests the GitHub login in Settings → Identity authored, one row per PR, and
the four things that decide whether it is moving: its head commit's check
rollup (passing, running, failing, or no checks), its review decision (approved,
changes requested, review required, or no review), who approved it, and how many
of its review threads are still open. Clicking the CI badge opens the pull
request's individual checks in a panel, failing first, with each check's state
and a link to its detail page; the checks are read on demand, so the page load
carries only the rollup. Each row's number opens the app's PR page, with a `ghx`
link (when a local ghx web server is configured) and a `gh` link to GitHub
beside it. Rows carry a vertical edge in the colour of the rank that placed
them (red for failing checks, orange for requested changes, amber for open
threads, blue for running checks, violet for a required review, green for
approved, grey for no action needed), with a tooltip naming that state, and sort
first, then by newest update; a text search filters by repository, number, title, or approver,
the same repository multi-select as the review queue narrows it to chosen
repositories, and chips narrow the list by CI status, review status, or whether
it has open threads, each chip counting the pull requests it would show. **Group
by** splits the list into sections (repository, CI status, or review status) and
remembers the choice on the device, and **Refresh** re-queries GitHub instead of
reusing the short cache. The list
comes from one GraphQL search through `gh`, because neither `ghx` nor `gh`'s
`--json` field set carries a review thread's resolved state, and nothing is
stored, so a PR that merges leaves the page on the next refresh.

The **PR feedback** page (`/feedback`, the speech-bubble icon) triages the
reviewer comments on the pull requests you authored. It reads the analysis files
the `handle-pr-reviewer-feedback` skill writes under
`~/.sdlc/{owner}/{repo}/pull-requests/{n}/feedback/`, one card per comment, with
the recommendation and confidence the analysis reached and its sections (the
comment, the analysis, a recommended action, and a draft reply). **Implement**,
**Decline**, or **Defer** records the decision into the file's frontmatter
(`decision` + `decided_at`, leaving `executed_at` unset), which is the "decided
but not run" state `handle-pr-reviewer-feedback` picks up and carries out on its
next run; **Reset** clears the decision. Cards filter and group by pull request,
repository, author, recommendation, status, or comment type, and picking a pull
request (or any other group) in the sidebar narrows the list to it. A card for a
closed PR is marked and hidden under the default "Active PRs" filter.

The **Decisions** page (`/decisions`, the signpost icon) collects what your
colleagues decided, from the reports the `extract-colleague-decisions` skill
writes under `decisions/YYYY/MM/DD.md` (or an ad-hoc
`*.colleague-decisions.md`) in the notes tree. It reads the same files the
skill's `colleague_decisions_page.py` script reads, through
`AGENTIC_NOTES_DIR` (or `NOTES_DIR`, default `~/notes`), and renders them in the
app. Each decision carries its bucket (Decided, Deferred, Open, Committed), its
Slack permalink, and who supported or opposed it. Switch between **By author**,
**By supporter**, **By opponent**, and a **Matrix** view that crosses authors
against the people who backed or opposed their decisions; the diagonal cell is
the author's own total. Search, a date range with 7/30/90-day presets, and the
status chips narrow everything, and the page closes with the report's
not-heard list and cross-cutting notes. It is read-only: the reports belong to
the skill.

A task that links a pull request or an issue gets a **Default / Issue / PR**
switch beside the title. **PR** and **Issue** both lead with each linked item
read fresh from GitHub (state, author, labels, description), so what the pull
request or issue is reads the same in either mode. **PR** then adds the review
queue's row for each pull request: readiness, reviewed commit, and per-step
verdicts (each opening its report), followed by its must/should/may findings.
Both special modes keep the Agent panel below their content, so the linked pull
requests or issues are worked through an agent instead of the GitHub UI. A mode
is disabled while the task links nothing of its kind, and the mode lives in the
URL (`?view=pr` or `?view=issue`), so a link opens a task straight in it.

Both surfaces offer **Share** for a pull request: it lists the must/should/may
findings the review skills recorded in their state files (`review.yaml`,
`validate.yaml`, `verify.yaml`), lets you pick which to send, and hands the
selection to an agent run on the task, whose skills post them inline on the PR.
Each check or uncheck records your decision (`include` or `skip`) on that finding
in its state file, so the selection is still there next time. The app itself
posts nothing.


The task header also links other tasks, next to the repository and people
selectors: add the tasks that must come first (**before**), the tasks that
follow (**after**), and the tasks merely **related** to it. The before/after
links form a DAG (the API refuses a link that would close a cycle), and the
**Graph** page (`/graph`) draws it, one column per dependency step, with an
arrow from each task to the ones that follow it; click a node to open the task.
A related link is symmetric and stays out of the graph.

For hands-on-keyboard navigation, press **f** on any page: every field and
button gets a letter badge; press the letter to focus that control (**Esc**
exits). On a task page that covers the header, the Agent/Items/Changes/Worktrees
panels,
and their buttons.

## The stack

The **Stack** page (`/stack`) is a focus queue: the task at the top is current
and the rest are queued. Every task that is open, in progress, or blocked is on
the stack automatically (a task that leaves those statuses leaves the stack), so
you never add work by hand. A task waiting on a person, or snoozed until a date,
is **parked**: it is still in flight but stays off the stack until its date
passes, then returns where it would join as a new task with its sessions and
execution count intact. Pushing a parked task brings it back immediately and
clears its snooze and wait. Each row shows its status, how many times it has
become current, when it started, when it was last current, and the total time it
has been current.

- **Enter** adds a new task to the top (making it current); **Shift+Enter**
  inserts it right after the current task.
- **↑ / ↓** move the selection; **← / →** move the selected task up or down one.
- **Drag** a row (or its handle) to reorder; the list reorders live and the move
  saves on release.
- **Home** (or `/`) promotes the selected task to current; **Delete** removes it
  from the stack (the task is kept; push it again to bring it back).
- **0–9** select a task by position; **Esc** clears the selection and filter.
- **Click** a row to select it; the status icon opens a picker, so set a task to
  **Done** to complete it (it then leaves the stack). Removed and completed tasks
  stay under **History**.

The optional **launcher** (`agentic-stack`) adds the two things a browser cannot:
a tray icon showing the current task, and a global hotkey (default
`Ctrl+Shift+T`) that opens the stack page from anywhere. See
[`launcher/README.md`](launcher/README.md).

## Open a session in a terminal or OpenChamber

When a run has a session id, the app shows links to reopen that session:

- **Open in OpenChamber** opens `<openchamber_url><openchamber_session_path>`,
  defaulting to `http://your-host:3001/?session=<id>`. For the native app use
  base `openchamber://session` with path `/{session}`.
- **Open in terminal** opens your configured `terminal_url_template` (any URL
  scheme, or a web terminal).
- **Copy resume command** copies something like
  `cd <worktree> && opencode --session <id>` for pasting into a shell.

A run builds these links from the session it produced. For a session agentic did
not start, such as one you opened in OpenChamber, attach it to the task by hand
and it gets the same links:

```bash
agentic session add <task> ses_abc123 --cwd /path/to/checkout --label "repro"
agentic session list <task>
```

The harness defaults to the task's harness; pass `--harness-id` to override it.
The task's detail (in the API and in `agentic task get`) then lists every
recorded session alongside the runs.

Configure the base URLs on the **Settings** page (persisted locally) or with
environment variables. Each harness has an editable resume command template.
Placeholders: `{session}`, `{cwd}`, `{harness}`.

**Settings → Agent prompts** defines one-click prompt buttons for the agent
panel. A prompt shows when a task has exactly one associated issue or pull
request of its kind; clicking it starts a run with the prompt's variables filled
in. The panel lists every variable (hover one for what it holds) and inserts it
at the cursor: `{owner}`, `{repository}`, and `{number}` from the linked item,
and task values such as `{task_id}`, `{title}`, `{description}`, `{status}`,
`{priority}`, `{deadline}`, `{tags}`, `{task_url}`, `{people}`, `{requested_by}`,
`{repositories}`, and `{worktree}`. When a task links several items, each gets a
short id and the item fields become `{li.a.item_url}`, `{li.a.number}`, and so
on (`{li.a}` alone is `owner/repository#number`); the panel labels each id with
the item it names. When you submit a message the panel also attaches a context
block, the task and the linked items the current view is about: the issue in the
issue view, the pull requests in the PR view. Commands (a message starting with
`$` or `/`) carry their own arguments, so the panel does not attach context to
them. Two prompts are seeded: **Review PR**
(`$review-pr-full {number} {owner}/{repository}`) and **Triage issue**
(`$triage-issue {number} {owner}/{repository}`).

The same settings page has an **Editor URL template**; when set, each worktree in
a task shows an **Open in editor** button that opens the worktree path (`{path}`).
Local: `vscode://file{path}`. Remote VS Code over SSH:
`vscode://vscode-remote/ssh-remote+<host>{path}` (needs Remote-SSH; add
`?windowId=_blank` to open in a new window). code-server:
`https://<host>:8443/?folder={path}`. Tunnel:
`https://vscode.dev/tunnel/<name>{path}`.

## Configuration

Environment variables (prefix `AGENTIC_`; the Slack credentials keep slackx's names) or `backend/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENTIC_DATA_DIR` | `~/.agentic` | SQLite DB location. |
| `AGENTIC_WORKTREE_ROOT` | `~/.agentic/worktrees` | Where worktrees are created. |
| `AGENTIC_FS_ROOT` | `~` | Root the repository picker may browse (`/` for anywhere). |
| `AGENTIC_STATIC_DIR` | `backend/static` | Built SPA to serve. |
| `AGENTIC_DEFAULT_HARNESS` | `opencode` | Fallback harness (by name) when no harness is marked default. |
| `AGENTIC_GITHUB_LOGIN` | (empty) | The GitHub login that counts as you, for change-record suggestions. Empty auto-detects the authenticated `gh` account. |
| `SLACK_TOKEN` | (empty) | Slack token the item view's poke action sends with (also `AGENTIC_SLACK_TOKEN`). A `xoxc-` web token needs `SLACK_COOKIE`; empty disables poking. |
| `SLACK_COOKIE` | (empty) | The `xoxd-` cookie for a `xoxc-` token (also `AGENTIC_SLACK_COOKIE`). |
| `AGENTIC_GHX_BACKEND` | `cli` | How the server runs `ghx`: `cli` spawns the binary per call, `rpc` sends the same command lines to a server you run (`ghx rpc serve`, base URL `AGENTIC_GHX_RPC_URL`, token `AGENTIC_GHX_RPC_TOKEN`), `managed` starts `ghx serve` with the server and calls it (no URL or token). Also on **Settings → Local tools**. |
| `AGENTIC_SLACKX_BACKEND` | `cli` | How the server runs `slackx`: `cli` spawns the binary per call, `rpc` sends the same command lines to a server you run (`slackx rpc serve`, base URL `AGENTIC_SLACKX_RPC_URL`, token `AGENTIC_SLACKX_RPC_TOKEN`), `managed` starts `slackx serve` with the server and calls it (no URL or token). Also on **Settings → Local tools**. |
| `AGENTIC_AUTO_APPROVE_PERMISSIONS` | `true` | Auto-approve ACP permission requests. |
| `AGENTIC_OPENCHAMBER_URL` | (unset) | Base URL for "Open in OpenChamber" links. |
| `AGENTIC_OPENCHAMBER_SESSION_PATH` | `/?session={session}` | Path appended to the base. |
| `AGENTIC_TERMINAL_URL_TEMPLATE` | (unset) | URL template for "Open in terminal" links. |
| `AGENTIC_EDITOR_URL_TEMPLATE` | (unset) | URL template for the worktree "Open in editor" button. |
| `AGENTIC_GHX_URL` | (unset) | Base URL of the ghx web UI (`ghx serve`), so GitHub items link into it. A `managed` transport supplies it. |
| `AGENTIC_SLACKX_URL` | (unset) | Base URL of the slackx web UI (`slackx serve`), so Slack items link into it. A `managed` transport supplies it. |
| `AGENTIC_SLACK_REFRESH_POLICY` | (empty) | When to re-fetch Slack threads, e.g. `1d=1h,7d=6h,30d=1d,*=7d`. Empty disables it. |
| `AGENTIC_GITHUB_REFRESH_POLICY` | (empty) | When to re-fetch GitHub issues/PRs, same format. Empty disables it. |
| `AGENTIC_ITEM_REFRESH_TICK` | `300` | Seconds between checks for due items (0 disables the loop). |
| `AGENTIC_REVIEW_SCAN_INTERVAL` | `1h` | How often the review scan asks GitHub which pull requests await you (a duration such as `1h`; empty disables it). |
| `AGENTIC_REVIEW_SCAN_TICK` | `300` | Seconds between checks for whether the review scan is due (0 disables the loop). |
| `AGENTIC_REVIEW_SCAN_DEFAULT` | `include` | What a repository with no review-scan policy of its own does: `include` or `exclude`. |
| `AGENTIC_REVIEW_SCAN_LIMIT` | `100` | Results each review-scan search returns. |
| `AGENTIC_REVIEW_SCAN_EXCLUDE_AUTHORS` | `dependabot[bot]` | Comma-separated logins the review scan leaves out. |
| `AGENTIC_REVIEW_SLO` | (empty) | How long a pull request may await your review before the inbox flags it (a duration such as `8h` or `1d`; empty disables it). Measured from when the scan first saw it waiting. |
| `AGENTIC_SCHEDULED_TASK_TICK` | `30` | Seconds between checks for scheduled shell tasks that are due (0 disables the loop). |
| `AGENTIC_SCHEDULED_TASK_TIMEOUT` | `3600` | Seconds a scheduled shell task may run before it is stopped and marked failed. |
| `AGENTIC_QUEUE_URL` | `sqlite:///<data_dir>/queue.db` | Agent-run queue. Use a `redis://` or `postgres://` URL to share the queue. |
| `AGENTIC_WORKER_CONCURRENCY` | `4` | Agent runs a worker processes concurrently. |
| `AGENTIC_WORKER_SWEEP` | `60` | Seconds between sweeps for stuck jobs (a dead worker's run). |
| `AGENTIC_JOB_TIMEOUT` | `0` | Per-run job timeout in seconds (0 disables it). |
| `AGENTIC_JOB_HEARTBEAT` | `120` | Seconds a job may go untouched before a sweep retries it. |
| `AGENTIC_JOB_RETRIES` | `1` | Times a run is retried after a failure or a dead worker. |

All three session-link settings can also be overridden on the Settings page;
the stored override wins over the environment variable.

### Item refresh policy

Slack threads and GitHub issues/PRs grow stale at different rates, so the API
re-fetches them (`slackx` for Slack, `ghx` for GitHub) on an age-tiered schedule.
Each source has its own policy: a comma-separated list of `age=interval` bands,
with an optional `*` fallback:

```text
1d=1h,7d=6h,30d=1d,*=7d
```

reads: refresh hourly while the item is under a day old, every 6h under a week,
daily under 30 days, and weekly after that. Omit the `*` band (or write
`*=never`) to stop refreshing once an item outgrows the last band. An item's age
is its upstream creation time when known (GitHub `createdAt`, a Slack thread
timestamp), otherwise when it was recorded. An empty policy disables that source.

Both policies are editable on **Settings → Refresh** (each with a live preview),
or with `agentic settings set --slack-refresh-policy "1d=1h,*=7d"
--github-refresh-policy "1d=1h,30d=1d"`, and `agentic item refresh-due` runs a
pass immediately. The same page shows when each source last ran (background job
or forced), how many items it refreshed, and the last error when a run failed
(also `agentic settings refresh-status`). A **Force refresh** button pulls one
source on demand, ignoring its policy (`agentic item refresh-source slack`).

## CLI

Two command-line tools are installed:

- **`agentic`** — the user client. Talks to a running API over HTTP, so agents
  can drive the app's content without touching the database.
- **`agentic-server`** — the backend. Runs the server and reports its config.

### Install

`uv sync` puts both commands in the repository's `.venv`. To use `agentic` from
anywhere, install the CLI as a [uv tool](https://docs.astral.sh/uv/concepts/tools/):

```bash
uv tool install ./cli          # from the repository root
uv tool install -e ./cli       # editable: code changes apply immediately
```

With `-e`, the command links to the working tree, so edits under `cli/src/` take
effect without reinstalling. This installs `agentic` only; run the backend from
the workspace (`uv run agentic-server`).

### User client

```bash
agentic --help                       # everything, grouped by resource
agentic task create --title "Fix the flaky ingest test" --tags bug --tags ci
agentic task create --title "Ship the beta" --deadline 2026-11-01T17:00
agentic task create --title "Await review" --waiting-on <person> --follow-up 2026-11-02T09:00
agentic task create --slack-url https://acme.slack.com/archives/C123/p1700000000000000
agentic task list --status open
agentic task list --tag bug          # every given tag must match
agentic task update <task> --clear-deadline
agentic task update <task> --waiting-on <person> --follow-up 2026-11-02T09:00
agentic task update <task> --clear-waiting   # stop waiting (clears the check-back date)
agentic task update <task> --snooze 2026-11-03T09:00
agentic task update <task> --clear-snooze    # bring it back now
agentic task deadlines               # deadlines in the next 7 days (overdue first)
agentic task deadlines --within-days 30
agentic task link <task> <other> --relation before   # other must be done first
agentic task link <task> <other>                     # other follows (after)
agentic task link <task> <other> --relation related  # related either way (not in the graph)
agentic task deps <task>             # the tasks linked before, after, and related
agentic task unlink <task> <other>
agentic graph                        # the whole before/after DAG (nodes + edges)
agentic tag list                     # tags in use, with task counts
agentic stack push --title "Fix the flaky ingest test"   # add to the top (becomes current)
agentic stack push --title "Then write the notes" --position next
agentic stack list                   # current task first
agentic stack current                # just the current task
agentic stack pop                    # complete the current task, promote the next
agentic stack promote <entry>        # make an entry current
agentic stack reorder <entry> 3      # move an entry to position 3
agentic stack history                # popped and removed entries
agentic link add <task> --url https://github.com/o/r/issues/482
agentic link add <task> --item-id <item>
agentic worktree create <task>
agentic context refresh <task>    # agent rewrites summary + next steps
agentic run create <task> --prompt "Investigate the failure"
agentic run wait <run-id>            # block until it finishes
agentic run stream <run-id>          # live transcript
agentic session add <task> <session-id> --cwd /path/to/checkout --label "repro"
agentic session list <task>          # recorded sessions, with reopen links
agentic session get <task> <session> # one session and how to reopen it
agentic session remove <task> <session>
agentic change create <task> --title "Fix the flaky ingest test" --change-class bugfix
agentic change accept <change>       # also: verify, reject, revert, intervene
agentic metrics show                 # autonomy rate and yield, with direction
agentic metrics baseline set autonomy_rate 0.2
agentic operation list --actor agent # audit log: what changed, from where, by whom
agentic person create --name "Ada Lovelace" --handle ada
agentic person link <person> --task <task>   # also: --item <item>
agentic person link <person> --requested-by <task>  # they asked for the task
agentic person list                  # people with task and item counts
agentic schedule list                # scheduled shell tasks, with last status
agentic schedule create --name backup --schedule "0 3 * * *" --command "make backup" --timezone "Europe/Paris"
agentic schedule run <schedule>      # run one now
agentic schedule runs <schedule>     # one task's run history
agentic schedule runs                # every task's executions, newest first
```

Commands return data. Output is JSON when piped (or with `--format json`) and
human-readable text otherwise (`--format text`). Point it elsewhere with
`--api-url` or `AGENTIC_API_URL`:

```bash
AGENTIC_API_URL=http://box:8600 agentic task list | jq '.[].id'
```

Resources: `task`, `tag`, `stack`, `item`, `link`, `person`, `repository`, `worktree`, `run`,
`session`, `context`, `harness`, `settings`, `change`, `metrics`, `operation`, `schedule`, `graph`, plus `health`.

### Backend

```bash
agentic-server                  # start the server (same as: agentic-server serve)
agentic-server serve --reload
agentic-server worker           # process queued agent runs (run alongside the API)
agentic-server info             # data dir, database, queue, harness availability
```

## API sketch

```
GET/POST            /api/tasks
GET/PATCH/DELETE    /api/tasks/{id}
POST                /api/tasks/{id}/items            (associate)
GET/POST            /api/tasks/{id}/dependencies     (before/after/related links)
DELETE              /api/tasks/{id}/dependencies/{related}
GET                 /api/graph                        (the before/after DAG)
GET                 /api/events                       (every task's timeline, newest first)
POST                /api/tasks/{id}/worktrees
POST                /api/tasks/{id}/runs
GET/POST            /api/tasks/{id}/sessions           (recorded agent sessions)
GET/PATCH/DELETE    /api/tasks/{id}/sessions/{session}
POST                /api/tasks/{id}/context/refresh
GET                 /api/tasks/{id}/stream           (SSE: task changes)
GET                 /api/runs/{id}/stream               (SSE: agent transcript)
GET/PATCH           /api/settings                        (session links, refresh policies, agent prompts)
GET                 /api/fs/list                         (repository picker)
POST                /api/repositories/bulk               (add several at once)
GET                 /api/github/issues                   (issue picker for import)
POST                /api/github/issues                   (create an issue)
GET                 /api/github/issue                    (single issue by URL)
GET/POST/PATCH/DELETE /api/groups                        (repository groups)
GET                 /api/operations                      (provenance audit log)
GET/POST            /api/stack                           (focus queue: list, push)
POST                /api/stack/pop                       (complete current, promote next)
POST                /api/stack/reorder                   (move an entry)
POST                /api/stack/{id}/promote              (make an entry current)
PATCH/DELETE        /api/stack/{id}                      (edit the task / remove the entry)
GET                 /api/stack/history                   (soft-deleted entries)
GET                 /api/stack/current                   (the current task)
GET/POST/PATCH      /api/harnesses   /api/repositories   /api/items
GET                 /api/items/{id}/reviewers       (a PR's reviewers, live from GitHub)
POST                /api/items/{id}/poke                (DM a reviewer on Slack)
GET/POST            /api/changes
GET/PATCH/DELETE    /api/changes/{id}
POST                /api/changes/{id}/status             (lifecycle transition)
POST                /api/changes/{id}/interventions      (record a human touch)
GET                 /api/metrics                         (autonomy rate + yield)
GET/PUT/DELETE      /api/metrics/baselines/{metric}
GET                 /api/inbox                           (suggested next actions)
GET                 /api/reviews                         (PR review queue from the local store)
GET                 /api/reviews/task/{task_id}          (the queue scoped to a task's PRs)
GET                 /api/reviews/findings/{number}       (a PR's must/should/may findings)
POST                /api/reviews/findings/{number}/decisions  (record include/skip on findings)
GET                 /api/reviews/report/{number}/{name}  (one review report)
GET/POST            /api/reviews/scan                   (the review scan: state, or run it now)
GET                 /api/feedback                        (reviewer comments awaiting a decision)
POST                /api/feedback/{feedback_id}/decision (record implement/decline/defer)
GET                 /api/decisions                       (colleague-decisions reports from the notes tree)
GET/POST            /api/schedules                      (cron-scheduled shell tasks)
GET/PATCH/DELETE    /api/schedules/{id}
POST                /api/schedules/{id}/run            (run now)
GET                 /api/schedules/{id}/runs           (run history)
GET                 /api/schedules/runs                (every task's executions)
GET                 /api/schedules/runs/{id}           (one run)
GET                 /api/schedules/preview             (next runs for a cron expression)
```

## Development

```bash
make test              # backend + CLI and frontend tests (no coverage)
make test-backend      # backend + CLI (pytest) tests, parallel
make test-frontend     # frontend (Vitest) tests
make coverage-backend  # backend + CLI tests, write coverage.xml
make coverage-frontend # frontend tests, write frontend/coverage/
make lint              # ruff format + check
make typecheck         # ty static type checking
make build             # build the SPA into backend/static
make docs              # build the documentation site into site/
make docs-serve        # serve the documentation site with live reload
make dev-worker        # run the agent-run worker on its own
make dev-tray          # run the tray/global-hotkey companion on its own
make run               # start the API, worker, frontend dev server, and tray (free ports from :8600/:5173)
make run-dev           # same as run, with the API reloading on changes
```

`make run` picks the first free port at or above 8600 (API) and 5173 (dev server), and wires the Vite proxy and the tray to the ports it chose, so several checkouts (one per worktree) can run side by side. Pass `ARGS` to override, e.g. `make run-dev ARGS="--api-port 9000 --frontend-port 5300"`, and add `--no-tray` to skip the tray (its global hotkey is best kept to one running stack). The tray is also skipped when there is no display, and a tray or worker that exits does not stop the API and dev server.

Tests run without coverage by default; use `make coverage-backend` / `make coverage-frontend` (or pass `COV="--cov=agentic --cov=agentic_cli --cov-report=term-missing"` to `make test-backend`) when you want it.

`make test-backend` runs pytest across all cores with pytest-xdist; pass `-n0` to `uv run pytest` to run it serially when debugging a single test.

`make run` starts the API (`agentic-server serve`), the worker (`agentic-server worker`), the Vite dev server, and the tray (`agentic-stack`, pointed at the dev server's stack page); `make run-dev` starts the same set with the API reloading on file changes. `agentic` is the separate client.
The worker does not need to reload: restart it to pick up backend changes.
To run the tray on its own, use `make dev-tray` (or `uv run agentic-stack`). On macOS it prompts for Accessibility and Input Monitoring the first time.

## Limitations (v1)

- Single-user, no auth, no multi-tenant isolation.
- Integrations are lightweight: metadata/content pulled on demand, no OAuth
  webhooks or continuous sync.
- Agent runs go through a durable queue: the API only enqueues, and a worker
  (`agentic-server worker`) executes them. A run therefore survives an API or
  worker restart (a worker that dies mid-run is retried once its heartbeat
  lapses), and a retried run resumes the session it recorded as soon as it
  started, so it continues the conversation instead of beginning again. Runs left
  queued or running with no live job are marked failed when the API starts. You
  must run a worker for runs to make progress.
- Permission requests are auto-approved; there is no interactive approval UI yet.
- A merged pull request you authored and a task links is recorded as an accepted
  change automatically, dated to the merge. A run or a git commit still creates
  no change, so the autonomy and yield metrics count only what GitHub reports as
  merged.
