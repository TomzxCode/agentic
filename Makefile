.PHONY: help install dev-backend dev-frontend test test-frontend test-backend coverage-backend coverage-frontend lint lint-frontend typecheck build run

help:
	@echo "install             install backend + CLI (workspace) and frontend deps"
	@echo "dev-backend         run the API with reload on 0.0.0.0:8600"
	@echo "dev-frontend        run the Vite dev server on 0.0.0.0:5173"
	@echo "test                run backend + CLI tests with coverage"
	@echo "test-backend        run backend + CLI tests with coverage"
	@echo "test-frontend       run frontend (Vitest) tests with coverage"
	@echo "coverage-backend    backend + CLI tests, write coverage.xml"
	@echo "coverage-frontend   frontend tests, write frontend/coverage/"
	@echo "lint                ruff format + check"
	@echo "lint-frontend       eslint + prettier check (frontend)"
	@echo "typecheck           ty check (static type checking)"
	@echo "build               build the SPA into backend/static"
	@echo "run                 serve API + frontend dev server (0.0.0.0:8600 and :5173)"

install:
	uv sync
	cd frontend && npm install

dev-backend:
	uv run agentic-server serve --host 0.0.0.0 --port 8600 --reload

dev-frontend:
	cd frontend && npm run dev

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
	@echo "API on http://0.0.0.0:8600, frontend dev server on http://0.0.0.0:5173 (Ctrl+C stops both)"
	@uv run agentic-server serve --host 0.0.0.0 --port 8600 & \
	api_pid=$$!; \
	( cd frontend && npm run dev ) & \
	frontend_pid=$$!; \
	trap 'kill $$api_pid $$frontend_pid 2>/dev/null' INT TERM EXIT; \
	wait
