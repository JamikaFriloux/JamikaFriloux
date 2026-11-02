# MEKA CRT PRO Upgrade: Staged Plan

| Stage | Contents | Status |
|---|---|---|
| **1** | Fair Value Gaps + inverse FVGs, Supply & Demand / order blocks, structure refinements (MSS), independent overlay toggles, minimal dashboard format | **Done** (this commit) |
| **2** | AMD / Power of Three as a separate optional setup model (accumulation → manipulation → distribution) | **Done** |
| 3 (next) | Confluence engine (optional filter/ranking with "why it qualifies / why rejected"), FVG setup model, strategy support for the new models, cost-inclusive in/out-of-sample tests on MNQ, MGC/gold, ES | After 2 |

**There is no "Model B" in the code.** The script contains **Model A** (CRT sweep/reclaim) and **Model C** (15M double range = "RANGE BREAK"). Both are unchanged in Stage 1: only display lines were edited, and no entry/stop/target/state logic changed.

## Stage 1 features

### Fair Value Gaps (input group ⑮)

* **Bullish FVG:** the low of candle 3 > the high of candle 1. **Bearish:** the high of candle 3 < the low of candle 1. Minimum size 0.15 × ATR.
* A gap exists only from the **close of candle 3**. The box starts at the middle candle (where the gap is), but nothing is signalled earlier.
* **Strong (★):** the middle candle is a displacement candle in the gap's direction (body ≥ 1.0 × ATR). Strong gaps are drawn first, and *Show only strong* is optional.
* **States:**
  * Fresh.
  * Partially filled (◐).
  * Fully mitigated (wick to the far edge) → removed.
  * **Close through the far edge** → becomes an **inverse FVG** (IFVG, grey dashed) with the opposite role. An IFVG closed through again → invalidated and removed.
* Only the **nearest 2 per side** within 8 × ATR are drawn, and redrawn on the last bar. There is no history clutter.

### Supply & Demand / order blocks (input group ⑯)

* **Displacement candle:** body ≥ 1.2 × ATR and a close beyond the previous candle's extreme.
* **Zone** = the **last opposite-colour candle** in the 3 candles before it (the order block), from its high to its low. If there is none, the candle just before.
* It is created only when the displacement candle **closes**. Overlapping same-side zones merge, so there are no stacks of boxes.
* **Rank 0–5:** an objective count, **not a probability**:
  * Freshness: 2 if untouched, 1 after one retest, 0 after more.
  * +1 if the displacement broke the last confirmed swing (**BOS**).
  * +1 or +2 for displacement size (2 if the body is ≥ 2.4 ATR).
* **Invalidated** on a close through the zone (shown faded for a while, at most 2). **Retired** after 3 retests. Only the nearest 2 per side are drawn.

### Structure & liquidity (input group ⑰)

* 15M structure markers now distinguish **BOS**, **CHoCH** and **MSS**, where MSS = a CHoCH whose breaking candle is a displacement candle.
* They can be shown **always**, **Detailed only** or **off**. They come from confirmed pivots and appear only after the breaking 15M candle closes.
* **Liquidity lines** (PDH/PDL, PWH/PWL, Asia/London/NY highs and lows, 15M swings, EQH/EQL) can now also be shown in Clean mode.
* Premium/discount shading already existed (Display ①).

### Dashboard (Compact)

`BIAS` (BULLISH / BEARISH / NEUTRAL. NEUTRAL when 4H and 1H disagree; hover for details) · `SETUP` (CRT / RANGE BREAK + direction) · `SIGNAL` (BUY / SELL only for an actionable trade, otherwise WAIT) · `ENTRY` · `SL` · `TP1` · `TP2` · `SESSION`.

The debug view is still available as *Dashboard style → Full* plus the *Diagnostic log*.

## Measured (Python replay of the Stage 1 rules: rule behaviour, not performance)

| Per trading day | XAUUSD Feb 2024 to Feb 2025 | NQ Jan to May 2008 |
|---|---|---|
| 5M FVGs created (strong) | 34.5 (14.4) | 56.8 (16.9) |
| FVGs closed through → inverse | 15.3 | 23.4 |
| S/D zones created (with BOS) | 10.5 (3.8) | 13.2 (4.1) |
| Zones invalidated / retired | 7.8 / 1.5 | 10.2 / 1.9 |
| Candidates within range on a bar (median) | FVG 6, zones 3 | FVG 7, zones 3 |

* No-future test (`tools/replay/context_zones.py`): engine state identical on every bar for 6 of 6 truncation cuts.
* **Implication for Stage 3:** raw 5M FVGs are very frequent and almost half get closed through. As a confluence input they should be limited (strong-only and/or 15M gaps). The data supports that; I am not assuming it.

## Default settings

All FVG / zone sizes are **ATR multiples**, so the same defaults apply to MNQ and gold. What really differs between them is risk:

| Setting | MNQ | MGC / gold |
|---|---|---|
| Chart | 5M | 5M |
| Entry windows (preset) | NY 09:30–11:30 | London 08:00–11:00 + NY 08:30–11:30 |
| Max stop in points (`⑥ maxStopPts`) | your decision; e.g. 40–60 pts ($80–120 per MNQ contract) | your decision; e.g. 6–10 pts ($60–100 per MGC contract) |
| Model C max stop | 2 × 15M ATR (default) | same |
| FVG / S&D overlays | on, nearest 2 per side | same |
| Strategy commission / slippage | ≈ broker all-in per contract, 1 tick | ≈ broker all-in per contract, 1–2 ticks |

## Testing (Stage 1)

1. Compile the indicator and strategy in TradingView. Neither has been compiled here, so send any error with its line number.
2. Bar Replay on a 5M chart, stepping one bar at a time:
   * An FVG box appears only **after** the third candle closes.
   * It turns ◐ when price enters it.
   * It disappears on a full fill.
   * It turns into a grey dashed IFVG when a candle closes through it.
3. Demand/supply boxes appear on the close of the displacement candle, merge instead of stacking, fade when closed through, and show a rank of x/5.
4. Toggle each overlay (FVG, IFVG, S&D, faded zones, structure markers, liquidity lines) independently.
5. Confirm Model A / Model C signals are unchanged on the same chart range as before the upgrade.

## Stage 2: Model AMD / Power of Three (input group ⑱)

A separate, **optional** model with its own state machine, trade, alerts, dashboard entry (`SETUP: AMD`) and strategy option (*Model AMD — Power of Three*). It is not required by any other model.

| Phase | Exact rule (defaults) |
|---|---|
| **Accumulation** | Over the last 24 chart bars, high − low ≤ 3.0 × ATR(100) **and** ATR(14) ≤ 0.8 × ATR(100) (compression). The range is frozen at that bar. It never overlaps the previous AMD range. It expires if there is no manipulation within 48 bars. Drawn as a thin outline. |
| **Manipulation** | Price trades ≥ 1 tick beyond one side, then a **completed 15M candle closes back inside** within 2 × 15M candles. The **M** marker appears only on that confirming bar. Two 15M closes outside = **accepted breakout** (invalid). A sweep deeper than 2 × ATR = **expansion** (invalid). Both sides broken on one candle = invalid. |
| **Distribution** | Within 24 bars: a displacement candle (body ≥ 1.0 × ATR) in the direction **away from the sweep** closes beyond the **opposite** range boundary (or the midpoint, optional). Optional: require a chart-TF swing break after the manipulation. **D** marker. Breaking the manipulation extreme first = invalid. |
| **Trade** | Signal at the distribution close; fill at the next bar open. Stop beyond the manipulation extreme + 2 ticks (or midpoint / displacement candle). Max stop = range height + max sweep (range-based) and the global points cap; wider = NOT TRADABLE. TP1/TP2 = 1R/2R, min R:R 1.5. Entry windows apply. Optional bias filter (same settings as Model C). |

Every ending is logged with a plain-English reason (Diagnostic log): *accepted breakout*, *expansion*, *manipulation extreme broken*, *no distribution*, *not tradable: …*.

### What the replay showed (`tools/replay/amd.py`, costs included, nothing tuned for profit)

Per year on XAUUSD, with the final defaults:
* About 590 accumulations, about 370 confirmed manipulations, about 270 of which **broke the manipulation extreme again** before distribution.
* About 35 distributions in total, and only **0–5 inside the entry windows**.
* With a 5M-close reclaim (the first draft), the extreme was broken again 81% of the time. That is why the 15M close is the default.
* The first draft's ATR stop cap made almost every manipulation-extreme stop "too wide". The range-based cap fixes that contradiction.

| Variant (15M reclaim, range cap) | Gold 2023 | Gold 2024 | NQ 2008 |
|---|---|---|---|
| Default (entry windows) | 3 trades, −0.73R | 1 trade, −0.03R | 0 trades |
| Any time of day | 36 trades, −0.29R | 35 trades, −0.29R | 13 trades, −0.54R |
| Any time + 4H/1H bias | 14 trades, +0.17R | 16 trades, +0.17R | 3 trades, −1.12R |

**Conclusion: AMD as specified is rare and showed no reliable edge.** The bias-filtered cells are positive in both gold years but rest on about 15 trades a year and fail on NQ. That is not evidence. The model is implemented faithfully for your own testing in TradingView.

The no-future test passes: 12 of 12 truncation cuts are identical.

### Stage 2 testing checklist
- [ ] Compile indicator + strategy, and send any error with its line number.
- [ ] Bar Replay:
  - [ ] An orange ACCUMULATION outline appears only once the compression rule holds, and it never moves.
  - [ ] The **M** marker appears on the 5M bar that closes a 15M candle back inside.
  - [ ] **D** and **AMD · BUY/SELL** appear on the displacement close, and the fill is on the next bar.
- [ ] Diagnostic log: every AMD ending has a reason.
- [ ] Strategy: *Model traded* = AMD. Test with entry windows on and off, then add the bias filter.
