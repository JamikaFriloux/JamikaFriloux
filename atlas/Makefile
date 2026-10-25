# Convenience targets. Run from the atlas/ directory.
.PHONY: setup test lint typecheck migrate api worker executor stream beat dashboard up down

setup:
	cd backend && uv sync
	cd dashboard && npm ci

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

typecheck:
	cd backend && uv run mypy atlas
	cd dashboard && npx tsc --noEmit

migrate:
	cd backend && uv run alembic upgrade head

api:
	cd backend && uv run uvicorn atlas.apps.api.main:app_factory --factory --reload --port 8000

worker:
	cd backend && uv run celery -A atlas.apps.worker.celery_app worker -Q default -n worker@%h

executor:  # Celery execution worker + live stream, as in Docker
	cd backend && uv run python -m atlas.apps.executor.run

stream:  # live stream only
	cd backend && uv run python -m atlas.apps.executor.stream_service

beat:
	cd backend && uv run celery -A atlas.apps.worker.celery_app beat

dashboard:
	cd dashboard && npm run dev

up:
	docker compose up -d --build

down:
	docker compose down
