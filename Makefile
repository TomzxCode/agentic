.PHONY: help install dev-backend dev-worker dev-frontend dev-tray test test-frontend test-backend coverage-backend coverage-frontend lint lint-frontend typecheck build run run-dev

help:
	@echo "install             install backend + CLI (workspace) and frontend deps"
	@echo "dev-backend         run the API with reload on 0.0.0.0:8600"
	@echo "dev-worker          run the agent-run worker"
	@echo "dev-frontend        run the Vite dev server on 0.0.0.0:5173"
	@echo "dev-tray            run the menu-bar/tray companion (global hotkey + Mark Done)"
	@echo "test                run backend + CLI tests with coverage"
	@echo "test-backend        run backend + CLI tests with coverage"
	@echo "test-frontend       run frontend (Vitest) tests with coverage"
	@echo "coverage-backend    backend + CLI tests, write coverage.xml"
	@echo "coverage-frontend   frontend tests, write frontend/coverage/"
	@echo "lint                ruff format + check"
	@echo "lint-frontend       eslint + prettier check (frontend)"
	@echo "typecheck           ty check (static type checking)"
	@echo "build               build the SPA into backend/static"
	@echo "run                 serve API + worker + frontend dev server + tray (0.0.0.0:8600 and :5173)"
	@echo "run-dev             like run, with the API reloading on file changes"

install:
	uv sync
	cd frontend && npm install

dev-backend:
	uv run agentic-server serve --host 0.0.0.0 --port 8600 --reload

dev-worker:
	uv run agentic-server worker

dev-frontend:
	cd frontend && npm run dev

dev-tray:
	AGENTIC_STACK_URL=http://localhost:5173/stack uv run agentic-stack

test: test-backend test-frontend

test-backend:
	uv run pytest -q

test-frontend:
	cd frontend && npm test

coverage-backend:
	uv run pytest -q --cov-report=xml:coverage.xml

coverage-frontend:
	cd frontend && npm run coverage

lint:
	uv run ruff format . && uv run ruff check --fix .

lint-frontend:
	cd frontend && npm run lint && npm run format:check

typecheck:
	uv run ty check

build:
	cd frontend && npm run build

run:
	@echo "API on http://0.0.0.0:8600, worker, frontend dev server on http://0.0.0.0:5173, tray (Ctrl+C stops all)"
	@uv run agentic-server serve --host 0.0.0.0 --port 8600 $(RELOAD) & \
	api_pid=$$!; \
	uv run agentic-server worker & \
	worker_pid=$$!; \
	( cd frontend && npm run dev ) & \
	frontend_pid=$$!; \
	AGENTIC_STACK_URL=http://localhost:5173/stack uv run agentic-stack & \
	tray_pid=$$!; \
	trap 'kill $$api_pid $$worker_pid $$frontend_pid $$tray_pid 2>/dev/null' INT TERM EXIT; \
	wait

# Like run, with the API reloading when backend files change.
run-dev:
	@$(MAKE) --no-print-directory run RELOAD=--reload
