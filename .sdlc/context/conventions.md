<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Conventions

## Naming

- **Files:** Python modules are `snake_case.py`; Vue components are `PascalCase.vue`; other JS modules and CSS are `lowercase.js`/`lowercase.css`.
- **Variables:** `snake_case` in Python, `camelCase` in JavaScript.
- **Functions / Methods:** `snake_case` in Python, `camelCase` in JavaScript; FastAPI route functions are verbs (`list_tasks`, `create_run`).
- **Classes:** `PascalCase` in Python and JavaScript; SQLModel tables are singular nouns (`Task`, `SourceItem`, `AgentRun`).
- **Constants:** `UPPER_SNAKE_CASE` (`HARNESS_PRESETS`, `CONTEXT_INSTRUCTIONS`, `SESSION_LINK_KEYS`).
- **Database:** table names are the lowercased class name; columns are `snake_case`; foreign keys are `<entity>_id`.

## Directory Structure

- `backend/src/agentic/` — the FastAPI app: `main.py` (app wiring), `config.py`, `db.py`, `models.py`, `schemas.py`, `crud.py`, `services.py`, `agents.py`, `events.py`, `links.py`, `settings_store.py`, `server_cli.py`, and `routers/` (one module per resource).
- `backend/tests/` — pytest tests, one file per area (`test_api.py`, `test_services.py`, and so on).
- `cli/src/agentic_cli/` — the user CLI (`cli.py`, `client.py`) with tests in `cli/tests/`.
- `frontend/src/` — the SPA: `App.vue`, `main.js` (router), `store.js`, `api.js`, `views/`, and `components/`.
- `.sdlc/` — SDLC artifacts (context, features, knowledge, templates).

## Coding Standards

- Python targets 3.12+ and uses type hints throughout.
- Use `structlog` for logging (`log = structlog.get_logger(__name__)`); do not use the stdlib logging module directly for app events.
- Ruff lint (E, F, I, UP, B, SIM) and format, line length 120, with `B008` ignored for FastAPI `Depends`.
- Types are checked with ty (`make typecheck`, `uv run ty check`). SQLModel columns used in query expressions are wrapped with `col(...)` so they type as columns, and bulk deletes/updates use `session.exec()` (not the deprecated `session.execute()`).
- Keep `__init__.py` files minimal; do not use `__all__` in them.
- SQLite enforces foreign keys, so deletes that touch parents use explicit, ordered `session.execute(sa_delete(...))` statements rather than relying on ORM cascade ordering.
- SQLModel's `create_all` only creates missing tables and never adds columns; add new columns in `db._ensure_columns()` and backfill seeded rows.
- Blocking work (subprocess, network) runs off the event loop via `anyio.to_thread.run_sync`.
- The CLI prints through a plain Rich `Console(markup=False, soft_wrap=True)` so `[open]`-style text stays literal and piped JSON is not wrapped.

## Frontend and UI

- The web app is designed with mobile in mind: design and check screens at phone widths as well as larger viewports, so the app stays usable on a phone.
- Breakpoints are max-width based, with the primary one at 760px.
  Below 760px the sidebar becomes an off-canvas drawer toggled from the top bar, and secondary chrome (command palette trigger, keyboard hints, some nav) hides.
- Controls stay touch-friendly on small screens (icons carry `aria-label`s, buttons keep a comfortable tap size, and form fields use 16px text so mobile browsers do not zoom on focus).
- Respect mobile browser chrome and notches by accounting for `env(safe-area-inset-*)` in full-height or edge-anchored regions.

## Commit Messages

Conventional Commits: `<type>[(scope)]: <description>`, with the imperative mood and no trailing period.
Types seen in history: `feat`, `fix`, `refactor`, `docs`.
Scopes are lowercase and name the area touched, for example `feat(import):`, `feat(ui):`, `fix(items):`, `feat(timeline):`.

## Branching

`main` is the default and deployment branch.
Agent worktrees created for a task use the branch `agentic/<slug-of-title>-<first-4-chars-of-task-id>`, for example `agentic/cli-driven-problem-2f43`.

## SDLC Documentation Style

- Write one sentence per line in markdown artifacts, so diffs stay small and reviewable.
- Use sentence case for headings, not title case.
- Prefer bullet lists and tables over prose paragraphs.
- Avoid em dashes; use commas or parentheses instead.
- Acceptance criteria are fenced `gherkin` blocks tagged with their requirement ID.
- Keep terminology consistent with `vocabulary.md`.
