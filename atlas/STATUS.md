# ATLAS project status

_Last updated: 2026-10-25 — Phase 2 in progress (Alpaca verified live; bar ingestion, live streaming, universe and watchlists built)._

| Phase | State |
|---|---|
| 1 Foundation | **Complete** |
| 2 Market data | **In progress**: Alpaca paper connectivity verified live (`check_alpaca` passes). Daily and minute bar ingestion with stored quality reports is built and tested live. The live WebSocket stream is built and tested against a local fake server, but not yet against Alpaca (this environment blocks the stream host). The universe screen with point-in-time snapshots and watchlist management is built and tested live. The dashboard data view is not built yet |
| 3 Trading engine | Partially pre-built: order state machine, idempotent submission, kill switch. No strategies, signal engine or risk engine yet |
| 4–8 | Not started |

## Implemented and tested
- Config: typed settings split by trust boundary; `config/policy.yaml` checked against hard ceilings in code; policy SHA-256 written to the audit log on every start.
- Database: 10 tables and an Alembic migration (upgrade, downgrade and upgrade again all checked on PostgreSQL 16). The audit log is append-only at the database level. The kill-switch row is a singleton and starts engaged.
- API: FastAPI, Argon2id auth, JWT, lockout, login rate limit, roles (viewer/operator/admin), liveness and readiness checks, status, kill switch, audit endpoints, security headers.
- Kill switch: blocks new orders, fails closed, cancels open orders, reconciles, sends an alert, and needs an admin plus password to resume. The follow-up task retries and alerts if the broker can't be reached.
- Execution prep: order state machine; idempotent submission that queries the broker before any retry; reconciliation that treats the broker as the source of truth; paper-only guards at 7 layers.
- Bar ingestion (`core/data/ingestion.py`, executor tasks `ingest_daily_bars` / `ingest_minute_bars`): fetches bars for the benchmark symbols (SPY, QQQ, IWM, DIA) plus all watchlist symbols. It drops partial bars and extended-hours minute bars, validates each series, and skips writing any symbol with a critical issue. Writes are upserts, so re-runs are idempotent. Daily runs refetch 400 days so split and dividend adjustments stay current; minute runs pick up from the last stored bar. One `data_quality_reports` row is written per symbol per run (migration 0002). A series is flagged stale when its newest bar is older than the XNYS calendar expects (minute tolerance = policy `max_bar_age_seconds`). Failures and stale data set the heartbeat to degraded and send a Telegram alert. `GET /api/v1/data/quality` returns the latest report for each series.
- Live stream (`integrations/alpaca/stream.py`, `apps/executor/stream_service.py`): a thin WebSocket client for Alpaca's market-data stream (quotes, trades, minute bars) for benchmarks plus watchlists, capped at `ATLAS_STREAM_MAX_SYMBOLS` (30, the free IEX limit) with benchmarks first. It reconnects with exponential backoff and jitter; the backoff resets after a session that delivered data. Connection-limit errors (406) wait at least 30 s. Auth failure (402) and insufficient subscription (409) set state `error`, retry every 5 minutes and send a critical alert. During market hours, a watchdog replaces a connection that has been quiet for 60 s. Subscriptions change on the live connection as watchlists change. Latest quotes and trades are coalesced into Redis every 0.5 s. Completed regular-hours minute bars are validated and stored in `bars` (`source=alpaca_<feed>_stream`). The `stream` heartbeat is ok / degraded (stale quotes) / error (disconnected), and an alert fires after 60 s down during market hours, with a "restored" message when it recovers. `core/data/live.fresh_quote()` is the fail-closed accessor for later trading code: market open, quote ≤ `max_quote_age_seconds` old by exchange time, two-sided, not crossed. `GET /api/v1/market/live` returns quotes with a `fresh` flag plus the stream status. The executor entrypoint `atlas.apps.executor.run` supervises the Celery worker and the stream together.
- Universe (`core/data/universe.py`, executor task `refresh_universe` at 06:45 NY on weekdays): screens every active Alpaca US equity against `policy.yaml`:
  - Tradable and listed on a national exchange. OTC and any unrecognized exchange label are excluded.
  - Last close ≥ $10.
  - 20-session mean dollar volume ≥ $20M, from **SIP** raw daily bars. IEX volume is ~3% of consolidated and would understate it ~30×.
  - At least 15 sessions of history and a print on the `as_of` session.
  - Every exclusion is counted by reason.
  - Snapshots are immutable: UPDATE is blocked by a PostgreSQL trigger (migration 0003); deleting old snapshots for retention is still allowed.
  - Point-in-time rule: a snapshot `as_of = D` is the universe for the next session, and `universe_for_session(T)` returns the latest snapshot with `as_of < T` (no lookahead).
  - A build writes everything or nothing. It refuses to publish if assets or bars can't be fetched, or if there are fewer than 50 members. The previous snapshot stays current and a Telegram alert is sent.
  - Same-day re-runs with unchanged criteria are no-ops.
  - Asset listing reads Alpaca's raw JSON because alpaca-py 0.44 fails on the new `TXSE` exchange code.
- Watchlists (`core/data/watchlists.py`, `/api/v1/watchlists`): operators create, replace and delete lists of up to 100 symbols, and every change is audited.
  - New symbols must be in the current universe snapshot; with no snapshot nothing can be added.
  - Symbols that later leave the universe may stay on a list but show `in_universe: false`. Trading must check membership itself.
  - Watchlist symbols feed minute ingestion and the live stream (benchmarks first, stream capacity reported).
  - `GET /api/v1/universe` returns the latest snapshot summary and its members, sorted by dollar volume and searchable.
- REST minute ingestion now resumes from its own coverage (rows with its source), so a gap the stream missed during a disconnect is backfilled.
- Data prep: NYSE (XNYS) calendar covering holidays, early closes and DST; bar validation (ordering, duplicates, OHLC consistency, stale data, gaps, future timestamps, extreme moves); Alpaca bar adapter.
- Integrations: Telegram notifier (redaction, dedupe, per-event preferences); provider-agnostic LLM interface with an Anthropic structured-output adapter and an untrusted-content policy.
- Workers: Celery `default` and `execution` queues, beat schedule in New York time, heartbeats.
- Dashboard: Next.js 16 with login, Overview, Risk Center (kill switch), Settings, and placeholder pages that say plainly what isn't built yet. PAPER banner on every page.
- Ops: Docker Compose (credentials isolated per container), Dockerfiles, CI (lint, types, tests with Postgres, pip-audit, npm audit, gitleaks, compose validation), Dependabot, backup script, docs.

## Test results (local, 2026-10-25)
- Backend: **215 passed, 0 failed** (unit, failure scenarios, PostgreSQL integration). Stream client tests run against a local fake of Alpaca's WebSocket protocol and cover auth, subscribe, parsing, drop and reconnect, growing backoff, 402/405/406, the watchdog, and live subscription changes.
- Migrations 0002 and 0003: upgrade, downgrade and upgrade again on PostgreSQL 16; `alembic check` finds no drift between models and schema.
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
- **Live universe (2026-10-25):** 14,398 active assets → 2,684 members (as of 2026-10-23) in 26 s. Exclusions: 7,045 below the dollar-volume minimum, 3,364 below $10, 894 not tradable, 308 OTC, 96 too little history, 5 no print on `as_of`, 2 no data. Lowest member close is $10.00 and lowest dollar volume $20.0M, exactly at the policy limits. A watchlist with an OTC symbol was rejected with its reason; a valid one was created and audited, and ingestion and the stream picked up its symbols.
- **The live stream has not connected to Alpaca.** This environment's network policy denies `stream.data.alpaca.markets` (403 from the egress proxy). Checked live with real Postgres, Redis and Celery: the executor launcher starts the worker and stream, the stream backs off correctly while blocked, the heartbeat and Redis status report `error` with the cause, `/api/v1/market/live` reports it (no invented quotes), and SIGTERM shuts down cleanly with exit 0. First live check once the host is allowed: Alpaca's 24/7 test feed (`feed="test"`, symbol `FAKEPACA`), then the IEX feed during market hours.
- Order submission has not been exercised against Alpaca. Only read paths (account, clock, calendar, bars) have been run live.
- The free IEX feed has gaps in thinly traded names (e.g. DIA: about 500 of 1,200 session minutes missing). These are reported as `missing_bars` warnings, not critical issues. Use the SIP feed if minute completeness matters.
- The stream and the Celery worker share one container; a crash of either restarts both (by design, so neither runs without the other).
- Ingestion runs on the single-concurrency `execution` queue, so a run can delay broker sync or kill-switch follow-up by a few seconds. That's fine for a few dozen symbols; split it into its own credentialed data service before scaling to a large universe.
- Point-in-time universe history starts with the first snapshot. Backtests over earlier dates have no survivorship-free universe; that needs a historical constituents source, which isn't available here.
- The screen applies only the policy rules. Leveraged/inverse ETFs, SPACs, warrants and units that pass price and liquidity stay in (e.g. leveraged ETFs are among the most liquid names). Add exclusions in a reviewed change if strategies shouldn't trade them.
- Minute bars are not re-adjusted after corporate actions; daily bars are refetched in full every day.
- Telegram is tested only against a mocked HTTP transport.
- Docker images were not built (no Docker daemon here). `docker compose config` validates.
- Rate limiting falls back to per-process limits when Redis is down.
- JWTs can't be revoked before they expire. Deactivating a user blocks them on the next request; logout only clears the cookie.

## Next engineering tasks (Phase 2)
1. ~~Run `check_alpaca` with paper keys~~ — done, all checks pass.
2. ~~Bar ingestion jobs (daily and minute)~~ — done.
3. ~~Live quotes/bars over the Alpaca WebSocket~~ — built; needs a live run once `stream.data.alpaca.markets` is reachable.
4. ~~Universe and watchlist management with point-in-time snapshots~~ — done.
5. Dashboard: watchlist and live prices on the Live Trading page.

## Required user action
- Alpaca paper keys: in place and verified. For Docker, make sure they are in `atlas/broker.env` (never in chat or git).
- Optional: Telegram bot token and chat id in `atlas/.env`; Anthropic key in `atlas/llm.env`.
