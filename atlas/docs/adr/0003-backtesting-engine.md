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

## Amendment (Phase 4, 2026-10-26)
* The simulator is `core/backtesting/simulator.py`. It calls the production
  `Strategy.generate` and `risk.engine.evaluate` directly: entries are sized, limited and
  rejected by the same code that trades. It also uses the production `liquidity_screen` on raw
  bars for a point-in-time universe, plus explicit spread, slippage, stop-slippage, regulatory
  fee, gap and participation (partial-fill) models from `policy.yaml`.
* **VectorBT was not adopted.** After optimisation (trusted pre-validated windows, O(n)
  rolling extremes, tail-only indicator windows, shared eligibility), a 10-year, 41-symbol run
  takes ~20-30 s. The parameter-stability screen therefore uses the same simulator, so screening
  and gating can't disagree, and there is no numba/LLVM dependency. Revisit if universes grow
  into the hundreds of symbols.
* Promotion gates live in `policy.yaml` (`promotion_gates`) with floors in code, and validation
  reports are immutable rows in `validation_reports`. `passing_validation_report()` accepts a
  report only for the exact version, parameters and policy hash, within `report_max_age_days`.
* Walk-forward here means consecutive out-of-sample windows of a fixed-parameter version. No
  parameters are fitted, because the baselines' parameters were fixed in advance. If future
  strategies fit parameters, the fit must happen inside each in-sample window.
