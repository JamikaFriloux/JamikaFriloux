# MEKA ALPHA PRO v3 — full-source static audit (re-verified for 4.0-r2)

Source: `MEKA_ALPHA_PRO_v3_SOURCE.pine` — Pine v6 `indicator(...)`, 1,595 lines, SHA-256 `d4bad2fe5a60949e0e2a2bdbcf9518b7ec96d325facdeba6e0d382a58dc988ed` (re-computed and matching on October 29, 2026). The file is complete: it ends inside the debug-table block with the closing `dbgTbl := na`, matching the module inventory below.

This document is the original r1 audit (preserved unchanged in `reference/r1/MEKA_ALPHA_PRO_v3_AUDIT_r1.md`) plus a second, independent read of all 1,595 lines. **Everything here is static inspection.** No TradingView compilation, replay or backtest of v3 was performed.

## Re-verification summary (r2 reviewer)

Every finding's quoted lines were re-opened in the source and checked against the claim.

| ID | Lines re-checked | Status | Note |
|---|---|---|---|
| A01 | 873–877, 911–915, 952–1062, 1096–1153 | **Confirmed** | Including the non-finding: Signal Close entry is created after management (section 3), so it is not checked against its own signal candle. |
| A02 | 801–802, 874, 912, 954–960 | **Confirmed** | `f_pendingFilled` tests range only; fill is always `pendingPrice`. |
| A03 | 731–734, 969, 1035, 1495 | **Confirmed** | BE stop = entry ± 0.05 ATR, so risk-per-unit shrinks and displayed quantity balloons rather than becoming `na`. |
| A04 | 826–829, 962–1062, line 2 | **Confirmed** | |
| A05 | 37–46, 137–146, 872–946 | **Confirmed** | |
| A06 | 328–330, 378, 420, 425, 462, 467 | **Confirmed** | |
| A07 | 1088–1090, 1428 | **Confirmed** | `>= cooldownBars` with 0 permits same-bar re-entry; pending cancellation never sets `lastTradeCloseBar`. |
| A08 | 652–666 | **Confirmed** | |
| A09 | 49–113, 679–713 | **Confirmed** | |
| A10 | 266–268, 564, 581 | **Confirmed** | |
| A11 | 533, 563–565, 581, 600–610 | **Confirmed** | Non-finding also confirmed: no probability or win-rate claim anywhere in v3. |
| A12 | 962–1062, 1299–1300, 1427–1447 | **Confirmed** | |
| A13 | 731–734, 1498 | **Confirmed** | |
| A14 | 507–516 | **Confirmed** | |
| A15 | 328, 1509 | **Confirmed** | |
| A16 | 1237–1244, 1255–1277 | **Confirmed** | |
| A17 | 1377–1396 | **Partly corrected — see below** | Only the bullish box is reversed. |
| A18 | 624–646, 1169–1189, 1456 | **Confirmed** | |

### Correction to A17

The original says the bear case is "similarly" reversed. It is not:

- Bullish: `bullFVG = low > high[2]` (1377), box `top = high[2]`, `bottom = low` (1392). Because `low > high[2]`, **top < bottom — reversed.** Mitigation test `close <= ftop and close >= fbot` (1387) then requires `close <= high[2]` and `close >= low` at once, which is impossible while `low > high[2]`. **Bullish gaps are never removed as mitigated**; they leave only through the `fvgMaxCount` cap (1397–1399). The original says the test is "inconsistent"; the precise effect is that it can never fire.
- Bearish: `bearFVG = high < low[2]` (1378), box `top = low[2]`, `bottom = high` (1395). Since `low[2] > high`, **top > bottom — correctly ordered**, and the close-inside mitigation can fire.

Repair and test from A17 still apply (normalize top/bottom; choose touch vs full-fill semantics).

### Additional observations not in the original audit (all P3)

- **A19 — event labels ignore `showHistoricalTrades`.** Lines 1291–1310 create a label for every fill/TP/stop/exit/cancel regardless of the toggle that governs the lines. They are bounded only by `max_labels_count=200` (line 2), where TradingView drops the oldest. This is a display/resource issue, not a decision defect.
- **A20 — HTF early exit silently disabled above 1H.** `htfInvalidationLong/Short` (742, 758) use `trend60`, which is `"N/A"` when the chart is above 60 minutes (228–235), so that exit reason can never fire on those charts. Nothing reports this.
- **A21 — VWAP on symbols without volume.** `ta.vwap(hlc3)` (180) has no missing-volume policy. Where VWAP is `na`, both `aboveVWAP` and `belowVWAP` are false, so the location score (583–586) gives 3/10 to both sides. It is a neutral-looking value created by missing data (same family as A10).

### Disposition in 4.0-r2

| Finding | How 4.0-r2 handles it |
|---|---|
| A01, A02 | Strategy uses the TradingView emulator with market entry plus pre-submitted fixed brackets. Indicator models fill at the next bar's open, judges that bar from its open, stop-first, gap-aware. |
| A03, A04 | Initial quantity is frozen. Remaining quantity is tracked separately (strategy: `strategy.position_size`). Whole-unit tranches sum to the initial quantity. |
| A05 | Three independent windows, each with its own IANA timezone, a weekday mask, whole-bar containment and a latest-entry cutoff. Holding outside the windows is configured separately (exit-outside-windows, force-flat window). |
| A06, A07 | ICC stages need three different closed bars. Consumed pivot IDs prevent reuse. Cooldown counts full bars, so there is never a same-bar re-entry. Trade and setup IDs are frozen into every payload. |
| A08, A09 | Too-far structure is rejected, not clipped. Inputs have bounds, ordering is validated at bar 0, and targets are tick-separated after rounding. |
| A10, A21 | Volume filter is optional. When it is required, missing volume blocks entries and the dashboard says so. VWAP is not used. |
| A11 | No score is computed. No probability, confidence or win-rate wording. |
| A12 | All events on a bar are concatenated into one detail string and kept in a 4-entry history. Payloads carry `event_id`, `fill_basis` and `trade_id`. |
| A13 | Sizing is in USD per 1.0 price move per unit (USD quote: pointvalue; USD base: pointvalue / close; otherwise a manual override is required). Futures use whole contracts. |
| A14 | The room check uses the frozen planned risk × TP1 R against the latest opposing pivot (still the latest only; documented). |
| A15 | Mode-specific presets, ICC state machine, manual news windows, date gates and a companion strategy. |
| A16, A17, A19 | Drawings are replaced by `plot.style_linebr` plots; FVG boxes are not ported. |
| A18 | One reason string follows the actual hard-gate order. The Data Window shows raw candidate, eligible signal and setup state. |
| A20 | HTF trend is a single, strictly-higher timeframe validated at bar 0. |

---

## Main conclusion

There is a useful confirmed-bar confluence indicator here, but not a backtesting or partial-execution system. Its most consequential problem is the pending-fill model: the fill candle's completed information determines stops and targets, and that same candle's entire range then evaluates them. Five target-hit flags do not establish five realized profits. Rebuild execution around a clearly declared order model before evaluating an edge.

## Findings and repair tests

### A01 — P1: pending fills use completed-bar information and unknown intrabar order

**Evidence:** lines 873–877: `entryPrice := pendingPrice`, `atrAtEntry := atrVal`, `slPrice := f_stopLong(entryPrice)`; short mirror 911–915. Lines 952–954 then run `if orderState == "ACTIVE LONG"` and `if low <= slPrice` in the same execution. Targets follow at 962 onward. MFE uses the full high/low at 953/1019.

A buy-stop at 101 with a target of 103 could be assigned a target reached before the later entry crossing if the path is unknown; a buy-limit can similarly be given a pre-fill high as favorable excursion. A fill-candle pivot confirmation and ATR are also used as if available at the intrabar fill. Stop-first ordering is conservative only relative to an already-existing position and fixed bracket; it does not establish chronology or fix future-dependent bracket construction.

**Repair:** freeze order parameters before execution; use the strategy emulator for fills. If retaining custom resting-order simulation, flag entry-bar path ambiguity rather than asserting an actual sequence. **Test:** reverse two plausible price paths with identical OHLC and show that neither receives unjustified certainty.

**Important non-finding:** default Signal Close entry is created in section 3 (1096–1118 / 1131–1153), after section 2 management. It does NOT immediately check the original signal candle for a TP/stop. Do not incorrectly report that bug for the default mode. Its assumed close fill is still not an attainable execution guarantee.

### A02 — P1: gap fills always assigned the requested price

**Evidence:** 801–802 checks only range crossing, followed by `entryPrice := pendingPrice` at 874/912. A long breakout at 100 with next open 105 is still assigned 100. Stops have a hit flag but no gap-aware exit price or ledger (954–960).

**Repair:** next-tick emulator fills, realistic stop gaps, documented limit assumptions and costs. **Test:** long/short favorable and adverse gaps, including a gap beyond the entire bracket.

### A03 — P1: displayed quantity changes after stop management

**Evidence:** 731–734 computes `math.floor(dollarRisk / riskPerUnit)`; 1495 calls it with the current `dispStop`. BE changes that stop at 969/1035. An entry 100 / initial stop 98 with $100 risk displays 50 units at point value 1; stop 99 would display 100 even though no scale-in occurred. At exact BE it becomes unavailable; a small profitable stop can suggest an enormous new size.

**Repair:** freeze initial quantity, track remaining units separately, show initial risk and current stop independently. **Test:** stop changes never increase position quantity.

### A04 — P1: no actual scale-out quantities or execution accounting

**Evidence:** 826–829 stores TP booleans; 962–995 and 1028–1062 toggle flags, with final close only at TP5. No tranche allocation, remaining quantity, executed-price ledger, commission, spread, or slippage model exists. Declaration at line 2 is `indicator(...)`, not `strategy(...)`.

**Repair:** two default exit tranches, optional third, integer futures allocation, protective stop for each remaining tranche, companion strategy. **Test:** sum of filled plus remaining quantity equals initial quantity after every event. Never report target hits as complete-position wins.

### A05 — P2: session names do not provide three independent entry sessions

**Evidence:** 137–143 interpret every window in `sessionTZ`, default New York (44); 145–146 use `allowOvernight or ...`. Asia/London are labels, while default entries remain restricted to the US window. Enabling overnight bypasses all entry-window restrictions, including off-hours. A New York IANA timezone handles New York DST, but not London/Tokyo local session hours independently.

Pending management 872–946 does not cancel on entry-window closure. Holding outside RTH is not actually forbidden by `allowOvernight=false`; an exit depends on encountering the separate flatten window. A chart interval or missing bar can miss it.

**Repair:** independent local windows, explicit overnight policy, boundary behavior and pending-order rules. **Test:** March/October/November DST mismatches, overnight bars, missing flatten bars, and overlap deduplication.

### A06 — P2: “fresh” conditions can reuse the same setup

**Evidence:** `hlFresh` remains true for several bars (328–330), and `higherLowContinuationLong = hlFresh ...` (425), mirrored at 467. `recentTouch` (378) permits repeated reclaim conditions (420/462). No consumed setup ID exists. A closed trade can re-enter the same fresh setup after cooldown. This contradicts “each is a fresh, one-bar-triggered event” at 418.

**Repair:** indication/correction/continuation stages with consumed IDs; trend-pullback crossover event. **Test:** persistent conditions and a quick stopout must not recreate an already-consumed setup.

### A07 — P2: cooldown zero allows close and re-entry to overwrite event context

**Evidence:** active management changes state to WAIT; section 3 recomputes flatState (1088), and `>= cooldownBars` (1090) allows same-bar re-entry with zero. Pending cancellation can also re-arm immediately. Event messages later reference mutable `lockedSetup`, prices, and grade (1428).

**Repair:** snapshot events with trade IDs and require a later bar for a new entry. **Test:** stop and opposite signal together with cooldown=0; old-exit and new-entry payloads must never mix.

### A08 — P2: smart stop clipping may move protection inside invalidation

**Evidence:** long `stop := math.max(stop, maxStop)` (657), short mirror 665. If structural invalidation is 5 ATR away and max is 3 ATR, the script moves the stop to 3 ATR rather than rejecting the setup. “Structure-aware” therefore does not ensure a structural stop.

**Repair:** reject too-distant invalidation, or clearly distinguish an explicit ATR alternative. Validate after tick rounding. **Test:** far/incorrect-side pivot and minimum/maximum distances.

### A09 — P2: unconstrained risk inputs and tick rounding can collapse levels

**Evidence:** ATR multipliers, stop distances, TP multiples, EMA/RSI lengths and account risk lack sufficient bounds (49–113). Targets are ordered before rounding (679–713), so small R can round multiple targets to the same tick. ATR-only has no final distance validation.

**Repair:** positive inputs, min<=max validation, tick-separated monotonic targets and directional stop validation. **Test:** tiny ATR, zero/negative settings, coarse ticks, and TP2<=TP1 settings.

### A10 — P2: missing volume receives a positive substitute

**Evidence:** `relVolume = volAvg > 0 ? volume / volAvg : 1.0` (267), `volumeGood = relVolume >= 1.0` (268). Missing/zero mean can become “good” relative volume; score grants approximately 6.67 volume points (581) plus setup-quality credit (564). VWAP-dependent decisions also lack an explicit missing-data policy.

**Repair:** visible volume policy per feed; block if a required filter lacks data or explicitly disable the filter. **Test:** all-na and zero volume series.

### A11 — P2: score is heuristic and counts related evidence more than once

**Evidence:** setup-quality awards `volGood` (563–565), plus separate volume score (581). Trend, location, and structure are also correlated. “Each input counted exactly once” (533) is inaccurate. Grades at 600–610 are thresholds, not statistical calibration.

**Repair:** retain “setup score,” document components and correlation; remove uniqueness assertion. **Non-finding:** no 87–97% win-rate claim or score-to-probability conversion appears in this source. **Test:** no UI or documentation labels score as probability.

### A12 — P2: multiple target events collapse into the last text

**Evidence:** 964–987 repeatedly overwrite `evTpText`, mirrored 1030–1053. A bar passing TP1 through TP4 emits only “TP4 HIT” via 1299–1300 / 1431–1432. Multiple alert branches and close/re-entry can coexist; there are no stable trade/event IDs. “ENTRY FILLED” (1442) is a simulation, not a broker acknowledgment.

**Repair:** immutable ordered event records or combined event payload containing all events, separate intent/fill labels, strategy order-fill alerts. **Test:** multiple TP fills and final exit on one candle; audit every quantity and alert event.

### A13 — P2: sizing is incomplete for FX and broker-specific units

**Evidence:** 732 multiplies distance by `syminfo.pointvalue`, assumes dollar risk (733), floors all quantities and labels them contracts (1498). No account/quote currency conversion, lot increment override, or 6J/USDJPY orientation information exists.

**Repair:** verified USD-per-point-per-order-unit or currency conversion, explicit quantity step, manual override and block unknown sizing. Native 6J LONG must remain native LONG; only cross-market normalized bias is inverted. **Test:** USDJPY yen P&L versus USD account; 6J native direction; MGC versus GC sizing.

### A14 — P2: room check uses approximate rather than executable risk

**Evidence:** `approxR` (514) can differ from final smart stop; room exemption is blanket for breakout/momentum (431/473/515–516). Only the last pivot is checked (507–508), not a maintained nearest-level set. `minRoomR` labeled “R of TP1” does not scale by TP1 multiple.

**Repair:** use frozen proposed stop risk, precise label, and explicitly selected opposing structure. **Test:** last pivot behind price but older resistance ahead, and final risk much larger than approximate risk.

### A15 — P2: modes and requested safeguards are largely absent

**Evidence:** mode changes freshness only (328), besides dashboard title (1509). No five-market profile calibration, explicit ICC three-stage machine, news blackout, out-of-sample window, fees/slippage, or strategy ledger exists anywhere in the source. These are feature gaps, not evidence that existing calculations are inherently incorrect.

**Repair:** implement documented research baseline and validate per market/mode; avoid invented optimized defaults.

### A16 — P3: stale stop-line segments accumulate

**Evidence:** each stop change allocates another `slLine` (1239–1242), losing the old handle; closing deletes only the current line (1259–1261). This can leave segments even with historical drawings disabled and eventually rely on garbage collection.

**Repair:** track/delete segments or use a plot with gaps. **Test:** a long trailing trade followed by exit leaves no unwanted drawings.

### A17 — P3: FVG top/bottom are reversed and mitigation is narrow (bullish only — see correction above)

**Evidence:** bullish condition `low > high[2]` (1377), but box top=`high[2]`, bottom=`low` (1392); bear case similarly top=`low[2]`, bottom=`high` (1395). The subsequent `close <= ftop and close >= fbot` (1387) is inconsistent with these passed coordinates; wick crossings and closes beyond the gap also are not considered mitigation.

**Repair:** normalize top=max/bottom=min and explicitly choose touch or complete-fill semantics. **Test:** bullish/bearish wick touch, full gap traversal, and close inside. Runtime rendering behavior remains untested; reversed argument values are statically confirmed.

### A18 — P3: rejection diagnostics and live preview are not the hard gates

**Evidence:** whyWait uses conflict in either direction (631) and low volume/no structure (635–638) even though those are not universal hard gates (524–527). Counters (1169–1189) count overlapping flat-bar conditions, not rejected candidate trades, and can increment on bars with successful entries. Dashboard refreshes every last-bar update (1456); equal-timeframe trend, scores and pending bracket previews can fluctuate intrabar while order events are confirmed-only.

**Repair:** distinguish live preview from confirmed signal, and report candidate-specific reasons. **Test:** accepted long while short-side conflict exists; neutral structure and volume behavior; intrabar reload.

## Inspected protections worth retaining

- HTF requests at 203–210 offset all expressions and use lookahead_on. Lower timeframe results are excluded at 228–235; equal timeframe reads chart values. No unoffset HTF lookahead was found. Above-daily charts are marked unusable for MTF, but not explicitly blocked from trading.
- Confirmed pivot availability at 299–326 is used without backdating order events. Intrabar pivot/score previews may move, but closed-bar state machine decisions are gated at 868.
- Default Signal Close entry occurs after existing-position management, avoiding pre-close target credit on that signal candle.
- For positions already open at bar start, the original stop is checked before targets. BE/trail updates occur after that check and are effectively eligible on the next bar. This is a close-update policy, not an immediate intrabar break-even simulation; retain/disclose it rather than alleging retroactive BE execution.
- Target-hit booleans prevent the same target repeatedly triggering across ordinary active bars. There is still no quantity ledger.
- Dashboard and debug tables use persistent handles and are removed when disabled. FVG array count is bounded; most ordinary price/EMA plots are straightforward.
- No empirical performance or proven-method claim was found in the file. It is an informational indicator, as acknowledged at 727–729; comments describing “real resting orders” at 809 overstate what it does.

## Complete section coverage

| Lines | Sections reviewed | Result |
|---|---|---|
| 1–172 | Declaration, inputs, session engine, rounding | A05, A09, A15 |
| 177–290 | Core series, MTF, momentum, regime | Retain confirmed HTF; A10–A11 |
| 299–499 | Structure, proximity, breakout/retest, long/short setups | A06; no explicit ICC stages |
| 507–646 | Room gates, score, grades, wait reasons | A11, A14, A18 |
| 652–802 | Stops, targets, prices, sizing, early exits, trails, fills | A02–A03, A08–A09, A13 |
| 812–1194 | Persistent state, management, entries, debug counters | A01, A04, A07, A12 |
| 1200–1407 | Lines, labels, watch, zones, FVG, plots | A16–A17; latest pivot ≠ nearest across history |
| 1412–1595 | Alerts, dashboard, debug table | A03, A12, A18 |

Potential dead/unused outputs: DI outputs, `beApplied`, and `initialRisk` are calculated/assigned but do not drive management; confirm intended use before deleting. The unused pieces do not establish a trading defect on their own.

## Verification boundary and references

Static audit complete. Pine compilation, live/replay checks, backtest results, fees calibration and walk-forward performance are **not performed**. No statistical win rate can be inferred from this audit.

Official references checked: [TradingView strategies](https://www.tradingview.com/pine-script-docs/concepts/strategies/), [repainting](https://www.tradingview.com/pine-script-docs/concepts/repainting/), and [time/DST](https://www.tradingview.com/pine-script-docs/concepts/time/). They inform execution/confirmation/session requirements; the line-specific findings above come from the supplied source.
