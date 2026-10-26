# ATLAS project status

_Last updated: 2026-10-26 — Phase 3 trading engine built. Paper orders are gated until Phase 4 validation (by design)._

| Phase | State |
|---|---|
| 1 Foundation | **Complete** |
| 2 Market data | **Built; one live check outstanding**: Alpaca paper connectivity verified live (`check_alpaca` passes). Daily and minute bar ingestion with stored quality reports is built and tested live. The live WebSocket stream is built and tested against a local fake server, but not yet against Alpaca (this environment blocks the stream host). The universe screen with point-in-time snapshots, watchlist management and the Live Trading dashboard are built and tested live |
| 3 Trading engine | **Built**: indicators, strategy framework with 2 baseline strategies, signal engine, deterministic risk engine with sizing, signal→order pipeline, broker-side protective stops, exits, dashboard. Strategies run in RESEARCH (shadow); paper orders start only after a strategy passes Phase 4 validation |
| 4 Backtesting & promotion gates | Not started (ADR 0003) |
| 5–8 | Not started |

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
- Live Trading page (`dashboard/app/(console)/live`):
  - Market and stream status strip.
  - Quote board for benchmarks and each watchlist: bid, ask, spread, last, quote age and a fresh/stale/unavailable badge. Fresh means market open and a recent, two-sided, uncrossed quote, decided by the API's `fresh_quote()` rule.
  - The board polls a same-origin route every 2 s. If polls fail it marks every quote as not fresh. A one-sided quote (Alpaca sends 0 for the missing side) shows "—", not $0.
  - Open positions show the broker-synced P/L, plus a live mark only while the quote is fresh.
  - Watchlist editor (operator/admin): create, delete and remove symbols, and add from a universe search by symbol or name showing dollar volume. API rejection reasons are shown inline.
  - There is no manual order entry; orders arrive with the Phase 3 signal and risk engines.
  - New route handlers (`/api/live`, `/api/universe`, `/api/watchlists[/name]`) go through a shared `lib/proxy.ts` that adds the httpOnly session token and requires same-origin requests for writes. The API enforces roles.
- `/health/ready` reports each service's own status (ok/degraded/error). The 3-minute staleness rule applies only to continuously reporting services (worker, executor, broker, stream). Before, a failing stream read as "ok" and scheduled jobs read as "stale" between runs.
- **Phase 3, trading engine.** Everything below is deterministic; no LLM touches it.
  - Indicators (`core/indicators`): SMA, EMA, Wilder ATR and RSI, rolling highs/lows. Values are `None` until fully warmed up.
  - Strategies (`core/strategies`):
    - Each one is a pure function of (bars up to the close of `as_of`, the strategy's own position), so the Phase 4 backtester can run the same code.
    - The framework skips a symbol, with the reason recorded, when its history is short, it has no bar for the session, or its data fails validation.
    - Every entry needs a stop below the close. Signal ids are deterministic.
    - Baselines (both hypotheses, starting in RESEARCH):
      - `trend_breakout` v1.0.0: 55-day breakout above the 200-day SMA, 2×ATR stop, exit on a 20-day low.
      - `rsi_pullback` v1.0.0: RSI(2) < 10 above the 200-day SMA, 2.5×ATR stop, exit above the 5-day SMA or after 10 sessions.
  - Registry and lifecycle: the `strategies` table, synced from code. Only admins change status (password re-entry, audited).
    - RESEARCH→PAPER and PAPER→LIVE_CANDIDATE require a passing validation report for the exact version. Phase 4 produces those, so promotion is refused until then.
    - A code or parameter change sends a strategy back to RESEARCH.
  - Signal engine (worker, 16:45 NY): runs every active strategy on stored daily bars for benchmarks and watchlist symbols in the universe. RESEARCH signals are `shadow`; PAPER signals are orderable.
  - Risk engine (`core/risk/engine.py`): one pure function that records every check, approved or not, in `risk_decisions`.
    - Capital base = min(broker equity, policy `starting_equity_usd`).
    - Entry checks: kill switch, strategy status, fresh account snapshot (≤3 min, no future timestamps), account not blocked, **broker-side shorting disabled**, entry window, universe membership and freshness, earnings blackout (**fails closed: no earnings data source yet**), fresh two-sided quote, spread ≤ 25 bps, no existing exposure, daily loss and drawdown (in dollars of the capital base), concurrent positions, trades per day, and a stop below the limit price.
    - Sizing is the minimum of: risk per trade (with stop slippage), position allocation, order notional, gross exposure, cash buffer, and the sector budget (unknown sectors pooled into one sector).
    - Exits are blocked only by the kill switch, account problems, a closed market or a missing price.
  - Pipeline (executor, every 5 minutes in session): acts only on the previous session's signals; older ones expire.
    - A rejection caused only by missing or stale data (quote, account, entry window) is retried until the window closes; anything else is a final rejection.
    - Shadow signals get their decision recorded and are never ordered. Approved paper signals go through the state machine (CANDIDATE→VALIDATED→RISK_APPROVED) and `submit_idempotent`, with a final kill-switch check just before submission.
    - Client order ids come from the signal, so a rerun can't double-submit. Each signal commits separately.
  - Protection (each broker sync): every filled entry gets a **GTC broker-side stop** at the signal's stop price, covering partial fills. The stop is re-placed if an exit fails.
    - Stops covering more than is held are cancelled. Alpaca accepts stop-sells without a position (verified live), and one could open a short.
    - Protective stops may be placed, and are kept, while the kill switch is engaged: they reduce risk, and the kill switch never liquidates.
    - Exits cancel the stop and confirm the cancel before selling. If the stop filled first, the exit is skipped.
  - Kill switch now cancels open orders one by one and **keeps protective stops**.
  - Daily bars now come from **SIP** (consolidated, with a 16-minute free-plan delay), so strategies see real highs, lows and volume, not IEX-only prints.
  - API: `/api/v1/strategies` (+ admin status change), `/signals`, `/risk-decisions`, `/orders`. No endpoint can create an order.
  - Dashboard: Strategy Lab (strategies, params, status control, signals), Live Trading (signals and paper orders), Risk Center (recent rejections, capital base).
- REST minute ingestion now resumes from its own coverage (rows with its source), so a gap the stream missed during a disconnect is backfilled.
- Data prep: NYSE (XNYS) calendar covering holidays, early closes and DST; bar validation (ordering, duplicates, OHLC consistency, stale data, gaps, future timestamps, extreme moves); Alpaca bar adapter.
- Integrations: Telegram notifier (redaction, dedupe, per-event preferences); provider-agnostic LLM interface with an Anthropic structured-output adapter and an untrusted-content policy.
- Workers: Celery `default` and `execution` queues, beat schedule in New York time, heartbeats.
- Dashboard: Next.js 16 with login, Overview, Risk Center (kill switch), Settings, and placeholder pages that say plainly what isn't built yet. PAPER banner on every page.
- Ops: Docker Compose (credentials isolated per container), Dockerfiles, CI (lint, types, tests with Postgres, pip-audit, npm audit, gitleaks, compose validation), Dependabot, backup script, docs.

## Test results (local, 2026-10-25)
- Backend: **282 passed, 0 failed** (unit, failure scenarios, PostgreSQL integration). Phase 3 adds tests for indicators (hand-computed values), strategies and the registry, the risk engine (each rule failing alone), the signal engine, and the order pipeline against the FakeBroker (approvals, shadow mode, transient vs final rejections, broker rejection, lost response, protective stops, orphan stops, exits, kill switch). Stream client tests run against a local fake of Alpaca's WebSocket protocol and cover auth, subscribe, parsing, drop and reconnect, growing backoff, 402/405/406, the watchdog, and live subscription changes.
- Migrations 0002–0004: upgrade, downgrade and upgrade again on PostgreSQL 16; `alembic check` finds no drift between models and schema.
- **Live Alpaca paper (2026-10-25):** `check_alpaca` passed all 5 checks (paper endpoint, ACTIVE paper account, clock, 22-session calendar cross-check against XNYS, SPY daily bars validated). Live ingestion into PostgreSQL: 1,100 daily bars and 4,312 regular-hours minute bars across 4 symbols, all OK and none stale. An immediate re-run fetched incrementally (4 bars rewritten).
- `ruff check`, `ruff format --check`, `mypy atlas`: clean. `pip-audit`: no known vulnerabilities.
- Dashboard: `tsc --noEmit` and `next build` pass.
- **Live Trading page end-to-end (Playwright, 26/26 checks)**, against the production build, the real API, PostgreSQL (the live 2,684-symbol universe) and Redis. Redis held Alpaca's real latest quotes, fetched over REST because the stream host is blocked, and the stream service's real status. Checked:
  - quotes render and are correctly stale with the market closed; one-sided quotes show "—"
  - the board polls, and a simulated API outage un-vouches all quotes
  - create a watchlist, add AMD by searching "advanced micro", remove it, delete the list
  - duplicate-name error is shown
  - viewer sees no edit controls, and the API refuses a viewer write (403)
  - no horizontal scroll at 390 px; no console errors besides the deliberately provoked 400/503
- End-to-end, run by hand with Playwright against local Postgres, Redis, API, worker, beat and the dashboard:
  - login (a wrong password is rejected)
  - httpOnly cookie that page scripts can't read
  - kill switch resume and engage through the UI
  - worker heartbeat
  - executor without credentials fails safely and reports broker `error`

## Not tested / known limitations
- **Phase 3 live checks (2026-10-26):**
  - **Data:** SIP daily ingestion for 41 symbols (11,093 bars, none stale).
  - **Signals:** the engine ran on the 2026-10-23 close in 0.6 s. RSI(2) pullback gave entries on AMZN, META and SNDK (META checked by hand: RSI 2.75, close above the 200-SMA, stop = close − 2.5×ATR). SPCX was correctly skipped for short history; there were no breakouts.
  - **Order round trip on the Alpaca paper account:** a non-marketable limit buy (1 SPY at $100) was submitted, resubmitting returned the same order, a lookup by client id worked, and the cancel was confirmed. The account ended with no orders or positions.
  - **Found live:** Alpaca accepted a GTC stop-sell with no position (it was cancelled). That led to the orphan-stop cleanup and the broker long-only check.
  - **Broker sync:** snapshots now record `shorting_enabled=true, multiplier=4` for this account.
  - **Playwright:** 14/14 Phase 3 checks (Strategy Lab with the real signals, refused promotion with its reason, signals and orders on Live Trading, rejections on Risk Center, viewer restrictions, no horizontal scroll at 390 px). The 26/26 Phase 2 Live Trading checks still pass.
  - **Not yet run:** shadow risk evaluation of those signals in a live session. It runs from 09:35 on the next session; the market was closed.
- **Live universe (2026-10-25):** 14,398 active assets → 2,684 members (as of 2026-10-23) in 26 s. Exclusions: 7,045 below the dollar-volume minimum, 3,364 below $10, 894 not tradable, 308 OTC, 96 too little history, 5 no print on `as_of`, 2 no data. Lowest member close is $10.00 and lowest dollar volume $20.0M, exactly at the policy limits. A watchlist with an OTC symbol was rejected with its reason; a valid one was created and audited, and ingestion and the stream picked up its symbols.
- **No strategy can place paper orders yet.** That's by design: promotion needs Phase 4 validation reports. Even then, with the current policy and account, every entry is rejected for two reasons:
  - **No earnings calendar:** `block_entries_before_earnings_days: 2` with no data source fails closed. Fix: add an earnings data source (needs a provider and API key), or set the value to 0 in a reviewed policy change.
  - **The paper account allows shorting** (and 4× margin): see Required user action.
- RESEARCH strategies have no simulated positions, so shadow mode records entries but never exits. Shadow performance belongs to the Phase 4 backtester.
- No sector data: all holdings share one 25% "unknown sector" budget, which effectively caps gross exposure at 25% (policy allows 50%).
- Protective stops are GTC; the policy's `order_time_in_force: day` applies to entries and exits. A GTC stop protects across sessions, but gaps through the stop fill at the open price.
- Strategies use daily bars only; intraday bars and quotes are used for execution checks, not signals.
- `/status` crashed with a 500 once any account snapshot existed (Decimal − float), and its total P/L compared equity to the policy budget (it would have shown +$90,000 on this account). Fixed: total P/L is now measured from ATLAS's first broker sync.
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
5. ~~Dashboard: watchlist and live prices on the Live Trading page~~ — done.

Phase 2 exit check still open: run the stream live (Alpaca test feed, then IEX during market hours) once `stream.data.alpaca.markets` is allowed.

## Next engineering tasks (Phase 4)
1. Event-driven backtester in `core/backtesting` reusing the strategy, sizing and risk-engine code, with cost, spread, slippage, gap and partial-fill models (ADR 0003).
2. Walk-forward and out-of-sample validation, parameter-stability screens, and validation reports that `passing_validation_report()` can accept, which unlocks gated promotion.
3. Simulated positions for shadow strategies, so they can be compared like for like with backtests.
4. Earnings calendar and sector classification sources (both currently fail closed).

## Required user action
- Alpaca paper keys: in place and verified. For Docker, make sure they are in `atlas/broker.env` (never in chat or git).
- **Disable shorting and margin on the Alpaca paper account.** The policy is long-only with no margin, and ATLAS rejects entries until the broker enforces it too: Alpaca dashboard → paper account → Configure, or `PATCH /v2/account/configurations` with `{"no_shorting": true, "max_margin_multiplier": "1"}`. `check_alpaca` reports the current setting.
- Decide on earnings data: connect a provider (needs an API key), or set `block_entries_before_earnings_days: 0` in a reviewed policy change.
- Optional: the paper account holds $100,000 while the policy budget is $10,000. ATLAS sizes to $10,000 either way. You could reset the paper account to $10,000 in Alpaca, or raise `starting_equity_usd` in a reviewed policy change.
- Optional: Telegram bot token and chat id in `atlas/.env`; Anthropic key in `atlas/llm.env`.
