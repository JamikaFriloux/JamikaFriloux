# MEKA CRT PRO: Exact CRT Rules

These are the rules the code runs. Each one acts only on **closed bars**. The defaults are shown in brackets.

---

## 0. Data integrity (applies to everything)

| Rule | Implementation |
|---|---|
| Higher-TF data | `request.security(..., expr[1], lookahead = barmerge.lookahead_on)`. This returns only the last **completed** 4H / 1H / 15M / D / W candle, and the value is the same on historical and live bars. |
| Engine execution | The whole state machine runs inside `if barstate.isconfirmed`. Nothing fires intrabar, so no labels appear and then vanish. |
| Swing points | Pivots only exist once their right-side bars have closed. A level is created on the bar where it became known, never earlier. |
| Event placement | Sweep labels go on the bar where the sweep was **confirmed**, not the breach bar. BUY/SELL goes on the confirmation candle. The fill is drawn on the next bar. |

## 1. Reference candle (CRT range)

1. On the first chart bar after a 4H (or 1H) candle closes, that completed candle becomes the **candidate**.
2. The candidate is **valid** only if `minRangeATR × ATR14(refTF) ≤ high − low ≤ maxRangeATR × ATR14(refTF)` [0.35 … 3.0]. This rejects dead inside candles and news spikes.
3. If it is valid, it **replaces** the active range. CRT HIGH = high, CRT LOW = low, CRT 50% = (high + low) / 2.
4. If it fails, the previous valid range stays active for up to `rangeMaxAge` [2] more reference candles, then **expires**. The dashboard says "No valid range".
5. Levels only change when a new **valid** reference candle exists.
6. If a level was breached but not yet resolved when its range was replaced, it stays tracked ("retired") until it resolves. A sweep that straddles the hour boundary is not lost.

**Premium / discount:** price ≥ 50% is premium and price < 50% is discount.

## 2. Sweep / reclaim / breakout (per level, once only)

| State | Condition |
|---|---|
| **Untouched** | Not yet traded through. |
| **Breached (unconfirmed)** | A closed bar trades ≥ `sweepTicks` [1] tick beyond the level. The sweep extreme starts tracking. |
| **Swept (reclaimed)** | Within `reclaimBars` [6] bars (counting the breach bar), a bar **closes back inside** the level. A wick-and-close on the same bar is an immediate sweep. |
| **Broken (breakout)** | `acceptBars` [3] consecutive closes beyond the level, or the reclaim window runs out. That level can no longer produce a sweep setup. |

Each level produces **at most one** classification, so the same pool is never labelled twice. Nearby levels from different sources are merged. For example, a PDL within tolerance of the Asia low becomes `PDL + ASIA L`.

## 3. Which sweeps can start a setup

* **4H CRT high/low** and **1H CRT high/low**, according to "Setups may originate from" [both].
* **Liquidity pools** (PDH/PDL, PWH/PWL, Asia/London/NY highs and lows, 15M swings, EQH/EQL), but only when **CRT-aligned**. An SSL pool must sit in the discount half of the active CRT range (for a long). A BSL pool must sit in the premium half (for a short). These are marked ★. Targets still come from the CRT range.
* Sweep depth must be ≤ `maxSweepATR` [3.0] × chart ATR.
* If several levels are swept on one bar, priority is **4H CRT > 1H CRT > pool**.

**Direction** = away from the swept side. SSL / CRT LOW swept means LONG. BSL / CRT HIGH swept means SHORT.

A setup is **not created** when:
* it is against the 4H CRT bias [filter on]. The 4H bias is bullish if the 4H low was swept or the 4H high broke out, and bearish if the opposite. 4H-sourced setups bypass this filter.
* the reclaim candle has already reached the range 50%.
* a trade is already active, or a same-direction setup is already pending. An **opposite** sweep replaces a pending setup.

## 4. State machine

```
IDLE → CRT RANGE ACTIVE → LIQUIDITY BREACHED → RECLAIMED (SETUP FORMING)
     → 15M CONFIRMED → 5M ENTRY CONFIRMED (SIGNAL) → FILLED / TRADE ACTIVE
     → TP1 HIT → TP2 HIT | STOP HIT | BE STOP | EARLY EXIT  → COMPLETE
pending states → SETUP INVALIDATED (reason shown)
```

### 15M confirmation (state RECLAIMED → 15M CONFIRMED)
Only 15M candles that **closed after the breach began** count.

* **MSS / CHoCH**: a 15M close beyond the last confirmed 15M swing (pivot `pivL15`/`pivR15` [3/2]) in the setup direction. It is labelled **CHoCH** when it breaks against the prior 15M structure, otherwise **BOS**. "Require CHoCH" [off] accepts only CHoCH.
* **Displacement**: a 15M candle in the setup direction whose body is ≥ `dispMult` [0.8] × 15M ATR14 and which closes beyond the prior 15M candle's extreme.
* Mode [MSS or Displacement]: `MSS / CHoCH`, `MSS or Displacement`, or `MSS + Displacement`.
* The sweep alone never counts as confirmation.
* Expiry: no confirmation within `confExpiry` [48] chart bars invalidates the setup.

### 5M entry (state 15M CONFIRMED → SIGNAL)
On a completed chart candle, at or after 15M confirmation:
* **5M structure break**: a close beyond the most recent unbroken 5M swing (`pivL5`/`pivR5` [3/2]).
* **Retest of 15M break**: the candle wicks to within `retestTol` [0.15 ATR] of the 15M break level and closes back on the correct side in the setup direction.
* **Momentum candle**: a directional candle closing beyond the prior candle's extreme.
* Default: **Break or Retest**.

A trigger is **accepted** only if all of these hold:
1. Stop distance ≤ `maxRiskATR` [4.0] × chart ATR (anti-chase).
2. Long entries are in discount and short entries in premium [on].
3. The candle is inside an enabled **entry window**.
4. It is not against the 4H bias [on].
5. A TP2 exists with reward:risk ≥ `minRR` [2.0].

If a trigger is rejected, the reason appears on the dashboard and the setup keeps waiting until `entryExpiry` [24] bars.

### Pending invalidation (checked every bar)
* Price trades through the sweep extreme (a wick by default, or a close if you switch it).
* Price reaches the CRT 50% before an entry. The move happened without us, so there is no chasing.
* Expiry, or replacement by an opposite sweep.

## 5. Stops and targets

* **Stop**: sweep extreme ∓ max(`stopBufTk` ticks, `stopBufATR` × ATR) [2 ticks, 0.10 ATR].
* **TP1** [CRT 50%]: the CRT 50%, if it is ahead of the entry, ≥ `tp1MinR` [0.8R] away, and before TP2. Otherwise the nearest untouched internal liquidity before TP2. Otherwise `tp1R` [1.0R].
* **TP2** [Opposite CRT / liquidity]: the opposite CRT boundary if it gives ≥ minRR. Otherwise the nearest untouched external liquidity beyond entry with ≥ minRR, capped at one range height beyond the boundary. **Otherwise there is no trade.** It never falls back to "any R" in structure mode. In `R multiple` mode TP2 = `tp2R` × risk.
* Targets are always in the trade direction and beyond the entry. A level price has already passed is never used.

## 6. Fill and management (simulation)

* The signal is at the confirmation candle's **close**. The assumed fill is the **next candle's open**, shown as a separate "FILL" marker.
* R is measured against the risk planned at signal time.
* If the fill bar opens beyond the stop, the trade is stopped at that open. This is realistic: you would be filled and stopped immediately.
* **Same bar touches stop and target → stop is assumed first** (conservative).
* `tp1Pct` [50%] closes at TP1 and the rest at TP2.
* Breakeven after TP1 [off]: when enabled, the stop moves to the fill price from the **next** bar.
* Early exit after N bars [off]: exits at the bar's close.
