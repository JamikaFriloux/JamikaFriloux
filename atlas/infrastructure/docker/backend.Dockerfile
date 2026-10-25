# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY config/ /app/config/
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 atlas && chown -R atlas /app
USER atlas
ENV PATH="/app/backend/.venv/bin:$PATH" ATLAS_POLICY_PATH=/app/config/policy.yaml
EXPOSE 8000
CMD ["uvicorn", "atlas.apps.api.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
