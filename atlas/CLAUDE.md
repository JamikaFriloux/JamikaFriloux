# CLAUDE.md — persistent rules for ATLAS

ATLAS is a research-driven algorithmic trading system for US stocks/ETFs. **This deployment
is PAPER TRADING ONLY.** Profitability is a hypothesis to test, never a claim.

## Non-negotiable architecture rules
1. Never add a code path that can reach a live brokerage endpoint. `TradingClient` is always
   built with the literal `paper=True`; never use `url_override`; never relax the validators
   in `core/configuration/settings.py`. `tests/unit/test_paper_isolation.py` must stay green.
2. Broker credentials exist only in the `executor` service (`broker.env`). The API, research
   worker, agents and dashboard must never import `BrokerSettings` or the Alpaca SDK.
3. LLM output is advisory. It is parsed into Pydantic schemas and never becomes an order,
   a risk-limit change, or a config change. Wrap external text with `wrap_untrusted()`.
4. The risk engine is deterministic and has final authority. No agent or LLM can override,
   bypass or modify it at runtime. Risk limits change only via reviewed edits to
   `config/policy.yaml`, bounded by `HARD_LIMITS`.
5. Every order goes through the state machine (`core/execution/state_machine.py`) and
   `submit_idempotent`. Never resubmit an uncertain order without querying the broker.
6. Fail closed: on missing/stale data, DB errors, or critical uncertainty, do not open
   positions. The kill switch starts engaged and only an admin can resume it.
7. Never fabricate data: no placeholder balances, indicator values, prices or sources. Show
   "unavailable" instead.
8. Strategies never self-promote. RESEARCH → PAPER → LIVE_CANDIDATE requires the gates in the
   spec; LIVE_CANDIDATE still cannot submit live orders.
9. Never log secrets. Use `core/observability/logging.py`; don't log URLs containing tokens.
10. Timestamps are timezone-aware UTC in storage; market logic uses the XNYS calendar.

## Conventions
* Python 3.12+, typed, `ruff` + `ruff format` (line length 100), `mypy atlas` clean.
* Money is `Decimal`/`Numeric`, never float in persistence.
* New tables → Alembic migration in `backend/migrations/versions` (hand-check autogenerate).
* Tests: unit tests use SQLite; PostgreSQL behavior (triggers, constraints) goes in
  `tests/integration` and runs with `ATLAS_TEST_DATABASE_URL`.
* Failure scenarios (timeouts, duplicates, partial fills, outages) go in
  `tests/failure_scenarios` with the `FakeBroker` in `tests/fakes.py`.
* Dashboard: Next.js App Router, server components fetch the API with the httpOnly session
  cookie; every trading page shows the PAPER badge.
* Default LLM model: `claude-opus-5-5` via `integrations/llm` (provider-agnostic interface).

## Commands
```
cd atlas && make test lint typecheck
cd atlas/dashboard && npm run build
```
Keep `STATUS.md` current at the end of each phase.
