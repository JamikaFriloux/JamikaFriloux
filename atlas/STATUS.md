# ATLAS project status

_Last updated: 2026-10-25 — Phase 2 in progress (Alpaca verified live, bar ingestion done)._

| Phase | State |
|---|---|
| 1 Foundation | **Complete** |
| 2 Market data | **In progress**: Alpaca paper connectivity verified live (`check_alpaca` passes). Daily and minute bar ingestion with stored quality reports is built and tested live. Streaming, universe/watchlists and the dashboard data view are not built yet |
| 3 Trading engine | Partially pre-built: order state machine, idempotent submission, kill switch. No strategies, signal engine or risk engine yet |
| 4–8 | Not started |

## Implemented and tested
- Config: typed settings split by trust boundary; `config/policy.yaml` checked against hard ceilings in code; policy SHA-256 written to the audit log on every start.
- Database: 10 tables and an Alembic migration (upgrade, downgrade and upgrade again all checked on PostgreSQL 16). The audit log is append-only at the database level. The kill-switch row is a singleton and starts engaged.
- API: FastAPI, Argon2id auth, JWT, lockout, login rate limit, roles (viewer/operator/admin), liveness and readiness checks, status, kill switch, audit endpoints, security headers.
- Kill switch: blocks new orders, fails closed, cancels open orders, reconciles, sends an alert, and needs an admin plus password to resume. The follow-up task retries and alerts if the broker can't be reached.
- Execution prep: order state machine; idempotent submission that queries the broker before any retry; reconciliation that treats the broker as the source of truth; paper-only guards at 7 layers.
- Bar ingestion (`core/data/ingestion.py`, executor tasks `ingest_daily_bars` / `ingest_minute_bars`): fetches bars for the benchmark symbols (SPY, QQQ, IWM, DIA) plus all watchlist symbols. It drops partial bars and extended-hours minute bars, validates each series, and skips writing any symbol with a critical issue. Writes are upserts, so re-runs are idempotent. Daily runs refetch 400 days so split and dividend adjustments stay current; minute runs pick up from the last stored bar. One `data_quality_reports` row is written per symbol per run (migration 0002). A series is flagged stale when its newest bar is older than the XNYS calendar expects (minute tolerance = policy `max_bar_age_seconds`). Failures and stale data set the heartbeat to degraded and send a Telegram alert. `GET /api/v1/data/quality` returns the latest report for each series.
- Data prep: NYSE (XNYS) calendar covering holidays, early closes and DST; bar validation (ordering, duplicates, OHLC consistency, stale data, gaps, future timestamps, extreme moves); Alpaca bar adapter.
- Integrations: Telegram notifier (redaction, dedupe, per-event preferences); provider-agnostic LLM interface with an Anthropic structured-output adapter and an untrusted-content policy.
- Workers: Celery `default` and `execution` queues, beat schedule in New York time, heartbeats.
- Dashboard: Next.js 16 with login, Overview, Risk Center (kill switch), Settings, and placeholder pages that say plainly what isn't built yet. PAPER banner on every page.
- Ops: Docker Compose (credentials isolated per container), Dockerfiles, CI (lint, types, tests with Postgres, pip-audit, npm audit, gitleaks, compose validation), Dependabot, backup script, docs.

## Test results (local, 2026-10-25)
- Backend: **158 passed, 0 failed** (unit, failure scenarios, PostgreSQL integration).
- Migration 0002: upgrade, downgrade and upgrade again on PostgreSQL 16; `alembic check` finds no drift between models and schema.
- **Live Alpaca paper (2026-10-25):** `check_alpaca` passed all 5 checks (paper endpoint, ACTIVE paper account, clock, 22-session calendar cross-check against XNYS, SPY daily bars validated). Live ingestion into PostgreSQL: 1,100 daily bars and 4,312 regular-hours minute bars across 4 symbols, all OK and none stale. An immediate re-run fetched incrementally (4 bars rewritten).
- `ruff check`, `ruff format --check`, `mypy atlas`: clean. `pip-audit`: no known vulnerabilities.
- Dashboard: `tsc --noEmit` and `next build` pass; `npm audit`: 0 vulnerabilities.
- End-to-end, run by hand with Playwright against local Postgres, Redis, API, worker, beat and the dashboard:
  - login (a wrong password is rejected)
  - httpOnly cookie that page scripts can't read
  - kill switch resume and engage through the UI
  - worker heartbeat
  - executor without credentials fails safely and reports broker `error`

## Not tested / known limitations
- Order submission has not been exercised against Alpaca. Only read paths (account, clock, calendar, bars) have been run live.
- The free IEX feed has gaps in thinly traded names (e.g. DIA: about 500 of 1,200 session minutes missing). These are reported as `missing_bars` warnings, not critical issues. Use the SIP feed if minute completeness matters.
- Ingestion runs on the single-concurrency `execution` queue, so a run can delay broker sync or kill-switch follow-up by a few seconds. That's fine for a few dozen symbols; split it into its own credentialed data service before scaling to a large universe.
- Minute bars are not re-adjusted after corporate actions; daily bars are refetched in full every day.
- Telegram is tested only against a mocked HTTP transport.
- Docker images were not built (no Docker daemon here). `docker compose config` validates.
- Rate limiting falls back to per-process limits when Redis is down.
- JWTs can't be revoked before they expire. Deactivating a user blocks them on the next request; logout only clears the cookie.

## Next engineering tasks (Phase 2)
1. ~~Run `check_alpaca` with paper keys~~ — done, all checks pass.
2. ~~Bar ingestion jobs (daily and minute)~~ — done.
3. Live quotes/bars over the Alpaca WebSocket in the executor/data service: reconnects, heartbeats, freshness tracking.
4. Universe and watchlist management (price ≥ $10, ADV ≥ $20M, no OTC) with point-in-time snapshots.
5. Dashboard: watchlist and live prices on the Live Trading page.

## Required user action
- Alpaca paper keys: in place and verified. For Docker, make sure they are in `atlas/broker.env` (never in chat or git).
- Optional: Telegram bot token and chat id in `atlas/.env`; Anthropic key in `atlas/llm.env`.
