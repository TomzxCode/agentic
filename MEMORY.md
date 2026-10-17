# Memory

## 2026-10-17: creating a GitHub issue goes through `gh`, not ghx

- `ghx` has no issue-create command (only comment, list, view), so `POST /api/github/issues` and `services.create_github_issue` shell out to `gh issue create --repo owner/repo --title T --body B` and read the new issue's URL from stdout. This is the one GitHub write that bypasses ghx; every read still uses ghx.
- The task view's "Create GitHub issue" button creates from the task's title/description without a dialog: exactly one task-linked GitHub repository creates immediately, zero or several reveal an inline picker (the same `SearchSelect` variant the repository property uses), and the new issue is then associated to the task as an item.
- A task's `repository_ids` may include non-GitHub repositories; only those whose `remote_url` contains `github.com` are offered or used.

## 2026-10-15: the CLI reads no env vars; only its flags work

- `AGENTIC_API_URL`, `AGENTIC_FORMAT`, and `AGENTIC_TIMEOUT` are read into `CONTEXT` at import, but `app.meta.default` in `cli.py` declares `api_url`/`format`/`timeout` with hardcoded defaults and calls `CONTEXT.update(...)`, which overwrites them, so all three env vars are ignored. The docstring, `client.py`, and the README claim otherwise; pass `--api-url`/`--format`/`--timeout` explicitly.
- `Settings` loads `.env` relative to the process working directory (`env_file=".env"`), so `backend/.env` is not read when the server runs from the repo root even though `.env.example` says to copy it there. Put the file where you start the server, or export the variables.

## 2026-10-15: UI-only layout preferences live in localStorage, not /api/settings

- The desktop sidebar width is a per-device preference (`agentic.sidebarWidth`, 260-560px), read and written in `App.vue`. Keep device-specific UI state (size, position, open/closed) in localStorage: the `setting` table is the server's state and is shared by every client, so a width there would fight across devices.
- 260px is the sidebar's floor because the bottom Search/New task row and the nav icon row start clipping below it; if that nav grows, re-measure before lowering the minimum.
- The sidebar's visibility has two separate states on purpose: `sidebarOpen` is the transient mobile drawer (reset on every navigation) and `sidebarHidden` is the persisted desktop preference. Collapsing them makes either a route change hide the desktop column, or a drawer close persist as a desktop preference.
- The desktop toggle is a floated element inside `.main`, not fixed chrome: that is what puts it at the page's left edge on the title's line with the title indented and the rest of the page at the edge, with no per-view markup. It therefore scrolls with the page; `data-no-hint` keeps it out of the focus-hint badges, which are scanned from `.main`.

## 2026-10-15: a screen-edge swipe never reaches the page on mobile

- Android's system back gesture (and iOS Safari's edge back-swipe) owns the outer ~25px of the screen edge and consumes a touch that starts there before the page sees it, so an edge-triggered drawer or carousel cannot be made reliable by widening the zone. The sidebar drawer opens on a rightward swipe from anywhere on the page instead (`App.vue`), which also steers around the Gantt and dependency graph strips that scroll sideways.
- Touch sampling drifts sideways at the start of a swipe, so an axis lock must not be decided from one sample: require the horizontal travel to pass a threshold and to dominate the sideways travel before claiming the gesture, otherwise a thumb that drifts down first kills the swipe.

## 2026-10-13: the owner's live dev server is on :8600 (~/.agentic); ad-hoc CLI runs can miss AGENTIC_API_URL

- `make run` starts the API on `:8600` backed by `~/.agentic` (the real database). A scratch/test server must set `AGENTIC_DATA_DIR=/tmp/...`; the env var does work for `agentic-server`.
- A mid-script `export AGENTIC_API_URL=...` before `uv run agentic ...` is not reliably picked up, so an ad-hoc CLI call can silently hit `:8600` and write to the real database. Pass `--api-url` explicitly (or prefix the command with the var) and confirm the target before mutating.

## 2026-10-13: the focus stack is a separate StackEntry + TaskSession, not Task fields

- The stack is its own model: `StackEntry` (task_id, position, is_current, deleted_at) plus `TaskSession` (started_at/ended_at), so a task can exist without being queued and its stack history survives independently. Position 0 is current; every mutation re-derives `is_current` and opens/closes sessions in `stack.py`, and `execution_count`/`duration` are computed from sessions and never stored.
- The stack is materialized from the in-flight tasks: `sync_stack` (called at the top of every `/api/stack` endpoint) appends an entry at the bottom for any open/in-progress/blocked task that has never had one, and soft-deletes the entry when a task leaves those statuses. A task that was popped or removed keeps its soft-deleted entry, so it is not re-added until pushed again. Because of this, stack tests must clear tasks, not just entries (the `test_stack.py` fixture deletes every task).
- `pop` (the tray's "Mark Done") sets the task status to `done`; `remove` (Backspace) soft-deletes the entry only. Both keep the entry in `/api/stack/history`. `TaskSession` and `StackEntry` rows must be deleted before the task (FK order) in `delete_task`.
- The tray/global-hotkey piece is a separate `launcher/` workspace member (`agentic-stack`, pystray + pynput) that only opens the PWA stack page and pops over HTTP; the stack UI itself is the SPA route `/stack`. On macOS the pynput listener runs in a subprocess to avoid the AppKit runloop clash (the same reason task-stack isolated it).

## 2026-10-13: list rows render through shared card components

- Every `.item` list row is built from `EntityCard.vue` (header row with lead/title/title-extra/actions slots, body, meta), so repositories, people, harnesses, worktrees, runs, and groups share one layout instead of each view styling its own. Items use `ItemCard.vue` and tasks use `TaskCard.vue`, both wrapping `EntityCard`. A reference to a task or item from another entity (a person, a repository item) uses `TaskLink.vue` / `ItemLink.vue`, not a hand-written button. Add a new list row by composing these rather than writing `.item` markup by hand.
- `store.sourceLabel` is the single source of item-source labels (GitHub, Slack, …); the old per-view `SOURCE_LABELS` map is gone. `TaskCard` owns the status picker, priority icon, person/tag filter chips, deadline badge, and age, so task rows are identical wherever they appear.

## 2026-10-13: the default harness is an is_default row, not AGENTIC_DEFAULT_HARNESS

- `Harness.is_default` (at most one row) is the harness a run uses when a task picks none; `AGENTIC_DEFAULT_HARNESS` is now only a name fallback for when no row is flagged. `seed_harnesses` picks it once (installed `opencode2`, else `opencode`) and records the non-overridable key `harness_default_seeded` in the `setting` table, so a later choice made in Settings is never overwritten.
- `GET /api/harnesses` reports `is_default` per harness and `PATCH /api/harnesses/{id}` demotes the others, which is what the Settings page uses. The marker row is not in `OVERRIDABLE_KEYS`, so it is invisible to the settings API (do not expect to see it under `/api/settings`).

## 2026-10-13: harness model is selected over ACP, never via a CLI flag

- A harness's `model` is applied with ACP `session/set_config_option(config_id="model", ...)` right after the session is created or resumed (`_apply_model` in `agents.py`). `opencode acp`/`opencode2 acp` reject `--model` as an unknown flag and the process fails to start, so the old "append `--model` to args" wiring was broken. `new_session` returns the model list and current value under `configOptions` (id `model`), and `set_config_option` changes it.
- A harness that lacks a model config option (pi) or rejects the value logs a warning and emits a `warning` transcript event, then runs with its own default; the setting never fails a run.
- `Harness.model` is editable per harness in Settings → Agent harnesses and shown in the run harness picker; blank means the harness default. The CLI `harness create/update --model` was already wired.

## 2026-10-12: opencode ACP defaults to its own model, not the CLI's

- `opencode acp` creates sessions with opencode's built-in default model (observed `opencode/big-pickle`), which is independent of the model `opencode run` resolves (observed `zai-coding-plan/glm-5.3`). With no valid `opencode` provider credential, that default fails with `Upstream request failed: Invalid credential`, and the ACP turn errors.
- The ACP model is selectable (see the 2026-10-13 entry); setting `"model"` in `~/.config/opencode/opencode.json` (this machine uses `zai-coding-plan/glm-5.3`) changes the default that `new_session` reports. A project-local `.opencode/opencode.json` in the run cwd works too, but agentic's cwd varies (worktree root or a repository).

## 2026-10-12: factory metrics are computed from explicit change records

- A `change` is recorded explicitly (CLI `agentic change`, `POST /api/changes`); nothing auto-creates one from an agent run, commit, or PR yet, so autonomy and yield are only as complete as what is recorded.
- autonomy_rate = touchless accepted changes / accepted changes in the window; yield = accepted changes not reverted / accepted changes whose observation window has elapsed. Changes still inside the observation window are pending and excluded from yield, so a recent change never counts as a survivor by default. Keep `metrics.py` pure (no DB) so the formulas stay deterministic.
- direction compares the value to a stored `metricbaseline` with a flat tolerance (default 0.02); with no baseline it is `no-baseline` and with no value `no-data`. `change.repository_id` / `worktree_id` are cleared when a repository is deleted and changes/interventions are deleted with their task.

## 2026-10-12: Tags are a normalized JSON list on Task, filtered in process

- Tags reuse the existing `task.tags` JSON column (no table, no migration). `crud.normalize_tags` trims, drops empties, and de-duplicates while preserving order, and the tasks router applies it on create and update. `GET /api/tasks` accepts a repeatable `tag` query parameter and keeps only tasks carrying every requested tag (AND), filtered in process like `q`. `GET /api/tags` derives `{name, count}` from the tasks, ordered by count descending then case-insensitive name. Tags are case-sensitive. The SPA filters the already-loaded list client-side (`store.tagFilter`), it does not send `tag` to the API; the CLI (`task list --tag`, `tag list`) does.

## 2026-10-11: the frontend dev toolchain upgrades as a set

- vue-router 5 needs vite `^7.3 || ^8`, vite 8 needs `@vitejs/plugin-vue` 6, and vitest 5 must move with `@vitest/coverage-v8` 5. Dependabot's per-package PRs fail `npm ci` on their own because of these peer constraints; bump the set together (done in PR #7).

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
- The frontend has a command palette (`CommandPalette.vue`, opened with Ctrl/Cmd+K from `App.vue`): it fuzzy-searches a mix of actions (new task, go to settings) and tasks, and navigates on Enter. Items carry a `run` callback supplied by `App.vue`. On a task page it adds a "This task" section whose items call `store.focusField` (set by `TaskView`), and `EditableText`/`SearchSelect` expose `activate()` so the palette can jump straight into editing a field.
- App settings (`setting` table, overridden on the Settings page) include `editor_url_template`; `WorktreesPanel` renders an "Open in editor" button per worktree that opens it with `{path}` substituted (the path keeps its leading slash, so use `vscode://file{path}`). The frontend loads effective settings into `store.settings`.
- Focus hints: press `f` (only when not typing) to set `store.hintMode`. `App.vue` scans `.main` for `a[href], button, input, textarea, select, [tabindex]` (skipping disabled controls and the transcript), assigns letters (`a..z`, then `aa..`), renders fixed-position badges, and focuses the matching control on keypress; `Esc` exits. This covers every control, buttons included, without per-field wiring.
- Task↔Repository is many-to-many (`TaskRepository`); `Task.repository_id` is gone from the model. `db._migrate_task_repositories()` moves old single values into the join table and nulls the column. SQLite cannot `DROP COLUMN` a column that carries a foreign key, so `task.repository_id` lingers in migrated databases, unused. Deleting a task or a repository removes the join rows; worktree creation defaults to one of the task's repositories and `_resolve_cwd` falls back to the task's first repository.
- An item's source (`slack`/`github`/`gdrive`/`url`/`note`) is inferred from the value by `infer_item_source` in `services.py`; the UI and CLI omit it (`ItemCreate.source` is optional). An explicit source still wins. Text that is not a URL (per `looks_like_url`: needs a scheme or a bare domain, and no spaces) is a `note`: `_upsert_item` moves it into `content` and leaves `url` null rather than storing a bogus link.
- The **Items** page (`ItemsView.vue`, route `/items`) lists every `SourceItem` with per-source filters and search; `ItemRead.task_ids` (populated by `_item_read` in `routers/items.py`) links each item back to the tasks that use it. Repositories, groups, and harnesses stay under Settings.
- Linking an item to a task from the Items page reuses the task-side endpoint (`POST /api/tasks/{id}/items` with `item_id`) rather than adding an item-side endpoint; the picker is a `SearchSelect` of the tasks the item is not yet linked to.
- Task creation can import a GitHub issue: `TaskCreate.github_url` makes `create_task` fetch the issue (via `ghx`), fill title/description, and link it as an item. The New task modal leads with a paste-the-URL field (`GET /api/github/issue?url=` gives a preview via `fetch_github_issue`) and keeps a filterable, number-descending issue list (`GET /api/github/issues`) under "or pick from a repository".
- All GitHub access goes through **`ghx`** (`ghx issue list`, `ghx issue view`, `ghx pr view`), never `gh`. ghx's `--json` is a boolean that emits the whole object (no field list), and the repo selector is the global `-R/--repo`. Its JSON field names match gh's (`number`, `title`, `state`, `author.login`, `labels[].name`, `url`, `body`).
