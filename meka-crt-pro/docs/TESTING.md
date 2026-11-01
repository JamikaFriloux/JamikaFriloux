# Testing and Verification

## A. First compile (do this first)

The scripts were written for Pine Script v6 but **have not yet been compiled inside TradingView**. Paste each file into the Pine Editor and press *Save / Add to chart*. If the compiler reports an error, copy the **line number and message** and send it back. Each fix is usually one line.

## B. Visual verification checklist (indicator, 5M chart)

Use **Bar Replay** on a few days of XAUUSD/GC and NQ.

- [ ] The 1H CRT HIGH (red), LOW (green) and 50% (gold dashed) start at the open of the **previous completed** 1H candle and match its high/low exactly. Check with the Data Window on a 1H chart.
- [ ] Levels change only on the first 5M bar of a new hour, and only when that hour's reference candle passes the size filter.
- [ ] In Detailed mode the 4H range is thicker than the 1H range, and previous ranges are faded and capped.
- [ ] A sweep label appears on the bar that **closed back inside**, never earlier. Step Replay one bar at a time through a sweep to check this.
- [ ] A level that broke out (3 closes beyond) shows "BROKEN" (Detailed) and never produces a sweep later.
- [ ] The same level is never labelled twice.
- [ ] "15M ✓" appears only after a 15M candle that closed **after** the breach. Compare with a 15M chart.
- [ ] BUY/SELL appears on a closed 5M candle. "FILL" appears on the next bar at its open.
- [ ] Only one signal per setup. A new setup needs a new sweep.
- [ ] TP1/TP2/SL lines match the dashboard. TP1 = the CRT 50% when that is ahead and ≥ 0.8R.
- [ ] On a bar touching both SL and TP, the indicator records **STOP HIT**.
- [ ] Turning entry windows off stops new signals, but ranges, sweeps and dashboard rows keep updating.
- [ ] Reload the chart after a live session. Signals on historical bars are **identical** to what printed live, which shows nothing repaints.
- [ ] Changing the chart timeframe to 1H shows "CHECK TIMEFRAMES" instead of signals.

## B2. Logic replay (outside TradingView)

`tools/replay/meka_replay.py` is a bar-for-bar Python port of the engine. Use it to measure setup outcomes on any 5M CSV (`Date;Open;High;Low;Close;Volume`, server time = NY+7). `tools/replay/repaint_test.py` checks that truncating history never changes earlier signals.

```bash
python3 tools/replay/meka_replay.py XAU_5m.csv --start 2024-02-01 --end 2025-02-01 --version both
```

```bash
python3 tools/replay/repaint_test.py XAU_5m.csv 2024-02-01 2025-02-01 v2
```

The results for gold are in `docs/STATE_MACHINE_AUDIT.md`. If you change the Pine rules, change the port too, or its numbers stop describing the indicator.

## B3. Diagnostic mode (inside TradingView)

Turn on **Display → Diagnostic log**. Then step through Bar Replay and check, for each row:
- [ ] SKIPPED rows name the exact block (4H bias / 50% already reached / no room).
- [ ] STRUCTURAL rows happen on a bar whose wick touches the dotted **INVALID** line.
- [ ] MISSED rows happen on a bar touching the dotted **LOCKED 50%** line.
- [ ] Setups survive the first bar of a new hour / 4H candle. The dashboard's "Locked" row notes "reference candle has rolled".
- [ ] "SWEEP IN PROGRESS" turns into "SWEEP CONFIRMED & RECLAIMED" only on the first 5M bar after a 15M candle closes back inside.

## B4. Model C

See the checklist in `docs/MODEL_C.md` §5. The logic replay and the no-future test:

```bash
python3 tools/replay/model_c.py gold XAU_5m.csv
```

```bash
python3 tools/replay/model_c_repaint_test.py gold XAU_5m.csv
```

## C. Backtesting protocol (strategy)

1. **Split the data before you look at results.** Use `Trade from / Trade until` to choose an in-sample period, for example the oldest 60%. Do all tuning there. Keep the most recent 20–40% **untouched** and run it **once** at the end.
2. Test **Gold and NQ independently**, and spot gold, GC and MGC separately (different costs).
3. **Market regimes**: run the same settings across a trending period, a range-bound period, a high-volatility period (CPI/FOMC weeks) and a low-volatility holiday period. A robust setup should not depend on one regime.
4. **Robustness, not optimisation**: change one parameter at a time by ±20–30%, for example reclaim window 4/6/8, minRR 1.5/2/2.5, maxRiskATR 3/4/5. Prefer a plateau of acceptable results over a single best peak.
5. **Sample size**: fewer than about 100 trades per market is not enough to judge win rate or profit factor. Report confidence honestly.
6. Record, **only from the Strategy Tester**: net profit, number of trades, win rate, profit factor, average trade (expectancy), max drawdown, largest loss. Report them only once actually measured. No numbers are claimed in this repository.
7. Compare the strategy's trade list with the indicator's labels on 10–20 trades. They should match except for the intrabar ordering case below.

## D. Known limitations (stated honestly)

| Limitation | What the code does instead |
|---|---|
| Pine cannot know the true tick order inside a bar. | Indicator: stop-first when both are touched. Strategy: TradingView's broker emulator (OHLC heuristic, or Bar Magnifier if enabled). These can differ on rare bars. A `SYNC` exit keeps the strategy in step with the engine. |
| Two scripts cannot share code without publishing a library. | `tools/build_strategy.py` generates the strategy from the indicator, so the engine is byte-identical. Edit the **indicator**, then re-run the script. |
| 15M information arrives on the first 5M bar after the 15M candle closes. | Accepted as a conservative delay of at most one chart bar. |
| Daily/weekly levels follow the symbol's exchange session. | Use the same data feed for live trading and testing. |
| CFD spread varies and is not modelled per bar. | Model it with strategy slippage ticks. |
| Simulated fills ignore partial-fill and liquidity effects. | Use realistic slippage, and test micros before full-size contracts. |
| "Equal highs/lows" use confirmed 15M swings only. | Their tolerance is `eqTolATR` × chart ATR. |
| A 50% partial on 1 contract is impossible. | The strategy then exits the full position at TP2 (or at TP1 if TP1 = 100%). Use ≥ 2 contracts. |
