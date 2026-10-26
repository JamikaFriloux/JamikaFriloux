# ATLAS architecture

```
              ┌──────────────┐  httpOnly cookie   ┌──────────┐
  operator ──▶│  dashboard   │ ─────────────────▶ │   api    │── PostgreSQL (system of record)
              │  (Next.js)   │   Bearer token     │ FastAPI  │── Redis (rate limits)
              └──────────────┘                    └────┬─────┘
                                                       │ send_task (kill switch follow-up)
                     ┌───────── Redis (Celery) ◀───────┘
        ┌────────────┴──────────┐
  ┌─────▼─────┐           ┌─────▼──────┐      Alpaca PAPER API
  │  worker   │           │  executor  │ ───▶ paper-api.alpaca.markets
  │ research, │  (no      │ broker sync│      data.alpaca.markets
  │ LLM agents│  broker   │ orders,    │      stream.data.alpaca.markets (WebSocket)
  │ reports   │  creds)   │ kill switch│
  └───────────┘           │ bar ingest │
                          │ live stream│ ──▶ Redis (latest quotes) ──▶ api /market/live
                          └────────────┘
```

The executor process (`python -m atlas.apps.executor.run`) runs the Celery `execution`
worker and the live market-data stream side by side, because both need the broker keys
and only this container has them. If either exits, both stop and the container restarts.

## Order lifecycle (deterministic)
`CANDIDATE → VALIDATED → RISK_APPROVED → SUBMITTED → ACKNOWLEDGED → PARTIALLY_FILLED / FILLED / CANCELLED / REJECTED / EXPIRED`

Implemented in `atlas/core/execution/state_machine.py`; every transition writes an
`order_events` row. Illegal transitions raise.

## Trading flow (Phase 3)
1. **After the close** (worker, 16:45 NY): the signal engine runs every non-retired strategy on stored daily bars for benchmarks and watchlist symbols in the universe. Signals are persisted with deterministic ids (`shadow` for RESEARCH strategies, `paper` for PAPER).
2. **Next session** (executor, every 5 min): `core/execution/pipeline.py` evaluates each signal with live inputs through the risk engine (`core/risk/engine.py`). Every decision is stored in `risk_decisions`. Approved paper signals become orders (state machine + `submit_idempotent`). Shadow signals are never ordered.
3. **Every minute** (executor, broker sync): reconcile with the broker, cancel orphaned protective stops, and place GTC protective stops for any filled quantity not yet covered.
4. **Exits** cancel and confirm the protective stop, then sell with a limit order off the bid.

The API and dashboard can read all of this but cannot create orders. Strategy promotion is admin-only and gated by validation reports (Phase 4).

## Idempotent submission
`atlas/core/execution/broker.py::submit_idempotent`:
1. Look up the client order id at the broker; if present, return it.
2. Submit.
3. On an uncertain outcome (timeout/5xx), query by client order id with backoff. Found → done.
   Confirmed absent → one retry with the **same** client order id. Still unknown → raise
   `SubmissionUncertain`; the order stays `SUBMITTED` and reconciliation resolves it.

## Repository layout
The spec's layout is followed with two justified adjustments:
* Python code lives in the `atlas` package under `backend/` (`backend/atlas/{apps,agents,core,integrations}`)
  so imports are namespaced (`atlas.core.risk`) instead of generic top-level names like `core`.
* The dashboard is `dashboard/` (spec: `apps/dashboard`) because it is a separate Node project
  with its own toolchain; Python CLI scripts are `atlas.scripts.*` so they run with `python -m`.

| Spec path             | Location |
|-----------------------|----------|
| apps/api, apps/worker | `backend/atlas/apps/{api,worker,executor}` |
| apps/dashboard        | `dashboard/` |
| agents/*              | `backend/atlas/agents/*` (Phase 5) |
| core/*                | `backend/atlas/core/*` |
| integrations/*        | `backend/atlas/integrations/{alpaca,llm,telegram}` |
| database/migrations   | `backend/migrations` |
| tests/*               | `backend/tests/{unit,integration,backtesting,failure_scenarios}` |
| infrastructure        | `infrastructure/` |
| scripts               | `backend/atlas/scripts` |
