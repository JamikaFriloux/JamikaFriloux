# ATLAS — Autonomous Trading & Learning Analysis System

> **PAPER TRADING ONLY.** Simulated orders against Alpaca's paper environment. No real money.
> Nothing in this repository is investment advice, and no performance is implied or promised.

ATLAS is a research-driven algorithmic trading platform for US stocks and ETFs: deterministic
strategies, an independent risk engine with final authority, idempotent paper execution with
broker reconciliation, research agents that explain (but never trade), and an operator
dashboard.

* **Status:** Phases 1–3 built (paper orders gated until Phase 4 validation) — see [STATUS.md](STATUS.md).
* **Setup & operations:** [docs/setup.md](docs/setup.md)
* **Architecture:** [docs/architecture.md](docs/architecture.md) and [docs/adr](docs/adr)
* **Security model:** [docs/security.md](docs/security.md)
* **Engineering rules:** [CLAUDE.md](CLAUDE.md)

## Quick start (Docker)
```bash
cd atlas
cp .env.example .env && cp broker.env.example broker.env && cp llm.env.example llm.env
# edit .env (POSTGRES_PASSWORD, ATLAS_DATABASE_URL, ATLAS_JWT_SECRET) and broker.env (paper keys)
docker compose up -d --build
docker compose run --rm api python -m atlas.scripts.create_user admin --role admin
open http://localhost:3000
```

## Development
```bash
cd atlas && make setup && make test lint typecheck
```

| Component | Stack |
|---|---|
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 16 |
| Jobs | Celery 5 + Redis, beat in America/New_York, XNYS calendar |
| Broker | alpaca-py (paper only) |
| AI | Anthropic Claude via provider-agnostic structured-output interface |
| Dashboard | Next.js 16, TypeScript, Tailwind CSS 4, shadcn-style components |
| Ops | Docker Compose, GitHub Actions, structlog JSON logs, Sentry/OTel hooks, Telegram |
