# Memory

## 2026-10-10: the domain entity is Task (renamed from Problem)

- Everything user-facing and internal uses "task": model `Task`, table `task`, columns `task_id` (association/worktree/agentrun/timelineevent), API `/api/tasks`, CLI `agentic task`, SPA routes `/task/:id`. `db._migrate_problem_to_task()` renames an existing database in place (table, FK columns, timeline messages) and must run before `create_all`, otherwise `create_all` would create an empty `task` table and orphan the data.

## 2026-10-10: Agentic (tasks + agents app) foundations

- Stack was chosen with the user: FastAPI + SQLModel/SQLite, Vue 3 + Vite + vite-plugin-pwa, single-user local-first, lightweight integrations (metadata/content pulled on demand, no OAuth).
- Harness abstraction is **ACP (Agent Client Protocol) over stdio** via the `agent-client-protocol` Python SDK. A harness is a `harness` table row (command + args); do not special-case individual agents in code. `opencode acp` and `pi-acp` both verified working.
- Data model centers on `Task`; external things are `SourceItem`s linked via `Association` (many-to-many). Worktrees and agent runs hang off a task; every change writes a `TimelineEvent`.
- Context refresh parses a JSON `{summary, next_steps}` out of the agent's reply. Parse **only `message` events, never `thought`**: opencode interleaves them on the same stream, so concatenating both corrupts the JSON. Extraction must also salvage truncated JSON (models do hit output limits).

## 2026-10-10: ACP runner gotchas

- After the prompt turn completes, terminate the harness process (`process.terminate()` + bounded `wait`). Waiting for it to exit on its own hangs: `opencode acp` stays alive until stdin closes.
- `pkill -f "agentic --host"` matches the invoking shell's own command line and kills it. Kill the server by PID discovered from the listening port instead.
- The backend serves `backend/static` (the Vite build output) as the SPA; `frontend/vite.config.js` writes its build there directly.
- SQLite runs with `PRAGMA foreign_keys=ON`, but SQLModel/SQLAlchemy does **not** order ORM `session.delete()` calls to satisfy FK constraints. Deletes that touch parents must use explicit, ordered `session.execute(sa_delete(...))` statements (see `routers/tasks.py`).
- `opencode acp` turn latency is variable (10s to 60s+ for a one-word reply); do not treat a run that is still `running` after a minute as hung.
- Frontend is mobile-first below 760px: the sidebar becomes an off-canvas drawer toggled by `.topbar .menu-btn`. When adding a class that sets `display` on an element that also has `.btn`, scope it to `.topbar <class>` (or place it after `.btn`): `.btn { display: inline-flex }` otherwise wins on source order and the hidden element shows.
- Session links: OpenChamber opens a session at `<base>/?session=<id>` (web) or `openchamber://session/<id>` (native deep link); both are `base` + `openchamber_session_path`. The resume command lives on `Harness.resume_command` (a template), because the harness command (e.g. `pi-acp`) is not the CLI to resume with (e.g. `pi`).
- SQLModel's `create_all` only creates missing tables, it never adds columns. New columns on existing tables need `_ensure_columns()` in `db.py` (a plain `ALTER TABLE`), plus a backfill for seeded rows when a column gains a default.
- Two console scripts, two packages: `agentic` (the `agentic-cli` package in `cli/`) is the user client over HTTP; `agentic-server` (the `agentic` backend package in `backend/`) runs and inspects the server. A uv workspace at the repo root (`members = ["backend", "cli"]`, root `package = false`) installs both into one `.venv`; the root lists both as dependencies so a plain `uv sync` installs their console scripts. Run tests/lint from the repo root.
- `cli/src/agentic_cli/cli.py` is the cyclopts app whose global flags (`--api-url`, `--format`, `--timeout`) live on `app.meta.default`. Inside the launcher, `app(tokens)` returns the command's value instead of printing it, so the launcher must `return app(tokens)` or output is silently dropped.
- Cyclopts prints command return values through Rich: markup eats `[open]`-style text and the default width wraps long output (breaking piped JSON). The CLI pins a plain `Console(markup=False, soft_wrap=True)`.
- Concurrent `uv run` invocations against this project can re-sync the venv and kill a background server; run the server with `uv run --no-sync` (or the venv binary) when also running CLI commands.
- The repository picker is a **server-side** directory browser (`GET /api/fs/list`, `DirectoryPicker.vue`), not a browser file input: a browser `<input webkitdirectory>` never reveals absolute server paths. Browsing is confined to `settings.fs_root` (default `~`); the picker adds several folders via `POST /api/repositories/bulk`.
- Repository groups (`RepositoryGroup` + `RepositoryGroupMember`, plus nullable `Task.group_id`) name a set of repositories; the group's name/description/paths are injected into the context-refresh prompt by `build_context_prompt` so the agent knows which checkouts may be relevant. Deleting a group detaches tasks (sets `group_id` null); deleting a repository removes its group memberships. New columns on existing tables still need `_ensure_columns` (`task.group_id` was added that way).
- An item's source (`slack`/`github`/`gdrive`/`url`/`note`) is inferred from the value by `infer_item_source` in `services.py`; the UI and CLI omit it (`ItemCreate.source` is optional). An explicit source still wins. Text that is not a URL (per `looks_like_url`: needs a scheme or a bare domain, and no spaces) is a `note`: `_upsert_item` moves it into `content` and leaves `url` null rather than storing a bogus link.
- Task creation can import a GitHub issue: `TaskCreate.github_url` makes `create_task` fetch the issue (via `ghx`), fill title/description, and link it as an item. The picker uses `GET /api/github/issues` (by `repository_id`, resolved through the repo's GitHub remote, or explicit `owner`/`repo`).
- All GitHub access goes through **`ghx`** (`ghx issue list`, `ghx issue view`, `ghx pr view`), never `gh`. ghx's `--json` is a boolean that emits the whole object (no field list), and the repo selector is the global `-R/--repo`. Its JSON field names match gh's (`number`, `title`, `state`, `author.login`, `labels[].name`, `url`, `body`).
