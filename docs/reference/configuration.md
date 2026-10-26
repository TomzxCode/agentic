# Configuration

The backend reads environment variables prefixed with `AGENTIC_`, or the same keys from a `.env` file in the directory you start the server from (the repository root when you use the Makefile).
The Slack credentials keep the names `slackx` uses (`SLACK_TOKEN`, `SLACK_COOKIE`, `SLACK_API_BASE_URL`), so one configuration serves both tools; the `AGENTIC_` spellings are accepted too.

`.env.example` in the repository root lists every key with its default.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENTIC_DATA_DIR` | `~/.agentic` | Directory holding the SQLite database. |
| `AGENTIC_DATABASE_URL` | `sqlite:///<data_dir>/agentic.db` | Full database URL. Overrides `AGENTIC_DATA_DIR` when set. |
| `AGENTIC_WORKTREE_ROOT` | `~/.agentic/worktrees` | Where git worktrees are created. |
| `AGENTIC_FS_ROOT` | `~` | Root the repository picker may browse. Use `/` to allow browsing anywhere. |
| `AGENTIC_SDLC_DIR` | `~/.sdlc` | User-global SDLC reviews store the item view reads PR review reports from. |
| `AGENTIC_NOTES_DIR` | `~/notes` | Markdown notes tree holding the colleague-decisions reports the Decisions page reads (`decisions/YYYY/MM/DD.md`). Also read as `NOTES_DIR`. Read-only. |
| `AGENTIC_STATIC_DIR` | `backend/static` | Built SPA for the API to serve. |
| `AGENTIC_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | CORS origins allowed for the Vite dev server. |
| `AGENTIC_DEFAULT_HARNESS` | `opencode` | Fallback harness by name, used when no harness is marked default. |
| `AGENTIC_GITHUB_LOGIN` | (empty) | The GitHub login that counts as "you": a merged PR this account authored and a task links is recorded as a change automatically, and the inbox and a repository's pull requests only offer to record a change for the same PRs. Empty auto-detects the authenticated `gh` account. |
| `SLACK_TOKEN` | (empty) | Slack token the item view's poke action sends with. Also read as `AGENTIC_SLACK_TOKEN`. A web token (`xoxc-`) needs `SLACK_COOKIE` (the `xoxd-` value); a bot token (`xoxb-`) does not. Empty disables poking. |
| `SLACK_COOKIE` | (empty) | The `xoxd-` cookie that goes with an `xoxc-` web token. Also read as `AGENTIC_SLACK_COOKIE`. |
| `SLACK_BOT_TOKEN` | (empty) | Bot token used to post event notifications as a bot instead of as you. Also read as `AGENTIC_SLACK_BOT_TOKEN`. Falls back to `SLACK_TOKEN` when unset. |
| `SLACK_BOT_COOKIE` | (empty) | Cookie paired with an `xoxc-` bot token. Also read as `AGENTIC_SLACK_BOT_COOKIE`. |
| `SLACK_USER_ID` | (empty) | Default recipient for event notifications (a Slack user id, channel id, or channel name). Also read as `AGENTIC_SLACK_USER_ID` and settable under **Settings → Slack**. |
| `SLACK_EVENTS_USER_ID` | (empty) | Preferred recipient for event notifications; overrides `SLACK_USER_ID`. Also read as `AGENTIC_SLACK_EVENTS_USER_ID`. |
| `SLACK_EVENTS_CHANNEL` | (empty) | Channel recipient for event notifications. Also read as `AGENTIC_SLACK_EVENTS_CHANNEL`. |
| `SLACK_NOTIFY_USER_ID` | (empty) | Recipient used for test notifications. Also read as `AGENTIC_SLACK_NOTIFY_USER_ID`. |
| `SLACK_API_BASE_URL` | `https://slack.com/api` | Slack API base event notifications post to. Also read as `AGENTIC_SLACK_API_BASE_URL`. |
| `AGENTIC_GHX_BACKEND` | `cli` | How the server runs `ghx`: `cli` spawns the binary per call, `rpc` calls its JSON-RPC server (start one with `ghx rpc serve`), using the typed methods for reads and `cli.run` for the rest. Also on **Settings → Local tools**, where a change applies without a restart. |
| `AGENTIC_GHX_RPC_URL` | `http://127.0.0.1:8090` | `ghx rpc serve` base URL when the transport is rpc (the JSON-RPC endpoint is `<url>/rpc`). Also on **Settings → Local tools**. |
| `AGENTIC_GHX_RPC_TOKEN` | (empty) | Bearer token sent to the `ghx rpc serve` server. Only needed when it is bound beyond loopback. Also on **Settings → Local tools**. |
| `AGENTIC_SLACKX_BACKEND` | `cli` | How the server runs `slackx`: `cli` spawns the binary per call, `rpc` calls its JSON-RPC server (start one with `slackx rpc serve`), using the typed methods for reads and `cli.run` for the rest. Also on **Settings → Local tools**, where a change applies without a restart. |
| `AGENTIC_SLACKX_RPC_URL` | `http://127.0.0.1:8280` | `slackx rpc serve` base URL when the transport is rpc (the JSON-RPC endpoint is `<url>/rpc`). Also on **Settings → Local tools**. |
| `AGENTIC_SLACKX_RPC_TOKEN` | (empty) | Bearer token sent to the `slackx rpc serve` server. Only needed when it is bound beyond loopback. Also on **Settings → Local tools**. |
| `AGENTIC_RPC_TOKEN` | (empty) | Bearer token required by this server's own JSON-RPC endpoint (`POST /rpc`) when it is bound beyond loopback. Clients send it as `Authorization: Bearer <token>`. |
| `AGENTIC_RPC_ALLOW_EXEC` | `true` | Allow the `cli.run` JSON-RPC method, which runs the `agentic` CLI on the server. |
| `AGENTIC_AUTO_APPROVE_PERMISSIONS` | `true` | Auto-approve ACP permission requests. |
| `AGENTIC_WARM_HARNESS_SESSION` | `true` | Hold an ACP session open for the default harness from API startup, so the task view lists its model choices without spawning it. Runs still spawn their own session. |
| `AGENTIC_QUEUE_URL` | `sqlite:///<data_dir>/queue.db` | Agent-run queue. Use a `redis://` or `postgres://` URL to share the queue across machines. |
| `AGENTIC_WORKER_CONCURRENCY` | `4` | Agent runs a worker processes concurrently. |
| `AGENTIC_WORKER_SWEEP` | `60` | Seconds between sweeps for stuck jobs left by a dead worker. |
| `AGENTIC_JOB_TIMEOUT` | `0` | Per-run job timeout in seconds. `0` disables it. |
| `AGENTIC_JOB_HEARTBEAT` | `120` | Seconds a job may go untouched before a sweep retries it. |
| `AGENTIC_JOB_RETRIES` | `1` | Times a run is retried after a failure or a dead worker. |
| `AGENTIC_OPENCHAMBER_URL` | (unset) | Base URL for **Open in OpenChamber** links. |
| `AGENTIC_OPENCHAMBER_SESSION_PATH` | `/?session={session}` | Path appended to the OpenChamber base. |
| `AGENTIC_TERMINAL_URL_TEMPLATE` | (unset) | URL template for **Open in terminal** links. |
| `AGENTIC_EDITOR_URL_TEMPLATE` | (unset) | URL template for the worktree **Open in editor** button. |
| `AGENTIC_GHX_URL` | (unset) | Base URL of the ghx web UI (`ghx serve`, default port 8080). When set, GitHub items link into it. A `managed` transport supplies it, since the server runs the UI itself. |
| `AGENTIC_SLACKX_URL` | (unset) | Base URL of the slackx web UI (`slackx serve`, default port 8280). When set, Slack items link into it. A `managed` transport supplies it, since the server runs the UI itself. |
| `AGENTIC_SLACK_REFRESH_POLICY` | (empty) | When to re-fetch Slack threads, for example `1d=1h,7d=6h,30d=1d,*=7d`. Empty disables it. |
| `AGENTIC_GITHUB_REFRESH_POLICY` | (empty) | When to re-fetch GitHub issues and pull requests, in the same format. Empty disables it. |
| `AGENTIC_ITEM_REFRESH_TICK` | `300` | Seconds between checks for items that are due. `0` disables the loop. |
| `AGENTIC_REVIEW_SCAN_INTERVAL` | `1h` | How often the review scan asks GitHub which pull requests await your review. A duration such as `30m`, `1h` or `1d`; empty disables the scan. |
| `AGENTIC_REVIEW_SCAN_TICK` | `300` | Seconds between checks for whether the review scan is due. `0` disables the loop. |
| `AGENTIC_REVIEW_SCAN_DEFAULT` | `include` | What a repository with no review-scan policy of its own does: `include` (scan every repository except the excluded ones) or `exclude` (scan only the repositories marked include). |
| `AGENTIC_REVIEW_SCAN_LIMIT` | `100` | How many results each of the review scan's two searches returns. |
| `AGENTIC_REVIEW_SCAN_EXCLUDE_AUTHORS` | `dependabot[bot]` | Comma-separated logins the review scan leaves out of its results. |
| `AGENTIC_REVIEW_SLO` | (empty) | How long a pull request may await your review before the inbox flags it. A duration such as `8h` or `1d`; empty disables it. Measured from when the scan first saw the pull request waiting. |
| `AGENTIC_REVIEW_NUDGE_SLO` | (empty) | How long a pull request of yours may wait without any review from anyone before the inbox offers to poke its reviewers on Slack. A duration such as `1h30m` or `1d`; empty disables it. Measured from when the pull request was opened. |
| `AGENTIC_SCHEDULED_TASK_TICK` | `30` | Seconds between checks for scheduled shell tasks that are due. `0` disables the loop. |
| `AGENTIC_SCHEDULED_TASK_TIMEOUT` | `3600` | Seconds a scheduled shell task may run before it is stopped and marked failed. |

Template placeholders:

| Setting | Placeholders |
| --- | --- |
| `AGENTIC_OPENCHAMBER_SESSION_PATH` | `{session}` |
| `AGENTIC_TERMINAL_URL_TEMPLATE` | `{session}`, `{cwd}`, `{harness}` |
| `AGENTIC_EDITOR_URL_TEMPLATE` | `{path}` |
| A harness resume command template | `{session}`, `{cwd}`, `{harness}` |

## Settings overrides

The session-link settings (OpenChamber URL and path, terminal URL template, and editor URL template) can also be set on the **Settings** page.
The ghx and slackx settings are under **Settings → Local tools**: the web UI base URLs, and how the server runs each tool (`cli` spawns the binary per call, `rpc` asks the tool's JSON-RPC server instead, started with `ghx rpc serve` or `slackx rpc serve`; reads go through the server's typed methods, so they answer in-process instead of spawning a child per call).
`managed` starts the tool's serve process from this server instead, so its web UI URL is shown as a link to open rather than as a field, and it fills in that tool's web UI URL for item links.
The transport is read per call, so a change there applies without a restart, also for the worker that runs agents.
A stored override wins over the matching environment variable.

The GitHub login is editable under **Settings → Identity**; leave it blank to fall back to the authenticated `gh` account.

The refresh policies are editable under **Settings → Refresh**.

The review scan is editable under **Settings → Review requests**: how often it runs (`review_scan_interval`), the review SLO (`review_slo`), and what a repository with no policy of its own does (`review_scan_default`).
Each registered repository can also be set to include or exclude on its own.
See [How to read the review queue](../how-to/review-pull-requests.md).

**Agent prompts** are editable under **Settings → Agent prompts**.
Each prompt appears as a button in the agent panel when a task has exactly one associated issue or pull request of the prompt's kind, and clicking it starts a run with the prompt's variables resolved.
Variables come from the task (`{task_id}`, `{title}`, `{description}`, `{status}`, `{priority}`, `{deadline}`, `{tags}`, `{task_url}`, `{people}`, `{requested_by}`, `{repositories}`, `{worktree}`) and from the associated GitHub item (`{owner}`, `{repository}`, `{number}`, `{item_url}`, `{item_title}`, `{item_author}`, `{item_state}`).
The panel lists every variable and inserts it at the cursor.
When a task links several items, each gets a short id and the item fields become `{li.a.item_url}`, `{li.a.number}`, and so on; `{li.a}` alone is `owner/repository#number`.
Submitting a message also attaches a context block naming the task and the linked items the current view is about (the issue in the issue view, the pull requests in the PR view); a command (a message starting with `$` or `/`) is left as-is.
Two prompts are seeded by default: **Review PR** (`$review-pr-full {number} {owner}/{repository}`) and **Triage issue** (`$triage-issue {number} {owner}/{repository}`).
There is no environment variable for these; they live only in the settings store.

**Diagnostics** under **Settings → Diagnostics** lists the external commands the app runs: the server's Python interpreter, `git`, `ghx`, `gh`, `slackx`, and every configured harness.
For each one it shows whether the command is on `PATH`, where it resolved, and the version it reports.
Below those it dumps the two local caches: the repositories `ghx` has cached (issue and pull-request counts, cache age, whether each is stale, and the cache hit rate per retrieval operation) and `slackx`'s cache database (the workspace it belongs to, its file path, and the entity counts with when each was last updated).
The section is read-only and probes on demand, when you open it or press **Recheck**.

## Refresh policy format

A refresh policy is a comma-separated list of `age=interval` bands, with an optional `*` fallback, for example:

```text
1d=1h,7d=6h,30d=1d,*=7d
```

Omit the `*` band, or write `*=never`, to stop refreshing once an item outgrows the last band.
An empty policy disables that source.
An item's age is its upstream creation time when known, and otherwise the time it was recorded.

## Related

- [How to configure session links](../how-to/configure-session-links.md)
- [How to refresh items on a schedule](../how-to/refresh-items.md)
