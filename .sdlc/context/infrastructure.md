<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Infrastructure

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| Language (backend, CLI, launcher) | Python | 3.12+ |
| Runtime (backend, CLI, launcher) | CPython via uv workspace | — |
| Runtime (frontend build) | Node.js (Vite) | 22+ (`engines` >= 22.12.0, CI uses 22) |
| Backend framework | FastAPI | >=0.159.1 |
| ASGI server | uvicorn[standard] | >=0.54.0 |
| ORM / models | SQLModel (SQLAlchemy) | >=0.0.22 |
| Database | SQLite (WAL) | bundled with Python |
| Job queue | SAQ (`saq[sqlite]`, installed from a git fork) | unpinned, `rev = dev` of `tomzxforks/saq` |
| Agent protocol | agent-client-protocol (`acp`) | >=0.12 |
| HTTP client | httpx | >=0.27 |
| Logging | structlog | >=24.1 |
| Settings | pydantic-settings | >=2.16.1 |
| SSE | sse-starlette | >=2.1 |
| API reference | scalar-fastapi (Scalar served at `/docs`) | >=1.9.1 |
| Scheduling helpers | croniter, tzlocal, pyyaml | >=6.2.4, >=5.4.4, >=6.0.3 |
| CLIs | cyclopts (CLI output rendered with rich) | >=5.2.0 (rich >=13.0) |
| Tray companion | pystray, pynput, pillow | >=0.19, >=1.7, >=13.0.0 |
| Documentation | Zensical | >=0.0.70 |
| Frontend framework | Vue | ^3.5.44 |
| Routing | vue-router | ^5.4.0 |
| Build tool | Vite | ^8.3.5 |
| Tests (frontend) | Vitest (+ @vitest/coverage-v8) | ^5.0.4 |
| Data grid | AG Grid Community (+ ag-grid-vue3) | ^36.2.0 |
| PWA | vite-plugin-pwa | ^2.0.0 |
| Package manager (frontend) | pnpm | 12.15.0 |

Other frontend dependencies: `@xyflow/vue` (graph view), `croner` (cron expressions), `dompurify` and `markdown-it` (markdown rendering).

## Development Tooling

| Tool | Purpose | Command |
|---|---|---|
| uv | Package and workspace management | `uv add <package>` / `uv sync` |
| ruff | Linting and formatting (line length 120) | `make lint` (`uv run ruff format .` / `uv run ruff check --fix .`) |
| ty | Static type checking | `make typecheck` (`uv run ty check`) |
| pytest (+ pytest-asyncio, pytest-cov, pytest-xdist) | Backend and CLI tests (parallel across cores) | `make test-backend` (`uv run pytest -q -n auto`) |
| Vitest | Frontend tests | `make test-frontend` (`cd frontend && pnpm run test`) |
| Vite | SPA dev server and build | `cd frontend && pnpm run dev` / `pnpm run build` |
| zensical | Documentation site build and preview | `make docs` / `make docs-serve` |

Type hints are checked statically with `ty` (`make typecheck`, `uv run ty check`), against the Python 3.12 floor declared in `requires-python`.

Make targets (`make help` lists them):

| Target | What it does |
|---|---|
| `make install` | `uv sync`, then `pnpm install` in `frontend/` |
| `make run` | API + SAQ worker + Vite dev server + tray, taking free ports from :8600 and :5173 (via `scripts/dev.py`) |
| `make run-dev` | like `run`, with the API reloading on file changes (`ARGS="..."` pins ports) |
| `make dev-backend` | API with reload on `0.0.0.0:8600` |
| `make dev-worker` | the SAQ agent-run worker |
| `make dev-frontend` | the Vite dev server on `0.0.0.0:5173` |
| `make dev-tray` | the menu-bar/tray companion against the dev frontend |
| `make test` | backend + CLI tests and frontend tests, no coverage |
| `make test-backend` / `make test-frontend` | one side only |
| `make coverage-backend` / `make coverage-frontend` | the same tests with coverage (`coverage.xml` / `frontend/coverage/`) |
| `make lint` / `make lint-frontend` | ruff format + check / eslint + prettier check |
| `make typecheck` | `ty check` |
| `make build` | build the SPA into `backend/static` |
| `make docs` / `make docs-serve` | build / preview the documentation site |

`scripts/dev.py` starts each service on the first free port at or above its default, so several checkouts can run side by side.
The API and the dev server are essential: if either exits, the whole stack is torn down.
The worker and the tray are optional and are skipped with `--no-worker` / `--no-tray`, or when no display is available for the tray.

## Environments

| Environment | Branch | Purpose | URL |
|---|---|---|---|
| Local (dev, split) | any | API, SAQ worker, Vite dev server, and tray (`make run` starts them together) | backend `http://127.0.0.1:8600`, frontend `http://localhost:5173` |
| Local (single app) | main | Built SPA served by the API | `http://127.0.0.1:8600` |

There is no staging or production environment; the app is run locally by its owner.
Both the API and the dev server bind `0.0.0.0` for remote/VPN access.
The Vite dev server proxies `/api`, `/docs`, `/openapi.json`, and `/saq` to the API (target taken from `AGENTIC_API`).
The API process owns the background loops: item refresh, review scan, user scheduled tasks, execution graphs, the warm ACP harness session, and the managed `ghx`/`slackx` serve-mode processes.
Agent runs execute in a separate worker process (`agentic-server worker`) from a SQLite queue at `<data dir>/queue.db`.
The SAQ run-queue monitor is served by the API at `/saq`, and the Scalar API reference at `/docs`.

## CI/CD Pipelines

| Workflow | Trigger | What it runs |
|---|---|---|
| `.github/workflows/ci.yml` (Python) | push to `main`, pull requests | `uv sync --frozen`, ruff check, ruff format check, `ty check`, `pytest -q -n auto --cov` with a `coverage-backend` artifact. |
| `.github/workflows/ci.yml` (Frontend) | push to `main`, pull requests | Node 22, `pnpm install --frozen-lockfile`, then lint, format check, coverage (artifact `coverage-frontend`), and build in `frontend/`. |
| `.github/workflows/docs.yml` | push to `main`, pull requests, manual dispatch | `uv sync --frozen` then `zensical build --clean`; on a non-PR event it uploads and deploys `site/` to GitHub Pages. |

Both CI jobs run on `ubuntu-latest` (Python via uv, Node 22), cancel superseded runs on the same ref, and have `contents: read` permissions.

## Deployment

Deployment is local: `make build` builds the SPA into `backend/static`, then `uv run agentic-server serve --host 0.0.0.0 --port 8600` serves the API and the built SPA from one process.
`make run` starts that same server together with the Vite dev server, for development.
There is no packaging or release pipeline beyond the three installable workspace packages (`agentic`, `agentic-cli`, `agentic-launcher`).
The documentation site is the only published artifact: the Docs workflow builds `docs/` with Zensical and deploys it to GitHub Pages at `https://tomzxcode.github.io/agentic/` on every push to `main`.

### Rollback

No formal rollback procedure: revert the change (or `git checkout` the previous revision), rebuild the SPA with `make build`, and restart the server.
The database is a single SQLite file under `AGENTIC_DATA_DIR` (default `~/.agentic/agentic.db`, with the SAQ queue next to it at `queue.db`); schema changes are applied in place and are not automatically reversible.

## Health Checks

| Endpoint | Expected response | Checked by |
|---|---|---|
| `GET /api/health` | `200 OK`, `{"status": "ok", "service": "agentic"}` | the `agentic health` CLI command; no probe infrastructure |

## Smoke Tests

`uv run pytest -q` from the repository root runs the backend and CLI test suites (see `pyproject.toml` `testpaths`).
`make test` also runs the frontend Vitest suite (`pnpm run test` in `frontend/`).
`make test-backend` and CI add `-n auto` so pytest-xdist spreads the tests across cores; each worker gets its own throwaway data directory (see `backend/tests/conftest.py`).
There is no separate smoke-test suite.

## Hosting

Runs on the owner's own machine; no cloud host, region, or scaling strategy.
The documentation site is hosted on GitHub Pages.
There is no infrastructure-as-code.

## Secrets Management

No secrets are stored by the app.
Configuration comes from environment variables prefixed `AGENTIC_` or from a `.env` file in the working directory the server is started from (`pydantic-settings`).
A few Slack settings also accept unprefixed aliases (`SLACK_TOKEN`, `SLACK_COOKIE`, and so on).
The optional `ghx` and `slackx` CLIs use their own external credentials; when the server manages them they run as serve-mode child processes and inherit that environment.
