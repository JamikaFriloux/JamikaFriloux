# ATLAS project status

_Last updated: 2026-10-26: Phase 7 reference data built. ETFs are now cleared for the earnings check and exposure is capped per sector. Stocks still need an earnings calendar (a provider key plus network access), and the paper account must disable shorting before any entry can pass. Both baselines remain eligible for PAPER, unpromoted._

| Phase | State |
|---|---|
| 1 Foundation | **Complete** |
| 2 Market data | **Built; one live check outstanding**: Alpaca paper connectivity verified live (`check_alpaca` passes). Daily and minute bar ingestion with stored quality reports is built and tested live. The live WebSocket stream is built and tested against a local fake server, but not yet against Alpaca (this environment blocks the stream host). The universe screen with point-in-time snapshots, watchlist management and the Live Trading dashboard are built and tested live |
| 3 Trading engine | **Built**: indicators, strategy framework with 2 baseline strategies, signal engine, deterministic risk engine with sizing, signal→order pipeline, broker-side protective stops, exits, dashboard. Strategies run in RESEARCH (shadow); paper orders start only after a strategy passes Phase 4 validation |
| 4 Backtesting & promotion gates | **Built**: event-driven simulator reusing the production strategy, sizing and risk code; cost, gap and partial-fill models; validation gates in `policy.yaml`; immutable validation reports; gated promotion wired. Both baselines pass all 10 gates on 9.7 years of real data, after the drawdown cooldown rule |
| 5 AI research agents | **Built; LLM output not yet verified live**: five advisory agents (market regime, technical analysis, news sentiment, performance, operations). Their deterministic features run live on real data; the AI narratives are tested with recorded responses only, because no Anthropic key is configured here |
| 6 Performance & track record | **Built; no paper record yet**: paper trade ledger, account metrics vs SPY, an out-of-sample forward test per strategy, LIVE_CANDIDATE gates on the paper record, Performance page. There are no paper fills or recorded session closes yet, so paper and account sections are empty by design |
| 7 Reference data | **Built; providers blocked here**: reviewed `config/instruments.yaml` (14 ETFs, 23 stock sectors), per-sector exposure limits, an earnings calendar with fail-closed clearance, SEC EDGAR and Finnhub adapters. The providers' hosts are blocked by this environment's network policy, so stocks have no earnings clearance yet |
| 8 | Not started |

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
- **Drawdown halt with cooldown** (`core/risk/drawdown.py`, `policy.yaml` `limits.drawdown_cooldown_sessions: 20`).
  - A session close ≥ the drawdown limit below the high-water mark halts new entries. They stay blocked for the next 20 sessions; at the close of the 20th, the high-water mark resets to that close and drawdown is measured from there.
  - Intraday breaches still block entries at that moment but don't start a cooldown. Exits are never blocked.
  - Production replays recorded session-close equity (`equity_closes`, migration 0006, written after each broker sync). If the reset close was missed, it resets to live equity. The backtester steps the same function at each simulated close.
  - `/api/v1/status` and the Risk Center show the high-water mark, current drawdown, limit and any cooldown.
- **Phase 4, backtesting and promotion.**
  - Simulator (`core/backtesting/simulator.py`): a daily event loop on the live schedule.
    - Entries and exits happen at the next open, plus 5 minutes, through `risk.engine.evaluate` with a synthetic quote. Limit orders are priced as in production and fill only if the modeled price (± half spread ± slippage) is within the limit, capped at `max_participation_pct` of session volume (partial fills).
    - Protective stops fill at the open on gaps, otherwise at the stop, less spread and stop slippage. SEC and FINRA fees are charged on sells.
    - The universe is point-in-time: the production `liquidity_screen` runs on raw bars up to the previous session.
    - Optimised from 185 s to about 25 s for 10 years × 41 symbols with identical results (trusted pre-validated windows, O(n) rolling extremes, tail-only indicator windows, shared eligibility).
  - Validation (`core/backtesting/validation.py`): gates for history, trades, profit factor, Sharpe, drawdown, holdout trades and Sharpe (last 2 years), walk-forward (12-month windows), parameter stability (±10% one at a time) and bootstrap (95% lower bound of mean trade return).
    - Thresholds come from `policy.yaml` `promotion_gates`, with code floors so they can only be tightened; the cost model comes from `backtest`.
    - Every report records the simulator's caveats, including survivorship bias.
  - Reports (`validation_reports`, migration 0005, immutable at the database level). `passing_validation_report()` accepts only a passing report for the exact version, parameters and policy hash, no older than 90 days. LIVE_CANDIDATE still accepts nothing: it needs a paper track record, which isn't built.
  - Running it:
    - Worker task `validate_strategy`, queued by an admin from the Strategy Lab (`POST /api/v1/strategies/{id}/validate`), or `make validate STRATEGY=…`.
    - History comes from `atlas.scripts.backfill_history` once; daily ingestion then keeps both adjusted and raw bars current.
    - Data quality reports now record which adjustment they cover.
  - Dashboard: Strategy Lab shows each strategy's latest validation, a "Run validation" button (admin) and a report page (gates, equity curve with tooltip and data table, full and holdout metrics, walk-forward windows, parameter neighbours, risk-engine rejections, caveats).
  - Fixed in Phase 3 code: the signal engine now evaluates exits for every held position even after its symbol leaves the universe or watchlists. Before, only the protective stop could close such a position.
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
- **Phase 5, AI research agents (advisory only).**
  - Framework (`agents/base.py`): each agent computes **features** deterministically (the source of truth), then optionally asks the LLM for a **narrative** parsed into a Pydantic schema and re-checked in code. One `agent_reports` row per run (migration 0007) with features, narrative, status, model and token counts.
    - Statuses: `ok`, `no_llm` (provider disabled), `budget` (daily cap), `no_data`, `refused`, `llm_error`. Failures are recorded, never raised into trading.
    - Identical inputs reuse the previous report (input hash over features, untrusted text, prompt version and model), and `ATLAS_LLM_MAX_CALLS_PER_DAY` (default 40) caps model calls per New York day across all agents.
    - Every prompt says the features are authoritative and forbids order, sizing or limit recommendations. Nothing in the trading path reads agent reports; a test forbids agents from importing execution, broker or status-changing code.
  - **Market Intelligence:** a deterministic regime from SPY daily bars. Trend comes from close vs SMA50/SMA200. Volatility is the 20-day realised vol ranked against its own year (high ≥ 80th percentile or > 30%). Breadth is the share of ingested symbols above their SMA50. The labels are risk_on, volatile_uptrend, transition, downtrend and risk_off. The LLM never sets the label. It feeds `/status` `market_regime` and the Overview card.
  - **Technical Analysis:** an indicator snapshot of every ingested symbol (trend, distance from SMA20/50/200, RSI14, ATR%, 20-day return, 20-day range position), with stale and missing-history lists. The narrative may name only symbols in the snapshot.
  - **News Sentiment:** the executor fetches Alpaca news every 30 minutes (`fetch_news`, `news_articles`; HTML stripped, entities decoded; updated articles refreshed). The worker sends the last 24 h of articles for watched symbols (max 40) with each headline and summary in `wrap_untrusted()`. The article id and its symbols sit outside the wrapper.
    - The output is rejected if it assesses an article or symbol that wasn't supplied, or assesses one twice.
    - The model flags articles that try to instruct it (`injection_suspected`), and the dashboard marks them.
    - Without an LLM, sentiment shows as unavailable; it is never guessed.
  - **Performance:** account, drawdown and cooldown, equity-close curve, strategy statuses with their latest validation, and 5-session signal, risk-decision (with top rejection reasons) and order counts. Money stays Decimal (strings in JSON).
  - **Operations:** heartbeats, using the health check's staleness rule (moved to `core/observability/heartbeats.py`): continuous services go stale after 3 minutes, scheduled jobs show their last run. Also the kill switch, 24 h data quality, universe freshness, news freshness and agent statuses.
  - Worker task `run_agents` at 08:40 and 17:40 NY on weekdays, or on demand (operator+) via `POST /api/v1/intelligence/run`. One agent failing doesn't stop the others. With `provider=anthropic` but no key, it runs features-only instead of crashing.
  - API: `GET /api/v1/intelligence` (latest per agent, today's LLM usage), `/intelligence/reports[/{id}]`, `GET /api/v1/news` (articles joined with the latest assessment; only `https://` links are returned).
  - Dashboard: the AI Intelligence page (regime facts, performance digest, technical table with AI notes, news feed with sentiment badges, operations), the "Run agents now" button for operators, and the regime badge on Overview. AI text is labelled as AI with model and token count; external headlines render as plain text with `noopener` links.
- **Phase 6, performance and track record.**
  - Paper ledger (`core/performance/ledger.py`): round trips rebuilt FIFO per strategy and symbol from filled orders (entries open lots; exits and protective stops close them).
    - The fill date is the last fill event. Risk per share comes from the signal's stop, or the protective stop order. Fees are 0, as on Alpaca paper.
    - Sells with no ATLAS lot are reported as unmatched, never turned into trades.
    - Trades use the backtester's `Trade` type, so paper and backtest statistics come from the same `summarize()` code.
  - Account (`core/performance/account.py`): metrics from `equity_closes` (return, CAGR, Sharpe, Sortino, max DD) and a SPY comparison over the same sessions (excess return, SPY drawdown, correlation, beta). Fewer than two closes gives "unavailable", not an estimate.
  - Track records (`core/performance/track_record.py`, `track_records`, migration 0008), recomputed by worker task `update_track_records` at 17:05 NY on weekdays (one row per strategy, kind and session; re-runs replace it):
    - `forward_sim`: the validation simulator, with the same strategy, risk engine, costs and symbols as the anchoring validation report, run **only on sessions after that report's data ended**. Out of sample by construction, and computed for RESEARCH strategies too, which closes the "shadow strategies have no positions" gap without touching the order path. Positions still open are reported as open, not as trades.
    - `paper`: the strategy's own paper round trips for the current version since its latest RESEARCH→PAPER promotion (from the audit log), judged against the new `track_record_gates` in `policy.yaml`: sessions ≥ 60, closed trades ≥ 20, profit factor ≥ 1.1, drawdown ≤ 10% of budget on cumulative realised P&L, avg R ≥ 0.5× the validation report's avg R. Code floors stop the gates from being loosened.
  - Promotion: PAPER→LIVE_CANDIDATE now requires a passing paper record for the exact version, parameters and policy hash, at most 7 days old. The record id is written to the audit entry.
  - **LIVE_CANDIDATE now keeps paper trading.** Before, the risk engine required exactly PAPER, so promoting a strategy would have stopped its orders and frozen its record. It still cannot place a live order: the broker client is paper-only at 7 layers.
  - API: `GET /api/v1/performance` (account, each strategy's backtest reference, latest forward and paper records, LIVE_CANDIDATE eligibility, gate settings) and `GET /api/v1/track-records/{id}` (curve and trades).
  - Dashboard Performance page:
    - Account stats and a chart of the account vs SPY, both indexed to 100. Colors pass the palette validator on the dark surface.
    - A per-strategy table comparing backtest, forward test and paper record.
    - Simulated open positions.
    - LIVE_CANDIDATE gate results with values and thresholds.
- **Phase 7, reference data** (`core/reference`, migration 0009).
  - `config/instruments.yaml`, reviewed like `policy.yaml`:
    - 14 ETFs with exposure buckets: broad US equity, semiconductors, treasuries, credit, gold. Leveraged funds are flagged.
    - GICS sectors for 23 stocks.
    - BE, CRWV, NBIS and SPCX are deliberately left out: I couldn't name their classification with confidence, so they stay unclassified and fail closed.
    - The file is validated strictly: symbol format, no symbol listed as both ETF and stock, the "unknown" name reserved, extra keys rejected.
  - Providers (executor, optional):
    - **SEC EDGAR** (`integrations/sec/edgar.py`, no key, contact User-Agent, ≤ 10 req/s): ticker → CIK → SIC → approximate GICS sector (`sectors.py`). Fills only symbols the config doesn't cover; config always wins.
    - **Finnhub** earnings calendar (`integrations/finnhub/earnings.py`): the key goes in a header, never the URL.
    - A fetch replaces the source's events in its window (moved dates are handled) and records an `earnings_coverage` row. Failures keep stored data and alert.
  - Earnings clearance (`earnings.py`), for today plus the next N sessions (policy N = 2):
    - ETF → clear.
    - A stored report in the span → blackout, even if the calendar is old.
    - A classified stock with a calendar under 30 h old covering the span and no report → clear.
    - Anything else → unknown, so the risk engine rejects the entry. An unclassified symbol is never cleared by its absence from a calendar.
  - Per-sector exposure: the pipeline passes the symbol's bucket and that bucket's exposure (positions plus open buy orders). `max_sector_exposure_pct` now caps each bucket; unclassified symbols share "unknown". The backtester passes no sector data and keeps the stricter single bucket, so validation results are unchanged.
  - Executor task `refresh_reference_data` (06:30 and 17:30 NY on weekdays; heartbeat `reference` ok/degraded/error). `execute_signals` builds the blackout and sector lookups from it.
  - API `GET /api/v1/reference` and a Risk Center card: clearance per watched symbol, sector buckets with held exposure, calendar coverage, upcoming reports.
- Workers: Celery `default` and `execution` queues, beat schedule in New York time, heartbeats.
- Dashboard: Next.js 16 with login, Overview, Risk Center (kill switch), Settings, and placeholder pages that say plainly what isn't built yet. PAPER banner on every page.
- Ops: Docker Compose (credentials isolated per container), Dockerfiles, CI (lint, types, tests with Postgres, pip-audit, npm audit, gitleaks, compose validation), Dependabot, backup script, docs.

## Test results (local, 2026-10-26)
- Phase 7: backend **404 passed, 0 failed** (35 new tests).
  - Instrument file validation and the repository file; config upsert, removal and idempotence, with provider rows untouched.
  - SIC mapping.
  - EDGAR and Finnhub against mocked HTTP: User-Agent, token only in a header, malformed rows, errors.
  - Calendar replacement and dedupe.
  - Every blackout rule: ETF; no calendar; report in and out of the span; stale calendar; window not covering the span; unclassified symbol; weekend span.
  - Refresh with providers, failing providers and none.
  - Engine sector cap and its reason text; a pipeline test where the same order is rejected when an existing holding shares its sector and placed when it doesn't.
  - Refresh task success, and an invalid config that alerts and keeps data; API.
- Phase 7 live (2026-10-26):
  - Migration 0009 applied; `alembic check` shows no drift.
  - `refresh_reference_data` classified 37 instruments (14 ETFs, 23 stocks). BE, CRWV, NBIS and SPCX are unclassified as intended.
  - The SEC EDGAR fetch failed with `ProxyError` (host blocked here). It was reported as a degraded heartbeat plus an alert, and nothing was deleted.
  - Now: the 14 ETFs are cleared for earnings; the 27 stocks and unclassified symbols are not.
- Playwright, Risk Center, 8/8: clearance counts (14 clear, 27 none), "no earnings calendar" warning, ETF tags, unknown bucket listing BE, CRWV, NBIS and SPCX, sector buckets, no console errors, no horizontal scroll at 390 px.
- Phase 6: backend **369 passed, 0 failed** (17 new tests).
  - FIFO ledger with R-multiples and protective-stop risk; unmatched sells; unpriced fills skipped.
  - Account vs SPY returns; the fewer-than-two-closes case.
  - Forward test: no report, no new data, and a real breakout after the validation window that is traded and reported as open positions. The first version of this test passed vacuously: no raw bars meant nothing passed the liquidity screen. Fixed and asserted.
  - Paper gates: pass case, expectancy-vs-backtest fail, promotion of another version not counted, no promotion fails closed.
  - LIVE_CANDIDATE promotion refused without a record, allowed with one, refused once the record is over 7 days old.
  - The risk engine lets LIVE_CANDIDATE trade paper and still blocks RESEARCH.
  - Idempotent daily update; API RBAC and 404; worker task success and failure; policy floors.
- Phase 5: backend **352 passed, 0 failed** (28 new tests).
  - Regime rules and realised vol against a hand computation.
  - Caching, budget, refusal, invalid output and no-data paths.
  - News cleaning, upsert and Alpaca parsing.
  - Untrusted wrapping, including an entity-encoded `</untrusted_content>` attack.
  - Every fabrication check; the technical symbol check.
  - End-to-end runs with and without an LLM, plus failure isolation.
  - Executor and worker tasks (news outage, missing key).
  - API RBAC and the https-only link filter.
  - The agent isolation test.
- Phase 6 live (2026-10-26):
  - Migration 0008 applied.
  - Revalidation under the new policy hash: `trend_breakout` report #5 (266 s) and `rsi_pullback` report #6 (465 s) both pass, with metrics identical to #3 and #4 (246 trades, Sharpe 0.785, PF 2.661, DD 6.93%; 1,404 trades, Sharpe 0.841, PF 1.37, DD 4.69%). The policy change doesn't touch the simulation.
  - `update_track_records` wrote a forward record for each strategy, anchored to #5 and #6. Both show 0 sessions and say why: stored data ends 2026-10-23, the last day of the validation data.
- Playwright, Performance page, 9/10 live checks plus 8/8 with sample data. The one live failure is expected: the first run came before any track record existed, and the page correctly said "not computed yet".
  - Live: honest empty account state, both strategy cards, backtest column linked to its validation report, no LIVE_CANDIDATE badge, no console errors, no horizontal scroll at 390 px.
  - Sample data (a throwaway copy of the database with 38 synthetic session closes and a synthetic promotion, dropped afterwards): account stats, two-line account-vs-SPY chart with legend and hover tooltip, paper gates with pass/fail, no console errors.
  - Fixed after looking at the screenshots: blank backtest trades, drawdown, P&L and span (now taken from the report); integers shown as "37.00"; cramped gate columns.
- Migration 0007 applied to the live database.
- **Live (2026-10-26, no LLM key):**
  - `fetch_news` stored 25 real Alpaca articles; 19 fell in the 24-hour window for 20 watched symbols.
  - `run_agents` produced all five reports from real data: SPY **risk_on** as of 2026-10-23 (close 759.97, +4.97% vs SMA200, 20-day vol 9.8% at the 17.5th percentile). Breadth is weak: 6 of 40 ingested symbols above their SMA50, and SPY itself is 0.9% below its SMA50.
  - A second run reused 4 of 5 reports (unchanged inputs, no new rows).
- Playwright, 15/15 Phase 5 checks: Overview regime badge; AI Intelligence page with deterministic facts, 41-row technical table, 25 headlines with https/noopener links, no sentiment shown without an LLM, "LLM disabled" on all five agents, run button queues a job, viewer has no button and gets 403 from the endpoint, no horizontal scroll at 390 px, no console errors. Temporary e2e users were deleted afterwards.
- Earlier phases: backend **324 passed, 0 failed** (unit, failure scenarios, PostgreSQL integration). Phase 3 adds tests for indicators (hand-computed values), strategies and the registry, the risk engine (each rule failing alone), the signal engine, and the order pipeline against the FakeBroker (approvals, shadow mode, transient vs final rejections, broker rejection, lost response, protective stops, orphan stops, exits, kill switch). Stream client tests run against a local fake of Alpaca's WebSocket protocol and cover auth, subscribe, parsing, drop and reconnect, growing backoff, 402/405/406, the watchdog, and live subscription changes.
- Migrations 0002–0006: upgrade, downgrade and upgrade again on PostgreSQL 16; `alembic check` finds no drift between models and schema.
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
- **No reference provider has been reached.** `www.sec.gov`, `data.sec.gov` and `finnhub.io` are denied by this environment's network policy (proxy 403), and no Finnhub key exists. Both adapters are tested only against recorded payloads. Until a calendar is configured, every stock entry is rejected; ETF entries pass the earnings check.
- The stock sectors in `instruments.yaml` were written from general knowledge, not a data feed. Review them, especially recent listings and spin-offs (SNDK). SIC→GICS from EDGAR is approximate: for example, internet platforms land in Information Technology.
- Sector buckets don't look through ETFs: SMH or SOXL exposure isn't counted against Information Technology stocks.
- Backtests still don't simulate earnings blackouts or per-sector limits (no history); they use one sector budget, which is stricter.
- **Phase 6 has no paper data to show yet.** No strategy is in PAPER, no paper order has filled, and `equity_closes` holds no sessions in this database, because the executor isn't running here. The Performance page shows those sections as unavailable. The forward test starts after 2026-10-23, the end of the validation data, so it accrues one session per trading day once the daily ingestion runs.
- The paper drawdown gate uses cumulative **realised** P&L on the budget, marked at session closes. Open-position swings aren't included until the trade closes. The account-level drawdown, which includes them, is shown separately.
- Account metrics cover the whole paper account ($100k) while ATLAS sizes against $10k, so account returns are diluted about 10×. Per-strategy records use the $10k budget.
- **No live LLM call has been made.** No `ATLAS_LLM_ANTHROPIC_API_KEY` exists in this environment, so the Anthropic provider is tested only against a mocked client and the agents with recorded responses. First live check: put the key in `atlas/llm.env`, set `ATLAS_LLM_PROVIDER=anthropic`, then click "Run agents now" and read the five narratives. Token use is shown per report; at most 5 calls per run, 2 scheduled runs a day.
- Phase 5 agents are advisory and deliberately unread by the trading path. The regime is not used as a strategy filter; that would be a strategy change requiring revalidation.
- Strategy Research and Quantitative Research agents (proposing new hypotheses) are not built. Their packages are empty: any proposal would need the backtester and gates, and that workflow isn't designed yet.
- News comes from Alpaca's feed only (mostly Benzinga), headline and summary only; full article bodies aren't fetched. Breadth covers the ~41 ingested symbols, not the market.
- **Revalidation with the 20-session cooldown (2026-10-26).** The new policy hash made the earlier reports ineligible for promotion; they remain stored as records.
  - `trend_breakout` (report #3): **passes 10/10.**
    - 246 trades, PF 2.66, avg +1.03R, Sharpe 0.79, CAGR 4.1% (+47.6% over 9.7 years on a $10k budget), max DD 6.9%.
    - Holdout: 47 trades, Sharpe 1.23. 7/10 windows profitable, 10/10 neighbours profitable, bootstrap lower bound +2.4%.
    - 7 drawdown halts, each reset exactly 20 sessions later (first 2020-02-27 → 2020-03-26). Max DD exceeds the 5% limit because halts block new entries but open positions keep moving until their stops or exits.
  - `rsi_pullback` (report #4): **passes 10/10.**
    - Its own path is unchanged: it never breached the limit (max DD 4.7%). Neighbours are now 13/13 profitable (6/13 before), confirming the earlier failure was the permanent-halt cliff.
    - 1,404 trades, Sharpe 0.84, CAGR 1.75%, holdout Sharpe 2.12.
  - `passing_validation_report()` now returns #3 and #4: **both are eligible for promotion to PAPER. Neither was promoted.**
  - Read with the caveats: today's most liquid names (incl. NVDA, MU, leveraged ETFs) were selected with hindsight, which flatters these numbers.
  - Playwright: Strategy Lab shows both as passed and promotable; report pages and the Risk Center render without horizontal scroll at 390 px.
- **Phase 4 live validation (2026-10-26), before the cooldown rule.** 10.5 years of SIP daily history (adjusted and raw, 98,176 bars each, 2016-04-26 → 2026-10-23) for 41 symbols. Simulated 2017-02-10 → 2026-10-23 with a $10,000 budget under the real policy.
  - `trend_breakout`: **fails** 6 of 10 gates. 77 trades, profit factor 2.08, avg +1.05R, Sharpe 0.43, max DD 5.5%, all 10 neighbours profitable.
    - **The 5% drawdown limit halted new entries on 2020-04-14 and never released** (4,208 entries blocked; 0 trades in the 2-year holdout).
  - `rsi_pullback`: **fails 1 of 10 gates** (stability, 6/13 neighbours profitable). 1,404 trades, Sharpe 0.84, PF 1.37, max DD 4.7%, holdout Sharpe 2.12, 8/10 walk-forward windows profitable, bootstrap lower bound +0.27%.
    - The 7 losing neighbours made only 330–380 trades against ~1,400 for the winners. Checked directly: `stop_atr=2.25` was halted by the drawdown limit on 2019-06-03, down only $190, and never traded again. **The stability failure is the same permanent-halt cliff, not parameter fragility.**
  - Playwright: 15/15 Phase 4 checks (validation on the Strategy Lab, promotion still refused, queued validation, report gates/chart/tooltip/tables/caveats, 404 for unknown reports, viewer restrictions, no horizontal scroll at 390 px after fixing an 88 px overflow).
- **Phase 3 live checks (2026-10-26):**
  - **Data:** SIP daily ingestion for 41 symbols (11,093 bars, none stale).
  - **Signals:** the engine ran on the 2026-10-23 close in 0.6 s. RSI(2) pullback gave entries on AMZN, META and SNDK (META checked by hand: RSI 2.75, close above the 200-SMA, stop = close − 2.5×ATR). SPCX was correctly skipped for short history; there were no breakouts.
  - **Order round trip on the Alpaca paper account:** a non-marketable limit buy (1 SPY at $100) was submitted, resubmitting returned the same order, a lookup by client id worked, and the cancel was confirmed. The account ended with no orders or positions.
  - **Found live:** Alpaca accepted a GTC stop-sell with no position (it was cancelled). That led to the orphan-stop cleanup and the broker long-only check.
  - **Broker sync:** snapshots now record `shorting_enabled=true, multiplier=4` for this account.
  - **Playwright:** 14/14 Phase 3 checks (Strategy Lab with the real signals, refused promotion with its reason, signals and orders on Live Trading, rejections on Risk Center, viewer restrictions, no horizontal scroll at 390 px). The 26/26 Phase 2 Live Trading checks still pass.
  - **Not yet run:** shadow risk evaluation of those signals in a live session. It runs from 09:35 on the next session; the market was closed.
- **Live universe (2026-10-25):** 14,398 active assets → 2,684 members (as of 2026-10-23) in 26 s. Exclusions: 7,045 below the dollar-volume minimum, 3,364 below $10, 894 not tradable, 308 OTC, 96 too little history, 5 no print on `as_of`, 2 no data. Lowest member close is $10.00 and lowest dollar volume $20.0M, exactly at the policy limits. A watchlist with an OTC symbol was rejected with its reason; a valid one was created and audited, and ingestion and the stream picked up its symbols.
- Drawdown rule: a 20-session cooldown, then a high-water-mark reset (chosen 2026-10-26). A halt doesn't liquidate, so realised drawdown can exceed the limit while open positions run to their stops (6.9% in the trend backtest).
- Backtest caveats, recorded in every report:
  - The symbol list is today's (survivorship bias).
  - Earnings blackouts and sectors aren't simulated; there is no historical data for them.
  - Fills come from daily bars.
  - The 41 symbols include leveraged ETFs (SOXL, TQQQ).
- Validation results are simulations under stated assumptions, not predictions.
- **No strategy places paper orders yet.** Promotion is an admin decision (both baselines are eligible). Even after promotion, with the current account:
  - **Shorting is enabled on the paper account:** every entry is rejected until it is disabled (Required user action).
  - **No earnings calendar for stocks:** stock entries fail closed until a calendar is connected (Phase 7). ETFs in `config/instruments.yaml` are cleared.
- RESEARCH strategies have no positions in the order path, so shadow mode records entries but never exits. Their like-for-like record is the Phase 6 forward test.
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

## Next engineering tasks
1. **Promotion decision (admin):** both baselines are eligible for PAPER. Even after promotion, entries stay blocked until (a) shorting is disabled on the Alpaca paper account and (b) an earnings calendar is connected or `block_entries_before_earnings_days` is set to 0.
2. ~~Simulated positions for shadow strategies~~: done in Phase 6 (out-of-sample forward test).
3. Connect the earnings calendar: a Finnhub key in `broker.env` plus `finnhub.io` allowed outbound (and `www.sec.gov` / `data.sec.gov` for EDGAR sectors). Then check one live refresh on the Risk Center.
4. First live LLM run of the Phase 5 agents once an Anthropic key is configured; review narrative quality and token cost.
5. Strategy/quantitative research agents that propose hypotheses for the backtester (design needed first).

## Required user action
- Alpaca paper keys: in place and verified. For Docker, make sure they are in `atlas/broker.env` (never in chat or git).
- **Disable shorting and margin on the Alpaca paper account.** The policy is long-only with no margin, and ATLAS rejects entries until the broker enforces it too: Alpaca dashboard → paper account → Configure, or `PATCH /v2/account/configurations` with `{"no_shorting": true, "max_margin_multiplier": "1"}`. `check_alpaca` reports the current setting.
- Earnings data for stocks: get a Finnhub API key (free tier) and set `ATLAS_REFDATA_FINNHUB_API_KEY` in `broker.env`, and allow `finnhub.io`, `www.sec.gov` and `data.sec.gov` in this environment's network settings. ETFs no longer need it.
- Optional: the paper account holds $100,000 while the policy budget is $10,000. ATLAS sizes to $10,000 either way. You could reset the paper account to $10,000 in Alpaca, or raise `starting_equity_usd` in a reviewed policy change.
- Optional: Telegram bot token and chat id in `atlas/.env`.
- **For AI narratives (Phase 5):** Anthropic API key in `atlas/llm.env` (`ATLAS_LLM_ANTHROPIC_API_KEY`) and `ATLAS_LLM_PROVIDER=anthropic`. Without it the agents still run and show their deterministic analysis.
