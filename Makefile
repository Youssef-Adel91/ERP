.PHONY: help test lint format migrate run

help:
	@echo "Omni ERP Makefile commands:"
	@echo "  make test      - Run all standard tests"
	@echo "  make lint      - Run ruff linter, formatter check, and mypy"
	@echo "  make format    - Run ruff formatter to fix files"
	@echo "  make migrate   - Run alembic database migrations"
	@echo "  make run       - Run the FastAPI server locally"

test:
	cd backend && .venv/Scripts/pytest tests/ -v

lint:
	cd backend && .venv/Scripts/ruff check .
	cd backend && .venv/Scripts/ruff format --check .
	cd backend && .venv/Scripts/mypy .

format:
	cd backend && .venv/Scripts/ruff check --fix .
	cd backend && .venv/Scripts/ruff format .

migrate:
	cd backend && .venv/Scripts/alembic upgrade head

run:
	cd backend && .venv/Scripts/uvicorn app.main:app --reload
