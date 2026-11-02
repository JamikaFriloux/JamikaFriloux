# MEKA CRT PRO Upgrade: Staged Plan

| Stage | Contents | Status |
|---|---|---|
| **1** | Fair Value Gaps + inverse FVGs, Supply & Demand / order blocks, structure refinements (MSS), independent overlay toggles, minimal dashboard format | **Done** (this commit) |
| 2 | AMD / Power of Three as a separate optional setup model (accumulation → manipulation → distribution) | Next |
| 3 | Confluence engine (optional filter/ranking with "why it qualifies / why rejected"), FVG setup model, strategy support for the new models, cost-inclusive in/out-of-sample tests on MNQ, MGC/gold, ES | After 2 |

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
