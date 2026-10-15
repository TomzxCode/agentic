# Configuration

The backend reads environment variables prefixed with `AGENTIC_`, or the same keys from a `.env` file in the directory you start the server from (the repository root when you use the Makefile).

`.env.example` in the repository root lists every key with its default.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENTIC_DATA_DIR` | `~/.agentic` | Directory holding the SQLite database. |
| `AGENTIC_DATABASE_URL` | `sqlite:///<data_dir>/agentic.db` | Full database URL. Overrides `AGENTIC_DATA_DIR` when set. |
| `AGENTIC_WORKTREE_ROOT` | `~/.agentic/worktrees` | Where git worktrees are created. |
| `AGENTIC_FS_ROOT` | `~` | Root the repository picker may browse. Use `/` to allow browsing anywhere. |
| `AGENTIC_STATIC_DIR` | `backend/static` | Built SPA for the API to serve. |
| `AGENTIC_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | CORS origins allowed for the Vite dev server. |
| `AGENTIC_DEFAULT_HARNESS` | `opencode` | Fallback harness by name, used when no harness is marked default. |
| `AGENTIC_AUTO_APPROVE_PERMISSIONS` | `true` | Auto-approve ACP permission requests. |
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
| `AGENTIC_SLACK_REFRESH_POLICY` | (empty) | When to re-fetch Slack threads, for example `1d=1h,7d=6h,30d=1d,*=7d`. Empty disables it. |
| `AGENTIC_GITHUB_REFRESH_POLICY` | (empty) | When to re-fetch GitHub issues and pull requests, in the same format. Empty disables it. |
| `AGENTIC_ITEM_REFRESH_TICK` | `300` | Seconds between checks for items that are due. `0` disables the loop. |

Template placeholders:

| Setting | Placeholders |
| --- | --- |
| `AGENTIC_OPENCHAMBER_SESSION_PATH` | `{session}` |
| `AGENTIC_TERMINAL_URL_TEMPLATE` | `{session}`, `{cwd}`, `{harness}` |
| `AGENTIC_EDITOR_URL_TEMPLATE` | `{path}` |
| A harness resume command template | `{session}`, `{cwd}`, `{harness}` |

## Settings overrides

The session-link settings (OpenChamber URL and path, terminal URL template, and editor URL template) can also be set on the **Settings** page.
A stored override wins over the matching environment variable.

The refresh policies are editable under **Settings → Refresh**.

**Agent prompts** are editable under **Settings → Agent prompts**.
Each prompt appears as a button in the agent panel when a task has exactly one associated issue or pull request of the prompt's kind, and clicking it starts a run with the resolved template.
Placeholders: `{owner}`, `{repository}`, `{number}` (filled from the associated GitHub item).
Two prompts are seeded by default: **Review PR** (`$review-pr-full {number} {owner}/{repository}`) and **Triage issue** (`$triage-issue {number} {owner}/{repository}`).
There is no environment variable for these; they live only in the settings store.

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
