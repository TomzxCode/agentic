# Agentic

Track work as **problems**, associate the Slack threads, GitHub issues/PRs, and
Google Drive docs that feed them, spin up git worktrees to work on them, and let
a coding agent keep a current summary and next-steps list so resuming is quick.

- **Backend**: FastAPI + SQLModel (SQLite), single-user and local-first.
- **Agents**: any [ACP](https://agentclientprotocol.com/) harness. OpenCode
  (`opencode acp`) and pi (`pi-acp`) are preconfigured; add more in Settings.
- **Frontend**: Vue 3 + Vite, built as an installable PWA and served by the API.
  Responsive down to phones: the problem list becomes an off-canvas drawer and
  the detail view stacks into a single column.
- **CLI**: `agentic` drives the whole API (problems, links, worktrees, runs,
  context) with JSON output, so agents can create and maintain the content.
  `agentic-server` runs and inspects the backend itself.

## Layout

A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) with
two Python packages and the SPA:

| Path | Package | Command | Role |
| --- | --- | --- | --- |
| `backend/` | `agentic` | `agentic-server` | FastAPI API, ACP agent runner, DB |
| `cli/` | `agentic-cli` | `agentic` | HTTP client that drives the API |
| `frontend/` | — | — | Vue 3 + Vite PWA served by the API |

`uv sync` at the root installs both packages and their console scripts into one
virtualenv.

## Concepts

| Concept | What it is |
| --- | --- |
| **Problem** | The unit of work. Everything hangs off it. Carries an agent-maintained `summary` and `next_steps`. |
| **Item** | Something external: a Slack thread, GitHub issue/PR, Drive doc, URL, note, or commit. Items are deduplicated by URL / external id. |
| **Association** | A link between an item and a problem (many-to-many), with a note. |
| **Worktree** | An isolated `git worktree` created for a problem from a registered repository. |
| **Repository group** | A named set of repositories. Picking one on a problem tells the agent those checkouts may hold information relevant to it. |
| **Agent run** | One prompt sent to a harness in a working directory. Events stream live to the UI. |
| **Context refresh** | A special agent run that reads the problem + its items and writes the `summary` and `next_steps`. |

Every meaningful change writes a **Timeline event**, so a problem's evolution is
visible at a glance.

## How agents are wired

The backend speaks **ACP (Agent Client Protocol) over stdio**. That is the
abstraction that lets you switch harnesses without touching app code: each
harness is just a command row in the `harness` table.

```
FastAPI ──spawn──▶ opencode acp   ┐
   ▲                pi-acp        ├── ACP JSON-RPC over stdio ──▶ agent
   │              (your harness)  ┘
   └── SSE ◀── normalized events (message / thought / tool_call / plan / usage)
```

Default harnesses (seeded on first run):

| Id | Command | Notes |
| --- | --- | --- |
| `opencode` | `opencode acp` | Default. |
| `pi` | `pi-acp` | `pi` via the pi-acp adapter. |

## Quickstart

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, and at
least one harness on your `PATH` (`opencode` and/or `pi-acp`).

```bash
# 1. Backend + CLI (API on :8600), from the repository root
uv sync
uv run agentic-server serve --host 0.0.0.0 --port 8600 --reload

# 2. Frontend (dev server on :5173, proxies /api to :8600)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Single-app mode

Build the SPA into `backend/static` and let FastAPI serve everything:

```bash
cd frontend && npm run build      # writes ../backend/static
uv run agentic-server serve --host 0.0.0.0 --port 8600   # from the repo root
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

1. **Create a problem** (the `+` in the sidebar); optionally pick a
   **repository group** so the agent knows which checkouts to consider.
2. **Associate items**: paste a Slack thread permalink, a GitHub issue/PR URL, a
   Drive doc, or write a note. The source (Slack/GitHub/Drive/URL/note) is
   inferred from what you paste. GitHub and Slack/URL items are fetched on demand
   (via `gh` and `slackx` for Slack); you can also paste content directly.
3. **Add repositories** in Settings. Use **Browse…** to pick folders on the
   machine (select several at once); git repositories are marked. Group related
   repositories (**Repository groups**) so a problem can point the agent at
   them. Then create a **worktree** for the problem.
4. **Refresh with agent** to generate the current summary and next steps.
5. **Run an agent** against the problem; the transcript streams live.

## Open a session in a terminal or OpenChamber

When a run has a session id, the app shows links to reopen that session:

- **Open in OpenChamber** opens `<openchamber_url><openchamber_session_path>`,
  defaulting to `http://your-host:3001/?session=<id>`. For the native app use
  base `openchamber://session` with path `/{session}`.
- **Open in terminal** opens your configured `terminal_url_template` (any URL
  scheme, or a web terminal).
- **Copy resume command** copies something like
  `cd <worktree> && opencode --session <id>` for pasting into a shell.

Configure the base URLs on the **Settings** page (persisted locally) or with
environment variables. Each harness has an editable resume command template.
Placeholders: `{session}`, `{cwd}`, `{harness}`.

## Configuration

Environment variables (prefix `AGENTIC_`) or `backend/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENTIC_DATA_DIR` | `~/.agentic` | SQLite DB location. |
| `AGENTIC_WORKTREE_ROOT` | `~/.agentic/worktrees` | Where worktrees are created. |
| `AGENTIC_FS_ROOT` | `~` | Root the repository picker may browse (`/` for anywhere). |
| `AGENTIC_STATIC_DIR` | `backend/static` | Built SPA to serve. |
| `AGENTIC_DEFAULT_HARNESS` | `opencode` | Harness used when a problem doesn't pick one. |
| `AGENTIC_AUTO_APPROVE_PERMISSIONS` | `true` | Auto-approve ACP permission requests. |
| `AGENTIC_OPENCHAMBER_URL` | (unset) | Base URL for "Open in OpenChamber" links. |
| `AGENTIC_OPENCHAMBER_SESSION_PATH` | `/?session={session}` | Path appended to the base. |
| `AGENTIC_TERMINAL_URL_TEMPLATE` | (unset) | URL template for "Open in terminal" links. |

All three session-link settings can also be overridden on the Settings page;
the stored override wins over the environment variable.

## CLI

Two command-line tools are installed:

- **`agentic`** — the user client. Talks to a running API over HTTP, so agents
  can drive the app's content without touching the database.
- **`agentic-server`** — the backend. Runs the server and reports its config.

### User client

```bash
agentic --help                       # everything, grouped by resource
agentic problem create --title "Fix the flaky ingest test"
agentic problem list --status open
agentic link add <problem> --url https://github.com/o/r/issues/482
agentic link add <problem> --item-id <item>
agentic worktree create <problem>
agentic context refresh <problem>    # agent rewrites summary + next steps
agentic run create <problem> --prompt "Investigate the failure"
agentic run wait <run-id>            # block until it finishes
agentic run stream <run-id>          # live transcript
```

Commands return data. Output is JSON when piped (or with `--format json`) and
human-readable text otherwise (`--format text`). Point it elsewhere with
`--api-url` or `AGENTIC_API_URL`:

```bash
AGENTIC_API_URL=http://box:8600 agentic problem list | jq '.[].id'
```

Resources: `problem`, `item`, `link`, `repository`, `worktree`, `run`,
`context`, `harness`, `settings`, plus `health`.

### Backend

```bash
agentic-server                  # start the server (same as: agentic-server serve)
agentic-server serve --reload
agentic-server info             # data dir, database, harness availability
```

## API sketch

```
GET/POST            /api/problems
GET/PATCH/DELETE    /api/problems/{id}
POST                /api/problems/{id}/items            (associate)
POST                /api/problems/{id}/worktrees
POST                /api/problems/{id}/runs
POST                /api/problems/{id}/context/refresh
GET                 /api/problems/{id}/stream           (SSE: problem changes)
GET                 /api/runs/{id}/stream               (SSE: agent transcript)
GET/PATCH           /api/settings                        (session-link config)
GET                 /api/fs/list                         (repository picker)
POST                /api/repositories/bulk               (add several at once)
GET/POST/PATCH/DELETE /api/groups                        (repository groups)
GET/POST/PATCH      /api/harnesses   /api/repositories   /api/items
```

## Development

```bash
make test        # backend tests
make lint        # ruff format + check
make build       # build the SPA into backend/static
make run         # serve API + built SPA on :8600
```

`make run` uses `agentic-server serve`; `agentic` is the separate client.

## Limitations (v1)

- Single-user, no auth, no multi-tenant isolation.
- Integrations are lightweight: metadata/content pulled on demand, no OAuth
  webhooks or continuous sync.
- Agent runs are in-process; restarting the API drops in-flight runs (the
  transcript already written is kept).
- Permission requests are auto-approved; there is no interactive approval UI yet.
