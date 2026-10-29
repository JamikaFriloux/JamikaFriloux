# MEKA ALPHA PRO 4.0.1 — validation ledger

Date: October 29, 2026. **4.0.1 has not been compiled in TradingView by the author, replayed, backtested or forward-tested.** No win rate, profit factor, expectancy or drawdown figure exists for any version.

| Level | Meaning | 4.0 status |
|---|---|---|
| L1 Static | Code reading, text and structure checks, grammar parse | **Done** |
| L2 Reference model | Rules ported to Python and exercised on synthetic candles | **Done** (port, not Pine) |
| L3 TradingView compile | Pine Editor compiles the file | **Not observed for 4.0.1.** 4.0 ran on the user's Gold 1m chart (they reported 10 trades), so 4.0 compiled; 4.0.1 changes execution and display code and must be recompiled. |
| L4 Replay / backtest | Behaviour on real data; emulator ledger | **No.** Only the user's 4.0 sample exists: 10 trades on Gold 1m, which is statistically meaningless (win-rate 95% range 17–69%) and pre-dates the execution corrections. The author's sandbox could not reach any market data. |
| L5 Forward test | Paper trading on live candles | **No** |

## What was actually done for 4.0.1

1. **Grammar parse (L1):** `pynescript` 0.3.0 parsed both generated files without error. It rejects broken syntax (verified with deliberate errors), but it does **not** check types, built-in signatures, UDT/method rules or other v6 semantics. This is not compilation.
2. **Build parity (L1):** `tools/build.py` asserts the signal engine, shared execution helpers and display block are byte-identical in both files. Raw signals therefore cannot differ between indicator and strategy.
3. **Reference tests (L1 + L2): 42/42 passing** (`python3 -I tools/test_reference.py`):

| Group | # | Establishes (on the Python port) |
|---|---|---|
| Structure | 3 | First break = CHoCH, later same-direction breaks = BOS; each swing broken once; CHoCH can be disallowed; sweep = wick through a swing with the close back inside. |
| ICC stages | 9 | Indication, correction and continuation on three different candles. One giant candle only indicates. No indication without a known swing (impulse origin). A deeper pullback moves the trigger to that candle's high; the stop includes it. The room check blocks when a newly confirmed swing leaves no space. Retracement zone 38.2% boundary exact. A close beyond the origin, a bias change or expiry cancels. VWAP, volume and required-sweep each block continuation. Far structure is rejected (not clipped). ATR and wider-of-both stop methods. A limit entry rests at the trigger. |
| Execution | 13 | No credit for targets touched on the signal candle. Gap fill at the real open; 2.5× fill-risk ratio triggers the gap exit next open. Long/short gaps through the stop exit at the worse open. Stop + target on one candle → stop-first, target marked touched. TP1 then break-even applies from the next candle only. 1 unit → TP2 tranche. Configurable allocations (50/30/20 → 5/3/2 of 10; 70/30) conserve quantity for 1–2,000 units at steps 1 and 0.01, with TP2 always populated. A limit touch without trade-through does not fill and expires after N candles. An intrabar limit fill defers targets; a gap through the limit fills at the open. Costs (commission, half spread, slippage on market/stop only) reduce R exactly as specified. Structure break → exit request → exit at next open. Cooldown 0 never re-enters on the exit candle. Targets strictly ordered after coarse rounding. |
| Execution corrections (4.0.1) | 6 | An exact touch is not a fill and never moves the stop. A touch on an intrabar limit-fill candle is neither credited nor used for break-even. Break-even needs a TP1 fill (1 unit: a certain touch). Emulator mode: targets then stop when the high is nearer the open; stop only when the low is nearer. Emulator-mode intrabar limit fills credit only prices visited after the fill. Conservative mode always stops first. |
| Properties | 1 | 150 random 600-candle series with randomized settings (framework, stops, corrections, limit/market, costs, BE, trail, early exit, conservative/emulator same-candle rule): stages always strictly later; market fills exactly one candle after ENTER, limit fills within N candles or a cancel at exactly N; nothing exits before a fill; exited quantity = entered quantity; every signal has stop < entry < TP1 < TP2 < TP3 (mirrored for shorts), all distinct, risk within limits; limit references never through the close; costs never negative. Exercised more than 100 trades, more than 20 ICC continuations and more than 10 limit fills. |
| Sessions | 3 | Pine window formula ported with `zoneinfo`: US/UK DST-mismatch weeks (March 9–27, October 26–31, 2026), Tokyo fixed, boundary-crossing candles rejected, cutoff minutes, weekday mask, 17:00 New York day roll. |
| Static Pine | 7 | Shared blocks identical; declarations (`calc_on_every_tick=false`, `calc_on_order_fills=false`, `process_orders_on_close=false`, `pyramiding=0`); no `strategy.*` in the indicator; every `request.security` uses `[1]` offsets with `lookahead_on`; no probability / accuracy / guarantee / confidence wording and no percentage performance claims in visible text; balanced brackets and 4-space indents; every `:=` target declared. |

**Not ported to Python:** session high/low and opening-range tracking, the breakout baseline, daily limits, the performance table, drawings and the dashboard. These are covered only by code reading.

## Highest compile risks for the first TradingView run

These are reasoned about, not observed. If the compiler complains, these are the likely places:

- The user-defined type `SessTrack` and its `method step(...)`, `var SessTrack x = SessTrack.new()`, a ternary that yields a `SessTrack` or `na`, and field assignment `sMain.orUp := true`.
- `switch` expressions returning floats (`pDisp`, `pAtrPct`).
- `syminfo.volumetype` (expected values `base` / `quote` / `tick` / `n/a`).
- `for l in array.from(lnE, lnS, ln1, ln2, ln3)` over possibly-`na` line handles.
- `strategy.entry(..., limit = isLimit ? refEntry : na)` (na means market) and `backtest_fill_limits_assumption=1` in the declaration.
- `strategy.closedtrades.exit_comment / exit_id / size / exit_price / profit`.
- Text-alignment arguments in `box.new` and `table.cell`.
- Warnings about unused values (`plusDI`, `minusDI`, `zoneTop`) are expected.

## TradingView test matrix (all NOT RUN)

The step-by-step version, with the execution check before any statistic and the ICC-vs-baseline comparison, is in `MEKA_ALPHA_PRO_4_TESTING_PLAN.md`.

| # | Test | Required outcome |
|---|---|---|
| 1 | Compile indicator / strategy | No errors |
| 2 | Bad chart (daily, Heikin Ashi, TF ≥ confirmation TF) | Clear MEKA error |
| 3 | Data Window parity on one chart | *Signal*, *Candidate*, *ICC stage* identical in both scripts |
| 4 | Reload / reopen after candles close | Past signals and IDs unchanged |
| 5 | Realtime then reload | Closed-candle signals unchanged |
| 6 | Bar Replay through an ICC setup | Indication, correction, trigger on three candles; WATCH texts match the zone/trigger shown |
| 7 | Signal candle already beyond TP1 | No TP1 credit |
| 8 | Gap at entry | Fill at real open; gap exit when > 1.5× risk |
| 9 | Stop + TP on one candle | Indicator conservative: stop. Indicator *Match TradingView emulator*: same result as the strategy with Bar Magnifier off |
| 9b | Candle high exactly at TP1 | Both scripts: TP1 *touched, not filled*; stop not moved |
| 9c | Limit filled inside a candle that also passed TP1 | Indicator conservative: no TP1 credit, no break-even next candle |
| 10 | TP1 then pullback, BE on | BE from next candle only |
| 11 | 1, 2, 3, 10 units with TP3 on/off | List of Trades tranche quantities sum to entry |
| 12 | Limit mode | Touch-only does not fill; cancels after N candles with alert; fill-bar targets deferred (indicator) |
| 13 | Early exits | Structure break / bias flip / max hold → EXIT next open; one EARLY_EXIT alert |
| 14 | Sessions in DST weeks | Windows at the correct local times |
| 15 | Overlapping London/NY | One trade per setup |
| 16 | Midnight and 17:00 NY with a position open | Protection unchanged; day counters reset at 17:00 only |
| 17 | News window / flat window while holding | No new entries; stops and targets stay active |
| 18 | TVC:GOLD vs GC1! | TVC: filters off "no volume"; GC: VWAP + volume on |
| 19 | 6J vs USDJPY | Native direction; USDJPY sizing = point value ÷ price |
| 20 | Unknown symbol | NO TRADE "Market not recognised" |
| 21 | Alerts | One JSON per event; ENTER and FILLED separate; no HOLD repeats |
| 22 | Performance table vs List of Trades | 10 trades reconciled by hand including modeled costs |
| 23 | Breakout baseline | Opening-range box drawn; one breakout per session and direction |
| 24 | Margin 100% on ES with $10k | "Entry order was not filled" cancel, no stuck order |

## Research protocol before quoting any statistic

1. Pass the matrix above and fix any accounting defect first.
2. Record version, feed, contract, timeframe, dates, Properties (capital, margin, Bar Magnifier) and every input.
3. Fix the out-of-sample date in advance. Use chronological folds (for example 12 months develop / 3 validate / 3 test, rolled forward) and a final untouched holdout. A position belongs to the fold in which it was entered.
4. Report per instrument × mode × session × direction using the performance table, complete positions only, with trade counts; amber (< 30) rows are not evidence.
5. Compare ICC against the Trend-pullback and Breakout baselines with identical costs, sessions and dates.
6. Test break-even on vs off and trailing on vs off on the same out-of-sample window.
7. Stress costs at ×1.5 and ×2; check ±20% neighbourhoods of key settings.
8. Paper-trade with alerts for several weeks and log every difference between alert, emulator fill and real fill.

**Passing L1/L2 is not evidence that the scripts compile or that the method has an edge.**
