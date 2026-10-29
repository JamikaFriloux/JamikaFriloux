# MEKA ALPHA PRO 4.0.1 — testing plan and results log

**Status, October 29, 2026:** no backtest of 4.0.1 has been run by the author. The sandbox used to build this version has no access to market data or to TradingView, because its network policy blocks the data hosts. Every number in this file must come from your own TradingView runs. This plan states what to run, in what order, and how to label each result honestly.

## 0. About the first Gold 1-minute sample (10 trades, 40% wins, PF 0.82)

- **Statistically it says almost nothing.** With 4 wins in 10 trades, the 95% range for the true win rate is roughly **17%–69%**. A profit factor from 10 trades swings wildly with one trade.
- It was produced by **4.0**, whose execution model had the defects fixed in 4.0.1 (see `CHANGELOG.md`). Those numbers are not comparable to 4.0.1 results.
- **Do not change any trading parameter because of it.** Changing settings to fix ten trades is exactly the overfitting that produces backtests that fail live.
- Run it again on 4.0.1 only as part of step 2 below (execution check), not as evidence about the method.

## 1. Labels: what kind of result is this?

Every result you record gets exactly one label:

| Label | Meaning |
|---|---|
| **EXPLORATORY** | Any period you looked at while settings could still change. This includes all of the Development period, and any period whose results you saw before freezing settings. |
| **VALIDATION** | The Validation period, evaluated once with frozen settings. Changes after looking at it make it exploratory. |
| **HOLDOUT (untouched)** | The Holdout period, viewed for the first time with frozen settings whose fingerprint was recorded **before** viewing. One look only. |

The strategy's performance table splits rows into *Development / Validation / Holdout* using the two dates in group 6. It also prints a **settings fingerprint**. If the fingerprint differs from the one you recorded before opening the holdout, that holdout is no longer untouched; relabel it EXPLORATORY.

**Set the dates now, before running anything.** Example for a chart with data from January 2025: Validation starts 1 Jan 2026, Holdout starts 1 Jul 2026. On 1-minute charts TradingView history is short; use Deep Backtesting (paid plans) or 3/5-minute charts to reach enough data.

## 2. Step 1 — verify the execution model before reading any statistic

On one Gold chart and one NQ chart, with the indicator and strategy both added and identical inputs:

1. **Signal parity.** Data Window, 30 random candles: *Signal*, *Candidate before filters* and *ICC stage* must be identical in both scripts. Any difference is a bug; report it.
2. **Fill parity.** Set the indicator's *stop and target in the same candle* to **Match TradingView emulator** and Bar Magnifier **off** in the strategy. Pick 10 trades from the strategy's List of Trades. For each, the indicator's dashboard and alerts must show the same entry candle and fill price (market: next open), the same TP1/TP2 fill candles and prices, the same stop candle, and the same remaining quantity.
3. **Explain every difference.** Allowed causes, each visible in the trade:
   - a limit filled inside a candle, where the emulator's path can differ from the indicator's rule
   - margin rejection (strategy shows *entry order was not filled*)
   - TradingView rounding of fill prices
   - Properties slippage not equal to 0

   Anything else is a defect. Send me the candle time and both outputs.
4. **Touch vs fill.** Find a candle whose high equals TP1 exactly. Both scripts must show TP1 *touched, not filled*, and the stop must **not** move to break-even.
5. **Break-even timing.** With break-even on, the stop moves on the candle **after** the TP1 fill in both scripts, never on the TP1 candle.
6. Switch the indicator back to **Stop first (conservative)** for normal use. Expect it to look slightly worse than the strategy on candles where the stop and a target were both touched; the performance table counts those candles.

Only when steps 1–5 pass do the strategy statistics mean anything.

## 3. Step 2 — compare the ICC hybrid with both baselines

Use the **strategy**, Properties: realistic margin, commission 0, slippage 0 (the cost model in group 4 handles costs), Bar Magnifier as you prefer but **the same for every run**.

For each market × mode × timeframe below, run three times, changing only *Strategy logic*: ICC hybrid, Trend pullback (baseline), Breakout (baseline). Turn on *Show performance table*. Record the rows listed in §5.

| Market (feed) | Mode | Timeframes |
|---|---|---|
| Gold (GC1! or MGC1!, and your broker's XAUUSD) | SCALP | 1m, 3m, 5m |
| Gold | DAY TRADE | 5m, 15m |
| Nasdaq-100 (NQ1! or MNQ1!) | SCALP | 1m, 3m, 5m |
| Nasdaq-100 | DAY TRADE | 5m, 15m |
| S&P 500, EUR/USD, USD/JPY | as above | optional, after Gold/NQ |

That is up to 30 runs for Gold + NQ. Keep every other input at the preset values. The point is to measure the method as specified, not to find a winning combination.

## 4. Step 3 — read the results without fooling yourself

- **Minimum sample:** rows with under 30 trades (amber) are anecdotes. Under 100 trades, treat any edge as unproven.
- **Win rate alone means nothing.** A 40% win rate is profitable if average win is well above 1R. Look at expectancy (R per trade) and profit factor together, after costs.
- **Long and short separately.** Read the *Long* / *Short* rows and the *Long · session* / *Short · session* rows. A method that only works one way in a trending sample is probably riding that trend.
- **Sessions:** compare Asia / London / New York rows. If one session carries all the profit, check whether it has enough trades on its own.
- **Regimes:** the Trending/Ranging and High/Normal volatility rows show whether results depend on market conditions.
- **ICC vs baselines:** ICC is worth its complexity only if, **in the Validation and Holdout rows**, it beats both baselines on expectancy after costs with comparable or lower drawdown and a meaningful trade count. If a baseline does as well, prefer the baseline.
- **Cost stress:** for the best combination, re-run with commission and spread × 1.5 and × 2 (group 4, preset costs off). An edge that disappears at 1.5× costs is not tradable.
- **Break-even test:** re-run the chosen combination with *Move stop to entry after TP1* on vs off. Keep it only if Validation and Holdout expectancy and drawdown both improve.
- **Walk-forward:** move both dates forward by 3 months and repeat. Record each fold's Validation row. Consistency across folds matters more than one good fold.
- **Stop when it fails.** If ICC loses in the Holdout, the honest conclusion is "no demonstrated edge on this market/timeframe", not "change settings and try again". New settings need a new, later holdout.

## 5. Results log (fill in; one line per run and row)

| Date run | Version | Fingerprint | Feed | Mode | TF | Logic | Row | Label | Trades | Win % (95% range) | Avg win R | Avg loss R | PF | Expectancy R | Max DD R | Net USD | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | 4.0.1 | | | | | | All trades | EXPLORATORY | | | | | | | | | |
| | 4.0.1 | | | | | | Long | | | | | | | | | | |
| | 4.0.1 | | | | | | Short | | | | | | | | | | |
| | 4.0.1 | | | | | | Validation | VALIDATION | | | | | | | | | |
| | 4.0.1 | | | | | | Holdout | HOLDOUT (untouched) | | | | | | | | | |

Also record: Properties (capital, margin, Bar Magnifier), the two split dates, the cost inputs, the number of candles loaded, and the first and last trade dates.

## 6. Paper forward test (after a positive holdout only)

Run the indicator with alerts on a paper account for at least 4–6 weeks per market. Log every alert, your actual fill, and the indicator's simulated fill. Compare slippage and missed fills with the cost model, and update the cost inputs from real data, never from backtest results.
