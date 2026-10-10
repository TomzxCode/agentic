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
- Frontend is mobile-first below 760px: the sidebar becomes an off-canvas drawer toggled by `.topbar .menu-btn`. When adding a class that sets `display` on an element that also has `.btn`, scope it to `.topbar <class>` (or place it after `.btn`): `.btn { display: inline-flex }` otherwise wins on source order and the hidden element shows.
- Session links: OpenChamber opens a session at `<base>/?session=<id>` (web) or `openchamber://session/<id>` (native deep link); both are `base` + `openchamber_session_path`. The resume command lives on `Harness.resume_command` (a template), because the harness command (e.g. `pi-acp`) is not the CLI to resume with (e.g. `pi`).
- SQLModel's `create_all` only creates missing tables, it never adds columns. New columns on existing tables need `_ensure_columns()` in `db.py` (a plain `ALTER TABLE`), plus a backfill for seeded rows when a column gains a default.
- The CLI is split in two console scripts: `agentic` (user client, over HTTP) and `agentic-server` (runs/inspects the backend). `agentic/cli.py` is the cyclopts app whose global flags (`--api-url`, `--format`, `--timeout`) live on `app.meta.default`. Inside the launcher, `app(tokens)` returns the command's value instead of printing it, so the launcher must `return app(tokens)` or output is silently dropped.
- Cyclopts prints command return values through Rich: markup eats `[open]`-style text and the default width wraps long output (breaking piped JSON). The CLI pins a plain `Console(markup=False, soft_wrap=True)`.
- Concurrent `uv run` invocations against this project can re-sync the venv and kill a background server; run the server with `uv run --no-sync` (or the venv binary) when also running CLI commands.
