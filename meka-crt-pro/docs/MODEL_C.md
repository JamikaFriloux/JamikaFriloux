# Model C: 15M Double-Range Confirmation

Model C is an independent model inside MEKA CRT PRO. It has its own state machine, chart drawings (purple, prefixed "C"), dashboard rows, alerts and strategy switch. **Model A (CRT sweep/reclaim) is unchanged.** Both models use one shared, conservative fill-and-exit routine.

> **There is no "Model B" in the code.** The existing script contains a single model, the CRT sweep/reclaim with 15M/5M confirmation, which is now labelled **A**. Nothing was invented to fill the B slot. If you have a specific "B" in mind (for example CRT continuation), describe its rules and it can be added the same way.

## 1. Reference candles

Each pair is two **consecutive, completed** 15M candles. H1/L1/H2/L2 are recorded, then **upper = max(H1, H2)** and **lower = min(L1, L2)** are frozen. They never move for the life of that pair.

| Mode | Which pair |
|---|---|
| **Session-opening pair** (default) | The first two 15M candles of each enabled session open: NY 09:30 America/New_York and London 08:00 Europe/London (Asia 09:00 Tokyo is optional). A new open supersedes a pair still waiting (→ EXPIRED, reason shown). |
| First pair after 15M structure event | The two 15M candles that follow a confirmed 15M MSS/BOS. The event is known only after its own candle closed. |
| Rolling consecutive pair | Consecutive pairs that never reuse a candle from a previous pair **or the candle that ended it**. |

A pair is used once. It can produce at most one breakout evaluation and so at most one signal, and its candles are never recycled.

## 2. Confirmation and invalidation (evaluated once per completed 15M candle after the pair)

**SHORT confirmation** = a later 15M candle **closes** `< lower − buffer` (`cBufTk`, default 0 ticks), **and** all of the following hold:

1. The short side was not disqualified by an upper-boundary sweep during the observation window (`cSweepWin`, 0 = the whole setup life):
   * **Strict** (default): any 15M high above the upper boundary.
   * **Sweep**: a 15M high above the upper boundary, followed (same or a later candle) by a 15M close back at or below it.
   * **Off**: no disqualifier.
2. The filters pass. Each can be toggled:
   * **Session**: the breakout candle is inside an enabled session (or "Any time").
   * **Bias** [4H + 1H]: the last completed 4H/1H close vs that timeframe's EMA 50. If 4H and 1H disagree, the **conflict policy** applies (Block (default) / Follow 4H / Follow 1H), and the dashboard shows `CONFLICT`.
   * **15M structure** [off].
   * **Displacement body** [off].
   * **Volume** [off]. This is skipped automatically if the volume data is missing.
3. Stop distance ≤ `cMaxRiskATR` [3.0] × 15M ATR, and TP2 ≥ `cMinRR` [1.5]R. With liquidity targets on, the nearest untouched pool must itself be ≥ minRR away.
4. No Model C trade is already open.

**LONG** is the exact mirror. No rule differs between sides.

### How a pair ends

| State | Reason shown (examples) |
|---|---|
| CONFIRMED LONG / SHORT | "15M closed below the lower boundary 28600.25" → a trade is issued. |
| INVALIDATED | The side was disqualified ("a 15M high 28652.0 at 10-30 10:15 traded above the upper boundary 28650.25"); a filter failed ("4H and 1H bias disagree…"); or both sides were disqualified. |
| MISSED ENTRY | Stop distance too wide, TP2 below min R:R, nearest liquidity too close, or a C trade is already open. |
| EXPIRED | No 15M close beyond either boundary within `cExpiry` [8] candles, or superseded by a new session pair. |

A new 15M candle starting **never** ends a pair. Only the events above do.

### Entry, stop, targets, size

* **Signal time** = the 15M close. **Simulated execution** = the **next chart bar's open**, shown as a separate "C FILL" marker. The strategy fills at the same price.
* **Stop** [opposite boundary + 2 ticks]. Alternatives: the most recent *confirmed* 15M swing (falls back to the boundary if it is on the wrong side), or ATR × 1.5.
* **TP1 / TP2** = 1R / 2R (configurable). Optional TP2 = nearest untouched liquidity pool.
* **Size** = risk budget ÷ (stop distance × `syminfo.pointvalue`), rounded down. MNQ = $2/pt, NQ = $20/pt. The size is shown on the dashboard. It is **never** inferred from a P&L figure.

## 3. Non-repainting and multi-timeframe handling

* The 15M candle is read with **`lookahead_off`**, and only on the confirmed chart bar whose close equals the 15M close (`time_close == time_close("15")`). At that instant the 15M candle is complete, so its values are final on both historical and realtime bars.
* **5M chart:** this happens on the last 5M bar of each 15M candle, so the signal lands at the true 15M close and the fill is the next 5M open.
* **15M chart:** every bar qualifies and the fill is the next 15M open. This is why behaviour differs between a 5M and a 15M chart, and both are handled.
* **Fallback:** if that chart bar is missing (a thin market), the previous candle is taken from a `[1]` + `lookahead_on` request on the next bar and processed once, labelled *processed late*. A candle is never processed twice.
* **Bias filters** use the last **completed** 4H/1H candle (`[1]` + `lookahead_on`), and the 15M swings/structure come from completed candles only. The 15M candle is never rebuilt from lower-timeframe bars.
* Alerts fire with `alert.freq_once_per_bar_close` on that confirmed bar, so never before the 15M candle has closed.

## 4. What was measured (Python bar-for-bar replay, not TradingView)

`tools/replay/model_c.py` re-implements these rules and replays real 5M data:

* Costs per trade: gold $0.30 spread; NQ 1 tick per side + $4.50 per round trip.
* Results are in **R per trade, net of costs**, using defaults unless stated.
* **No parameters were tuned.**
* `tools/replay/model_c_repaint_test.py`: truncating the data never changes earlier trades (12 of 12 cuts identical).

| Sample | Variant | Trades | Win % | PF | Net R | Exp. R | Max DD R |
|---|---|---|---|---|---|---|---|
| XAUUSD Feb 2023 to Feb 2024 | **Raw** (no filters) | 218 | 36.2 | 0.99 | −0.6 | −0.003 | 12.6 |
| | Default (4H+1H, block) | 114 | 36.8 | 0.96 | −2.6 | −0.023 | 9.8 |
| XAUUSD Feb 2024 to Feb 2025 | **Raw** | 240 | 33.8 | 0.98 | −2.7 | −0.011 | 14.5 |
| | Default | 115 | 37.4 | 1.13 | +7.1 | +0.061 | 9.6 |
| NQ Jan to May 2008 | **Raw** | 93 | 33.3 | 0.84 | −8.1 | −0.087 | 14.6 |
| | Default | 43 | 27.9 | 0.61 | −10.7 | −0.250 | 11.4 |

Individual filters, compared against raw:

* **4H bias:** helped gold 2024, hurt NQ.
* **1H bias:** neutral to negative.
* **15M structure:** negative in all three samples.
* **Displacement ≥ 0.5 ATR:** mixed.
* **Volume:** about neutral. Gold volume is tick volume.
* **Sweep rule off:** the only variant that was not negative in all three samples (+16.0R, −0.2R, +1.2R). The effect is small and noisy.
* **"After structure" and "rolling" reference modes:** produce 2–3× more trades with worse or similar expectancy.

Long/short and session splits **flip sign between years** (for example, gold longs were negative in 2023 and positive in 2024), which points to market regime rather than a stable edge.

**Conclusion: on these samples Model C as specified shows no reliable edge after costs.** The one profitable cell (gold 2024 default) did not hold in 2023 or on NQ. The model is implemented faithfully so you can keep testing it. It is not presented as profitable.

The Oct 30, 2026 MNQ example could **not** be checked: no 2026 MNQ intraday data was available here. It was not used to set any parameter.

## 5. Testing checklist

- [ ] Compile the indicator and the strategy in TradingView (they have not been compiled here), and send any compiler error with its line number.
- [ ] 5M MNQ/NQ chart, Bar Replay through a NY open:
  - [ ] Purple H1/L1/H2/L2 segments appear right after the 09:45 candle closes (on the 09:55 5M bar close).
  - [ ] The dashed upper/lower boundaries never move.
- [ ] The "C · SELL" label appears on the 5M bar that closes at the 15M close, and "C FILL" appears on the next bar's open.
- [ ] Step one bar at a time: no C label appears before its 15M candle has closed.
- [ ] With a high above the upper boundary, a later breakdown shows **C ✕ INVALID** with that high's time and price.
- [ ] Switch the chart to 15M: the same signals occur at the same 15M closes, with fills on the next 15M open.
- [ ] Set the dashboard bias to 4H ↑ / 1H ↓ and confirm it shows `CONFLICT (Block trade)` and that breakouts are invalidated with that reason.
- [ ] Strategy: set *Model traded* = Model C.
  - [ ] Test the **raw** model first: bias Off, Any time, displacement/volume 0.
  - [ ] Then change **one** filter at a time.
  - [ ] Use *Trade from/until* to hold back an untouched period.
  - [ ] Read the results table (All / Long / Short / sessions) and the Strategy Tester summary.
- [ ] Run each instrument separately (MNQ, NQ, MGC/GC, XAUUSD) with its own commission and slippage in Properties.

## 6. Decisions that need you

1. **Model B**: should it exist, and what are its rules?
2. **Opposite-sweep definition**: "Strict" and "Sweep + close back" behaved identically in testing. The reason: a candle that trades beyond the opposite boundary either closes back inside (which disqualifies in both modes) or confirms the other direction immediately. Only "Off" differs. Do you want "Off" as an option you actively test, given it removes the rule you used on Oct 30?
3. **Default bias filter**: it is kept as you asked (conservative 4H+1H, block on conflict), but it did not improve results consistently. It stays the default until your own TradingView tests say otherwise.
4. **Stop**: the opposite boundary can be wide after a large range. A max of 3 × 15M ATR leads to MISSED ENTRY on wide pairs. Please confirm this value or set it yourself.
5. **One Model C trade at a time**, and A and C can be open at the same time in the indicator. The strategy trades one model per run.
