# Recommended Starting Settings: Gold and NQ

> These are **research starting points**. They are not optimised or proven. Nothing here has been backtested yet. Measure them with the strategy before trusting them.

Most parameters scale with ATR, so the same values carry across instruments. What really differs between markets is the **entry windows**, the **tick and point value**, and the **execution costs**.

## Common to both (defaults)

| Setting | Value |
|---|---|
| Chart | **5 minute** |
| Higher / Setup / Confirmation TF | 240 / 60 / 15 |
| Reference range filter | 0.35 – 3.0 × ref-TF ATR |
| Reclaim window / breakout acceptance | 6 bars / 3 closes |
| 15M confirmation | MSS or Displacement, swings 3/2, displacement 0.8 ATR, expiry 48 bars |
| 5M trigger | Break or Retest, swings 3/2, retest tol 0.15 ATR, expiry 24 bars |
| Anti-chase | max stop 4.0 × ATR |
| Stop buffer | 0.10 × ATR (min ticks below) |
| Min R:R to TP2 | 2.0 |
| TP1 / TP2 | CRT 50% / opposite CRT or liquidity, 50% / 50% |
| Breakeven | **Off** |

## GOLD

| Setting | XAUUSD (spot / CFD) | GC (futures) | MGC (micro futures) |
|---|---|---|---|
| Tick | usually 0.01 (broker-dependent) | 0.10 = $10 | 0.10 = $1 |
| Point value | broker-dependent (often $1 per oz per $1) | **$100 / point** | **$10 / point** |
| Min stop buffer ticks | 20 (= $0.20) | 2 | 2 |
| Entry windows (preset) | London 08:00–11:00 Europe/London + NY 08:30–11:30 America/New_York | same | same |
| Strategy commission | set **0** per contract; model the spread with slippage | ≈ broker all-in per contract per side | ≈ broker all-in per contract per side |
| Strategy slippage | **20–30 ticks** (spread ≈ $0.20–0.30) | 1–2 ticks | 1–2 ticks |
| Quantity step | your lot step in oz | 1 | 1 |

Spot, GC and MGC have **different costs and sizing**, so test each one separately. Daily and weekly levels follow each symbol's own session, so CFD and futures PDH/PDL can differ.

## NASDAQ (NQ / MNQ)

| Setting | NQ | MNQ |
|---|---|---|
| Tick | 0.25 = $5 | 0.25 = $0.50 |
| Point value | **$20 / point** | **$2 / point** |
| Min stop buffer ticks | 4 (1 point) | 4 |
| Entry windows (preset) | NY 09:30–11:30 America/New_York (London off) | same |
| Strategy commission | ≈ broker all-in per contract per side | ≈ broker all-in per contract per side |
| Strategy slippage | 1–2 ticks (more around 09:30) | 1–2 ticks |

ES / MES use the NQ windows. EUR/USD uses London + NY. USD/JPY adds Tokyo 09:00–11:30. These are all research presets.

## Strategy properties to set per market (Settings → Properties)

* **Commission**: the default is 1.5 per contract per order. Change it to your broker's real all-in cost.
* **Slippage**: the default is 2 ticks.
* **Initial capital / margin**: the defaults are 100,000 and 5% margin, so a full NQ/GC contract is not rejected for margin.
* **Bar Magnifier**: turn it on if your plan supports it. It gives more realistic intrabar stop/target ordering.
* **Sizing**: fixed 2 contracts by default (so the 50% partial works), or risk % of equity.
