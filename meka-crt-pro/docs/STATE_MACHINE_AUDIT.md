# State-Machine Audit: Why Setups Kept Ending as INVALIDATED

## How this was tested

TradingView cannot be run outside TradingView. So I ported the engine bar-for-bar to Python (`tools/replay/meka_replay.py`). The port uses the same rules, the same defaults and the same order of operations, with higher-timeframe data reproduced exactly as `request.security(expr[1], lookahead_on)` returns it. I replayed it on real **XAUUSD 5-minute data**:

* Source: public dataset `juan2000lopezg-afk/datacsvgold`, broker server time = NY + 7h.
* Period A: Feb 2024 to Feb 2025.
* Period B: Feb 2023 to Feb 2024. This year was **untouched**: nothing was tuned on it.

What this does and does not show:

* It **does** test the logic.
* It is **not** a TradingView compile or a TradingView backtest. The HTF candles are rebuilt from the 5M feed, so bucket edges and ATR seeds can differ slightly from your broker feed.
* Trade counts are far too small for any performance conclusion, and none is made.

## Every condition that could end a v1 setup

| # | v1 condition (code step 8/9) | Category | Was it the problem? |
|---|---|---|---|
| 1 | Low traded below the **raw sweep extreme** (wick) | structural | **Yes. 68% of all endings.** |
| 2 | Price reached the CRT 50% before entry | missed | **Yes. 30% of endings**, 93% of them before 15M could confirm. |
| 3 | No 15M confirmation within 48 bars | expired | Rare (<1%). |
| 4 | No valid 5M entry within 24 bars | expired | Rare (<1%). |
| 5 | Opposite qualifying sweep while pending | replaced | Rare (1.4%). |
| 6 | New 4H/1H reference candle | (none) | **No.** 841 setups lived across a roll and none ended because of it: the levels were copied into the setup. |

**v1 measured (Period A):** 3,558 setups reached "SETUP FORMING". **Only 6 became signals.**

## Root causes

1. **The reclaim was confirmed on noise.** A 1-tick wick past *every* previous hour's high/low, plus **one 5M close back inside**, counted as "sweep confirmed". That is about 14 setups a day. Median time from that "reclaim" to price trading through the sweep extreme was **2 bars**, and only 0.8% of those setups ever got a 15M confirmation first. These were not valid CRT sweeps that the machine wrongly killed. They should never have become setups.
2. **Internal boundaries were treated as liquidity.** When the previous 1H candle had already traded beyond this candle's low, that low is not a resting liquidity pool, yet it still started setups.
3. **Strict 15M → 5M sequencing caused misses.** When a reclaim really works on a 1H range, price usually reaches the 50% within about 3 bars, before a 15M candle can even close a structure break. A forward check (enter at the reclaim close, planned stop, target the 50%) shows **every** v1 "MISSED" setup would have reached the 50% before its stop. That same check also shows that entering with *no* confirmation has about zero expectancy overall. So the answer is to fix the *ordering*, not to drop confirmation.
4. **Invalidation was stricter than the risk plan.** v1 killed setups on a wick 1 tick past the raw extreme, while the stop that would have been placed sits *below* it (extreme ∓ buffer).
5. **The dashboard showed the *new* range after a roll.** It looked as if the reference candle had changed under a live setup, even though the setup's own levels had not.

## Corrections (risk protections unchanged)

| Fix | What changed |
|---|---|
| **Two-stage sweep** | `SWEEP IN PROGRESS` = breached. `SWEEP CONFIRMED & RECLAIMED` only when a **completed 15M candle** (selectable: reference-TF close for classic CRT, or chart close for the v1 behaviour) closes back inside within 2 candles. A 5M close back inside shows as "reclaim pending". |
| **External boundary** | A CRT high/low starts setups only if it is beyond the previous 2 reference candles (`extLook`). This is a methodology rule; it was not optimised. |
| **Locked setup** | Direction, level, sweep extreme, planned stop, range H/L/50%, reference-candle time and breach time are frozen at the reclaim. A new 4H/1H candle never changes or ends the setup. The locked stop and 50% are drawn, and the dashboard notes when the live range has rolled. |
| **Timestamp-paired confirmation** | A 5M structure break that happened *after the breach* and ≤ 12 bars before the 15M confirmation completes the 5M side. The entry is taken only at the close of the bar where **both** are known, at that bar's price, with every filter re-checked. Nothing is back-dated. |
| **Stop-consistent invalidation** | Structural invalidation = price reaches the **planned stop**, which is the same level the trade would use. |
| **No-room skip** | If even a retest of the swept level has no target ≥ min R:R, the sweep is logged as SKIPPED instead of showing "setup forming". |
| **Separated endings** | `STRUCTURAL` (planned stop hit) · `CONFLICT` (opposite 15M MSS after the reclaim) · `MISSED` (50% reached before entry, says whether before or after 15M) · `EXPIRED` (no 15M / no 5M in time) · `SESSION` (only out-of-window triggers) · `REPLACED` · `SKIPPED` (sweep confirmed but not tradable, with the reason). |
| **Dashboard + diagnostics** | Plain-English reason in "Status / Next / Last setup". The optional **Diagnostic log** table (bottom of the chart, tiny text) shows the last 20 outcomes. |

Unchanged: anti-chase distance, discount/premium, entry windows, 4H bias, min R:R 2.0, stop-first intrabar rule, next-open fill.

## Measured after the fix (same data, same defaults)

| | v1 Period A | **v2 Period A** | v1 Period B (untouched) | **v2 Period B** |
|---|---|---|---|---|
| Setups reaching "reclaimed" | 3,558 | **1,659** | 3,682 | **1,623** |
| Structural | 2,418 | 964 | 2,488 | 941 |
| Missed | 1,068 | 597 | 1,110 | 560 |
| Conflict / Expired / Session / Replaced | 66 | 80 | 75 | 100 |
| **Signals** | **6** | **18** (11 used paired confirmation) | **9** | **22** (7 paired) |
| Ended by an HTF candle roll | 0 | 0 | 0 | 0 |

**No-future-information test** (`tools/replay/repaint_test.py`): the engine was cut off at 3 points per year. Every signal and outcome before each cut was **identical** to the full-history run (6 of 6 cuts, v1 and v2).

## What this does *not* fix (honest)

* Most CRT sweep attempts on 1H gold still fail (structural) or run to the 50% without a confirmed entry (missed). That is the market, not a bug. The system now says which one happened instead of showing "SETUP FORMING" for noise.
* Signals remain selective (about 20 a year on gold with default filters). Making it more active means deliberately changing risk filters (entry windows, 4H bias, min R:R). That is your decision, and it was not done here.
* Not yet verified inside TradingView. Compile it, then check the diagnostic log on Bar Replay (see `TESTING.md` §B).
