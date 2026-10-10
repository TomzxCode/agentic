.PHONY: help install dev-backend dev-frontend test lint build run

help:
	@echo "install        install backend + CLI (workspace) and frontend deps"
	@echo "dev-backend    run the API with reload on 0.0.0.0:8600"
	@echo "dev-frontend   run the Vite dev server on 0.0.0.0:5173"
	@echo "test           run backend + CLI tests"
	@echo "lint           ruff format + check"
	@echo "build          build the SPA into backend/static"
	@echo "run            serve API + built SPA on 0.0.0.0:8600"

install:
	uv sync
	cd frontend && npm install

dev-backend:
	uv run agentic-server serve --host 0.0.0.0 --port 8600 --reload

dev-frontend:
	cd frontend && npm run dev

test:
	uv run pytest -q

lint:
	uv run ruff format . && uv run ruff check --fix .

build:
	cd frontend && npm run build

run:
	uv run agentic-server serve --host 0.0.0.0 --port 8600
