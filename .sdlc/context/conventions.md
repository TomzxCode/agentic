<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Conventions

## Naming

- **Files:** Python modules are `snake_case.py`; Vue components are `PascalCase.vue`; other frontend JS modules are `camelCase.js` (`cycleTime.js`, `gridSetup.js`), frontend tests are `*.test.js` under `src/__tests__/`.
- **Variables:** `snake_case` in Python, `camelCase` in JavaScript.
- **Functions / Methods:** `snake_case` in Python, `camelCase` in JavaScript; FastAPI route functions are verbs (`list_tasks`, `create_run`).
- **Classes:** `PascalCase` in Python and JavaScript; SQLModel tables are singular nouns (`Task`, `SourceItem`, `AgentRun`).
- **Constants:** `UPPER_SNAKE_CASE` (`HARNESS_PRESETS`, `CONTEXT_INSTRUCTIONS`, `SESSION_LINK_KEYS`).
- **Database:** table names are the lowercased class name; columns are `snake_case`; foreign keys are `<entity>_id`.

## Directory Structure

- `backend/src/agentic/`, the FastAPI app. Wiring and cross-cutting modules, one concern per file: `main.py` (app wiring), `config.py`, `db.py`, `crud.py` (shared CRUD helpers, including `get_or_404`), `events.py`, `links.py`, `provenance.py`, `jobs.py`, `stack.py`, `schedules.py`, `metrics.py`, `inbox.py`, `refresh.py`, `graphs.py`, and the `*_store.py` modules (`settings_store.py`, `decisions_store.py`, `feedback_store.py`, `review_store.py`).
- Domain packages, each imported by its defining submodule (the `__init__.py` files carry docstrings only, no re-export barrels): `models/` (SQLModel tables, by domain), `schemas/` (request/response models, by resource), `services/` (`shell`, `git`, `names`, `parsing`, `github`, `slack`, `sources`, `prompts`, `managed_tools`), `agents/` (`harnesses`, `client`, `pool`, `runner`, `executions`), and `rpc/` (JSON-RPC 2.0: `protocol.py`, `methods.py`, `server.py`, mounted at `POST /rpc`).
- `routers/` holds one module per resource; a resource too large for one module keeps its sub-concern in a sibling (`task_writes`, `task_service`, `task_items`, `task_dependencies`, `items_refresh`, `agent_runs` + `agent_streams`, `people` + `people_service` + `people_links`, `reviews` + `review_findings`), all mounted from `main.py`.
- `backend/tests/` holds pytest tests, one file per area or module (`test_agents_harnesses.py`, `test_services_prompts.py`, and so on); shared fixtures live in `conftest.py` and `_*_helpers.py`.
- `cli/src/agentic_cli/` is the user CLI: `cli.py` (root app + launcher), `runtime.py` (context, output format, API client), `rpc_client.py` (JSON-RPC client), `render.py` (plain-text renderers), and `commands/` (one module per resource, each exposing `register(app)`), with tests in `cli/tests/`.
- `frontend/src/` is the SPA: `App.vue`, `main.js` (router), `store.js`, `api.js`, plus one `camelCase.js` helper module per area (`gantt.js`, `markdown.js`, `toolLinks.js`), with `views/`, `components/`, `composables/`, and `__tests__/`.
- `docs/` is the zensical documentation site (`make docs`), organized by Divio type: `tutorials/`, `how-to/`, `reference/`, `explanation/`.
- `.sdlc/` holds SDLC artifacts (context, features, knowledge, templates).

## Coding Standards

- Python targets 3.12+ and uses type hints throughout.
- Use `structlog` for logging (`log = structlog.get_logger(__name__)`); do not use the stdlib logging module directly for app events.
- Ruff lint (E, F, I, UP, B, SIM) and format, line length 120, with `B008` ignored for FastAPI `Depends`.
- Types are checked with ty (`make typecheck`, `uv run ty check`). SQLModel columns used in query expressions are wrapped with `col(...)` so they type as columns, and bulk deletes/updates use `session.exec()` (not the deprecated `session.execute()`).
- Keep `__init__.py` files minimal; do not use `__all__` in them.
- SQLite enforces foreign keys, so deletes that touch parents use explicit, ordered `session.execute(sa_delete(...))` statements rather than relying on ORM cascade ordering.
- SQLModel's `create_all` (`db.create_db_and_tables`) only creates missing tables and never adds columns; add new columns in `db._ensure_columns()` and backfill seeded rows.
- Never mutate a JSON column dict in place, SQLAlchemy emits no UPDATE for it; assign a fresh object back to the attribute and merge concurrent writers (`_merged_state` in `graphs.py`).
- Blocking work (subprocess, network) runs off the event loop via `anyio.to_thread.run_sync`.
- The CLI prints through a plain Rich `Console(markup=False, soft_wrap=True)` so `[open]`-style text stays literal and piped JSON is not wrapped.

## Testing

- Backend and CLI tests run in parallel across processes (`make test-backend`, `uv run pytest -q -n auto`); pass extra args through `COV` (`make test-backend COV="--cov=agentic ..."`).
- `backend/tests/conftest.py` points `AGENTIC_DATA_DIR` at a fresh temp dir per process (assigned unconditionally, not `setdefault`) and sets `AGENTIC_WARM_HARNESS_SESSION=0`, so no test spawns the real ACP harness pool.
- Monkeypatch the module where the symbol is used or defined (`monkeypatch.setattr(shell, ...)`), never the package.
- Frontend tests run with Vitest (`make test-frontend`) under jsdom with `pool: 'vmThreads'`; shared stubs (for example `ResizeObserver`) live in `src/test-setup.js`.
- Do not `vi.stubGlobal('location', ...)`; stub `RouterLink` through mount options instead.
- AG Grid applies row changes asynchronously, so a test that narrows rows waits on a `settleGrid()` helper (`flushPromises()` plus a short timeout) before asserting.

## Frontend and UI

- The web app is designed with mobile in mind: design and check screens at phone widths as well as larger viewports, so the app stays usable on a phone.
- Breakpoints are max-width based, with the primary one at 760px.
  Below 760px the sidebar becomes an off-canvas drawer toggled from the top bar, and secondary chrome (command palette trigger, keyboard hints, some nav) hides.
- Controls stay touch-friendly on small screens (icons carry `aria-label`s, buttons keep a comfortable tap size, and form fields use 16px text so mobile browsers do not zoom on focus).
- Respect mobile browser chrome and notches by accounting for `env(safe-area-inset-*)` in full-height or edge-anchored regions.
- The Settings icon is always last in the sidebar's default nav order (`SIDEBAR_NAV_ITEMS` in `frontend/src/sidebarNav.js`). Add a new page before `settings`, never after it. The user can still reorder the icons in Settings → Sidebar.
- Card components compose: `EntityCard.vue` is the shared shell (slots for `title`, `lead`, `select`), and `TaskCard.vue` and `ItemCard.vue` wrap it instead of duplicating markup.
- AG Grid registration is shared: `components/gridSetup.js` registers the row-model, filter, and column-API modules once and exports the `gridTheme` mapped to the app's design tokens.
- Per-device UI preferences (sidebar state, grid column choices, status bar) persist in `localStorage`, not in user settings.
- List views needing a multi-select filter use the shared `ValuesFilter.vue` custom filter (`valuesFilter: ValuesFilter` in the grid's component definitions), because AG Grid's Set filter is Enterprise-only.
- Grid cell renderers resolve link components at setup time with `resolveComponent('RouterLink')` (see `RepositoriesView.vue`, `PeopleView.vue`).

## Commit Messages

Conventional Commits: `<type>[(scope)]: <description>`, with the imperative mood and no trailing period.
Types seen in history: `feat`, `fix`, `refactor`, `docs`, `build` (dependabot bumps).
Scopes are lowercase and name the area touched, for example `feat(import):`, `feat(ui):`, `fix(items):`, `feat(timeline):`.

## Branching

`main` is the default and deployment branch; changes land through PRs (dependabot bumps open their own `dependabot/*` branches).
Agent worktrees created for a task use the branch `agentic/<slug-of-title>-<first-4-chars-of-task-id>`, for example `agentic/cli-driven-problem-2f43`.

## SDLC Documentation Style

- Write one sentence per line in markdown artifacts, so diffs stay small and reviewable.
- Use sentence case for headings, not title case.
- Prefer bullet lists and tables over prose paragraphs.
- Avoid em dashes; use commas or parentheses instead.
- Acceptance criteria are fenced `gherkin` blocks tagged with their requirement ID.
- Keep terminology consistent with `vocabulary.md`.
