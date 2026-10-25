# ADR 0003 — Backtesting engine

Status: Accepted (decision for Phase 4)

## Options considered (checked 2026-10-25)
* **Backtrader** — last PyPI release 1.9.78.123 in April 2023; effectively unmaintained.
  Rejected.
* **VectorBT (open-source)** — release 1.2.0 on 2026-10-19, supports Python 3.11–3.14.
  Very fast vectorized simulation, good for parameter sweeps; its fill model is simpler than
  our live execution model.

## Decision
* **Validation backtests** use a small in-house event-driven simulator in
  `atlas/core/backtesting` that reuses the *same* strategy, position-sizing and risk-engine
  code as paper trading, with explicit cost, spread, slippage, gap and partial-fill models.
  This keeps research and production behavior identical (no "two implementations" drift).
* **VectorBT** is used only for fast screening: parameter-stability grids, sensitivity
  analysis, and bootstrap resampling. Any strategy promoted out of RESEARCH must pass the
  event-driven simulator, walk-forward and out-of-sample gates.

## Consequences
More code to own, but promotion decisions rest on the same code path that trades.
