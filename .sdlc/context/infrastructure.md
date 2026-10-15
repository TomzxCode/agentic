<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Infrastructure

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| Language (backend, CLI) | Python | 3.12+ |
| Frontend language | JavaScript (ES modules) | — |
| Runtime (backend) | CPython via uvicorn | — |
| Runtime (frontend build) | Node.js (Vite) | 20+ |
| Backend framework | FastAPI | >=0.115 |
| ORM / models | SQLModel (SQLAlchemy) | >=0.0.22 |
| Database | SQLite (WAL) | bundled with Python |
| Agent protocol | agent-client-protocol (`acp`) | >=0.12 |
| HTTP client | httpx | >=0.27 |
| Logging | structlog | >=24.1 |
| Settings | pydantic-settings | >=2.0 |
| SSE | sse-starlette | >=2.1 |
| CLIs | cyclopts | >=5.2.0 |
| Documentation | Zensical | >=0.0.70 |
| Frontend framework | Vue | ^3.5.13 |
| Routing | vue-router | ^4.5.0 |
| Build tool | Vite | ^6.0.7 |
| PWA | vite-plugin-pwa | ^0.21.1 |

## Development Tooling

| Tool | Purpose | Command |
|---|---|---|
| uv | Package and workspace management | `uv add <package>` / `uv sync` |
| ruff | Linting and formatting (line length 120) | `uv run ruff format .` / `uv run ruff check --fix .` |
| ty | Static type checking | `uv run ty check` |
| pytest (+ pytest-asyncio) | Testing | `uv run pytest -q` |
| Vite | SPA dev server and build | `cd frontend && npm run dev` / `npm run build` |
| zensical | Documentation site build and preview | `make docs` / `make docs-serve` |
| make | Task shortcuts | `make test`, `make lint`, `make build`, `make run` |

Type hints are checked statically with `ty` (`make typecheck`, `uv run ty check`), against the Python 3.12 floor declared in `requires-python`.

## Environments

| Environment | Branch | Purpose | URL |
|---|---|---|---|
| Local (dev, split) | any | Backend with reload and the Vite dev server (`make run` starts the backend and the Vite dev server together) | backend `http://127.0.0.1:8600`, frontend `http://localhost:5173` |
| Local (single app) | main | Built SPA served by the API | `http://127.0.0.1:8600` |

There is no staging or production environment; the app is run locally by its owner.
Both servers bind `0.0.0.0` for remote/VPN access.

## CI/CD Pipelines

| Workflow | Trigger | What it runs |
|---|---|---|
| `.github/workflows/ci.yml` (Python) | push to `main`, pull requests | `uv sync --frozen`, ruff check, ruff format check, `ty check`, `pytest -q`. |
| `.github/workflows/ci.yml` (Frontend) | push to `main`, pull requests | `npm ci` then `npm run build` in `frontend/`. |
| `.github/workflows/docs.yml` | push to `main`, pull requests, manual dispatch | `uv sync --frozen` then `zensical build`; on a non-PR event it uploads and deploys the site to GitHub Pages. |

Both jobs run on `ubuntu-latest` (Python via uv, Node 22), cancel superseded runs on the same ref, and have `contents: read` permissions.

## Deployment

Deployment is local: `make build` builds the SPA into `backend/static`, then `uv run agentic-server serve --host 0.0.0.0 --port 8600` serves the API and the built SPA from one process.
`make run` starts that same server together with the Vite dev server, for development.
There is no packaging or release pipeline beyond the two installable Python packages (`agentic`, `agentic-cli`).
The documentation site is published separately: the Docs workflow builds `docs/` with Zensical and deploys it to GitHub Pages at `https://tomzxcode.github.io/agentic/` on every push to `main`.

### Rollback

No formal rollback procedure: revert the change (or `git checkout` the previous revision), rebuild the SPA with `make build`, and restart the server.
The database is a single SQLite file under `AGENTIC_DATA_DIR` (default `~/.agentic/agentic.db`); schema changes are applied in place and are not automatically reversible.

## Health Checks

| Endpoint | Expected response | Checked by |
|---|---|---|
| `GET /api/health` | `200 OK`, `{"status": "ok", "service": "agentic"}` | `agentic health`; no probe infrastructure |

## Smoke Tests

`uv run pytest -q` from the repository root runs the backend and CLI test suites (see `Makefile` `test` target and `pyproject.toml` `testpaths`).
There is no separate smoke-test suite.

## Hosting

Runs on the owner's own machine; no cloud host, region, or scaling strategy.
There is no infrastructure-as-code.

## Secrets Management

No secrets are stored by the app.
Configuration comes from environment variables prefixed `AGENTIC_` or from a `.env` file in the working directory the server is started from (`pydantic-settings`); the optional `ghx` and `slackx` CLIs use their own external credentials.
