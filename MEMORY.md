# Memory

## 2026-10-10: Agentic (problems + agents app) foundations

- Stack was chosen with the user: FastAPI + SQLModel/SQLite, Vue 3 + Vite + vite-plugin-pwa, single-user local-first, lightweight integrations (metadata/content pulled on demand, no OAuth).
- Harness abstraction is **ACP (Agent Client Protocol) over stdio** via the `agent-client-protocol` Python SDK. A harness is a `harness` table row (command + args); do not special-case individual agents in code. `opencode acp` and `pi-acp` both verified working.
- Data model centers on `Problem`; external things are `SourceItem`s linked via `Association` (many-to-many). Worktrees and agent runs hang off a problem; every change writes a `TimelineEvent`.
- Context refresh parses a JSON `{summary, next_steps}` out of the agent's reply. Parse **only `message` events, never `thought`**: opencode interleaves them on the same stream, so concatenating both corrupts the JSON. Extraction must also salvage truncated JSON (models do hit output limits).

## 2026-10-10: ACP runner gotchas

- After the prompt turn completes, terminate the harness process (`process.terminate()` + bounded `wait`). Waiting for it to exit on its own hangs: `opencode acp` stays alive until stdin closes.
- `pkill -f "agentic --host"` matches the invoking shell's own command line and kills it. Kill the server by PID discovered from the listening port instead.
- The backend serves `backend/static` (the Vite build output) as the SPA; `frontend/vite.config.js` writes its build there directly.
- SQLite runs with `PRAGMA foreign_keys=ON`, but SQLModel/SQLAlchemy does **not** order ORM `session.delete()` calls to satisfy FK constraints. Deletes that touch parents must use explicit, ordered `session.execute(sa_delete(...))` statements (see `routers/problems.py`).
- `opencode acp` turn latency is variable (10s to 60s+ for a one-word reply); do not treat a run that is still `running` after a minute as hung.
