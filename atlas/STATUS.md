# ATLAS project status

_Last updated: 2026-10-25 — end of Phase 1 + Phase 2 preparation._

| Phase | State |
|---|---|
| 1 Foundation | **Complete** |
| 2 Market data | **Prepared**: Alpaca paper gateway, market-data adapter, calendar, bar validation, reconciliation built and unit-tested. Needs paper credentials to run live; ingestion jobs, streaming and watchlists not built yet |
| 3 Trading engine | Partially pre-built: order state machine, idempotent submission, kill switch. No strategies, signal engine or risk engine yet |
| 4–8 | Not started |

## Implemented and tested
- Config: typed settings split by trust boundary; `config/policy.yaml` checked against hard ceilings in code; policy SHA-256 written to the audit log on every start.
- Database: 10 tables and an Alembic migration (upgrade, downgrade and upgrade again all checked on PostgreSQL 16). The audit log is append-only at the database level. The kill-switch row is a singleton and starts engaged.
- API: FastAPI, Argon2id auth, JWT, lockout, login rate limit, roles (viewer/operator/admin), liveness and readiness checks, status, kill switch, audit endpoints, security headers.
- Kill switch: blocks new orders, fails closed, cancels open orders, reconciles, sends an alert, and needs an admin plus password to resume. The follow-up task retries and alerts if the broker can't be reached.
- Execution prep: order state machine; idempotent submission that queries the broker before any retry; reconciliation that treats the broker as the source of truth; paper-only guards at 7 layers.
- Data prep: NYSE (XNYS) calendar covering holidays, early closes and DST; bar validation (ordering, duplicates, OHLC consistency, stale data, gaps, future timestamps, extreme moves); Alpaca bar adapter.
- Integrations: Telegram notifier (redaction, dedupe, per-event preferences); provider-agnostic LLM interface with an Anthropic structured-output adapter and an untrusted-content policy.
- Workers: Celery `default` and `execution` queues, beat schedule in New York time, heartbeats.
- Dashboard: Next.js 16 with login, Overview, Risk Center (kill switch), Settings, and placeholder pages that say plainly what isn't built yet. PAPER banner on every page.
- Ops: Docker Compose (credentials isolated per container), Dockerfiles, CI (lint, types, tests with Postgres, pip-audit, npm audit, gitleaks, compose validation), Dependabot, backup script, docs.

## Test results (local, 2026-10-25)
- Backend: **135 passed, 0 failed** (unit, failure scenarios, PostgreSQL integration). Coverage 83%.
- `ruff check`, `ruff format --check`, `mypy atlas`: clean. `pip-audit`: no known vulnerabilities.
- Dashboard: `tsc --noEmit` and `next build` pass; `npm audit`: 0 vulnerabilities.
- End-to-end, run by hand with Playwright against local Postgres, Redis, API, worker, beat and the dashboard:
  - login (a wrong password is rejected)
  - httpOnly cookie that page scripts can't read
  - kill switch resume and engage through the UI
  - worker heartbeat
  - executor without credentials fails safely and reports broker `error`

## Not tested / known limitations
- **Real Alpaca connectivity has not been run** (no credentials in this environment). The gateway and market-data code are tested with fakes and the real SDK types. `python -m atlas.scripts.check_alpaca` is the acceptance check once paper keys exist.
- Telegram is tested only against a mocked HTTP transport.
- Docker images were not built (no Docker daemon here). `docker compose config` validates.
- Rate limiting falls back to per-process limits when Redis is down.
- JWTs can't be revoked before they expire. Deactivating a user blocks them on the next request; logout only clears the cookie.

## Next engineering tasks (Phase 2)
1. Run `check_alpaca` with paper keys; fix anything it finds.
2. Bar ingestion jobs (daily and minute) into `bars`, with validation reports stored and stale data flagged.
3. Live quotes/bars over the Alpaca WebSocket in the executor/data service: reconnects, heartbeats, freshness tracking.
4. Universe and watchlist management (price ≥ $10, ADV ≥ $20M, no OTC) with point-in-time snapshots.
5. Dashboard: watchlist and live prices on the Live Trading page.

## Required user action
- Create Alpaca **paper** API keys and put them in `atlas/broker.env` (never in chat or git).
- Optional: Telegram bot token and chat id in `atlas/.env`; Anthropic key in `atlas/llm.env`.
