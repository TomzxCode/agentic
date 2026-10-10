.PHONY: help install dev-backend dev-frontend test lint build run

help:
	@echo "install        install backend and frontend deps"
	@echo "dev-backend    run the API with reload on :8600"
	@echo "dev-frontend   run the Vite dev server on :5173"
	@echo "test           run backend tests"
	@echo "lint           ruff format + check the backend"
	@echo "build          build the SPA into backend/static"
	@echo "run            serve API + built SPA on :8600"

install:
	cd backend && uv sync
	cd frontend && npm install

dev-backend:
	cd backend && uv run agentic serve --host 127.0.0.1 --port 8600 --reload

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff format . && uv run ruff check --fix .

build:
	cd frontend && npm run build

run:
	cd backend && uv run agentic serve --host 127.0.0.1 --port 8600
