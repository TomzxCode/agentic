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

## Concepts

| Concept | What it is |
| --- | --- |
| **Problem** | The unit of work. Everything hangs off it. Carries an agent-maintained `summary` and `next_steps`. |
| **Item** | Something external: a Slack thread, GitHub issue/PR, Drive doc, URL, note, or commit. Items are deduplicated by URL / external id. |
| **Association** | A link between an item and a problem (many-to-many), with a note. |
| **Worktree** | An isolated `git worktree` created for a problem from a registered repository. |
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
# 1. Backend (API on :8600)
cd backend
uv sync
uv run agentic --host 127.0.0.1 --port 8600 --reload

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
cd ../backend && uv run agentic --host 127.0.0.1 --port 8600
```

Open http://127.0.0.1:8600. The PWA installs from there.

## Using it

1. **Create a problem** (the `+` in the sidebar).
2. **Associate items**: paste a Slack thread permalink, a GitHub issue/PR URL, a
   Drive doc, or write a note. GitHub and Slack/URL items are fetched on demand
   (via `gh` and `slackx` for Slack); you can also paste content directly.
3. **Add a repository** in Settings, then create a **worktree** for the problem.
4. **Refresh with agent** to generate the current summary and next steps.
5. **Run an agent** against the problem; the transcript streams live.

## Configuration

Environment variables (prefix `AGENTIC_`) or `backend/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENTIC_DATA_DIR` | `~/.agentic` | SQLite DB location. |
| `AGENTIC_WORKTREE_ROOT` | `~/.agentic/worktrees` | Where worktrees are created. |
| `AGENTIC_STATIC_DIR` | `backend/static` | Built SPA to serve. |
| `AGENTIC_DEFAULT_HARNESS` | `opencode` | Harness used when a problem doesn't pick one. |
| `AGENTIC_AUTO_APPROVE_PERMISSIONS` | `true` | Auto-approve ACP permission requests. |

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
GET/POST            /api/harnesses   /api/repositories   /api/items
```

## Development

```bash
make test        # backend tests
make lint        # ruff format + check
make build       # build the SPA into backend/static
make run         # serve API + built SPA on :8600
```

## Limitations (v1)

- Single-user, no auth, no multi-tenant isolation.
- Integrations are lightweight: metadata/content pulled on demand, no OAuth
  webhooks or continuous sync.
- Agent runs are in-process; restarting the API drops in-flight runs (the
  transcript already written is kept).
- Permission requests are auto-approved; there is no interactive approval UI yet.
