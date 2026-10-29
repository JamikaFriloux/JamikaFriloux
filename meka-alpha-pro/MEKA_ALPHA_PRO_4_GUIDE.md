# MEKA ALPHA PRO 4.0.1 — guide

A private trading assistant for TradingView. It reads price structure, finds a defined setup, and tells you what to do in plain English: **WAIT, WATCH LONG / SHORT, ENTER LONG / SHORT, HOLD, TAKE PROFIT, EXIT, NO TRADE**. Every entry comes with an entry price, a stop and profit targets. A companion strategy measures the actual results.

> **Honest status:** the code is complete, but **the author has not compiled 4.0.1 in TradingView** (a previous build of the strategy did compile on your chart). It has been grammar-parsed and its rules exercised in a Python model; see `MEKA_ALPHA_PRO_4_VALIDATION.md`. **No win rate, profit factor or drawdown exists yet.** You will measure those yourself with the strategy. Preset values are starting points, not validated settings.

---

## 1. Installation

1. In TradingView open **Pine Editor → New → Indicator**. Delete the template, paste **all of** `MEKA_ALPHA_PRO_4_INDICATOR.pine`, click **Save**, then **Add to chart**.
2. Do the same with `MEKA_ALPHA_PRO_4_STRATEGY.pine` in a new script. It is a separate script; don't paste both into one.
3. Use **standard candles** on a **minute chart**: SCALP 1/3/5 minutes, DAY TRADE 5/15 minutes. Heikin Ashi, Renko, range bars and daily charts stop with a clear message.
4. Open the settings (gear icon). Group **1 · Quick setup** is all most people need:
   - **Market:** Auto recognises GC, MGC, XAUUSD, TVC:GOLD, NQ, MNQ, NAS100/US100, ES, MES, SPX500/US500, EURUSD, 6E, USDJPY and 6J. If the dashboard says *Market not recognised*, pick the market here.
   - **Trading mode:** SCALP or DAY TRADE.
   - **Strategy logic:** *ICC hybrid* (main). *Trend pullback* and *Breakout* are simpler baselines for comparison.
   - **Chart view:** *Clean* (signals, levels, minimal dashboard) or *Detailed* (adds BOS / CHoCH, liquidity sweeps, pullback zones, session levels and opening ranges).
5. Group **2 · Risk & targets:** set your **account size** and **risk per trade**. Position size is calculated from the stop distance in dollars.
6. **Strategy only, Properties tab:**
   - **Initial capital:** your account size.
   - **Margin:** your broker's margin. The declared 5% is a placeholder. At 100% margin, futures orders get rejected and appear as "entry order was not filled".
   - **Commission and slippage:** leave at **0**. The script's own cost model (group 4) is subtracted in its performance table. If you prefer Properties costs, turn **Use preset cost model** off and set commission 0 / spread 0 / slippage 0 in group 4, so nothing is counted twice.
   - **Bar Magnifier** (paid plans): optional, makes intrabar fills more realistic.
7. **Alerts:** right-click the indicator → *Add alert* → condition **MEKA ALPHA PRO 4.0 → Any alert() function call** for the full JSON messages, or pick a single named condition ("Long entry confirmed", "TP1 reached", …). Re-create alerts after changing any setting, because TradingView alerts keep a snapshot of the settings.

## 2. Recommended initial settings — Gold and Nasdaq-100

These are **research starting points**. They are what the presets load, and they still need your own out-of-sample testing.

| Setting | Gold SCALP | Gold DAY | NQ SCALP | NQ DAY | Why |
|---|---|---|---|---|---|
| Chart | 1m or 3m | 5m or 15m | 1m or 3m | 5m | Mode definition |
| Confirmation TFs | 15m + 1H | 1H + 4H | 15m + 1H | 1H + 4H | Both must agree |
| Sessions (entries) | London 08:00–11:00, NY 08:30–11:30 | same | NY 09:35–11:30 only | same | Gold is liquid in London and NY; NQ's real liquidity is the cash session; skip the first 5 min |
| Swing strength | 3 bars | 5 bars | 3 bars | 5 bars | Confirmation delay = strength |
| Break candle body | ≥ 0.8 ATR | ≥ 0.8 ATR | ≥ 0.8 ATR | ≥ 0.8 ATR | Gold and NQ produce many weak breaks; demand displacement |
| Min ADX | 20 | 20 | 20 | 20 | Trend filter |
| Min ATR | 0.010% of price | 0.025% | 0.015% | 0.035% | Avoid dead markets |
| Stop distance | 0.5–3.0 ATR | 0.6–3.5 ATR | 0.5–2.5 ATR | 0.6–3.0 ATR | Gold wicks more; wider structure is rejected, not clipped |
| Stop buffer | 0.20 ATR | 0.20 ATR | 0.15 ATR | 0.15 ATR | Beyond the structural low/high |
| Max distance from EMA20 | 2.5 ATR | 2.5 ATR | 3.0 ATR | 3.0 ATR | Don't chase extended moves |
| VWAP side filter | on (needs a feed with volume) | on | on | on | Intraday institutional reference |
| Volume filter | futures only | futures only | on (futures) | on | Spot / CFD volume is unreliable |
| Targets | TP1 1R 50% / TP2 2R 50% | same, TP3 optional | same | same | Default per spec |
| Break-even after TP1 | off: test it | off: test it | off: test it | off: test it | Must earn its place (see §6) |
| Risk per trade | 0.25–0.5% | 0.25–0.5% | 0.25–0.5% | 0.25–0.5% | Conservative while unvalidated |
| Costs (illustrative) | XAUUSD spread 0.25; GC $2.40/side, MGC $0.70/side + 1 tick | same | NQ $2.40/side, MNQ $0.70/side + 1 tick | same | Replace with your broker's numbers |

**TVC:GOLD note:** TVC:GOLD has no volume, so the VWAP and volume filters switch off automatically. The dashboard's *Filters* row says so. TVC:GOLD is also a reference price, not something you can trade, so its fills won't match your broker. For results you can rely on, test on your broker's XAUUSD feed or on GC/MGC.

## 3. How a signal is built (ICC hybrid)

ICC = **Indication → Correction → Continuation**. It's a transparent, rule-based research hypothesis, not a proven edge. Every step happens on a different **closed** bar.

**0. Filters (all must pass, otherwise WAIT or NO TRADE explains which one failed)**
- **Higher-timeframe bias:** for each confirmation timeframe, the *previous completed* candle's close vs its EMA50, plus the EMA50's slope. Both timeframes must agree. The script never reads a forming higher-timeframe candle.
- **Trend strength:** ADX(14) ≥ minimum.
- **Volatility:** ATR(14) ≥ minimum % of price.
- **Not overextended:** within the allowed distance from EMA20.
- **Inside an enabled session window**, before the last-minutes cutoff, outside news blackouts, within your dates and daily limits.

**1. Indication: a break of structure in the bias direction**
- Swings are confirmed pivots (N bars each side) and are usable only from the bar on which they became known.
- A **BOS** is a candle that *closes* beyond the latest swing high (low) by at least 1 tick, in the direction of the existing structure. A **CHoCH** is the first such break against the prior structure. Each swing can be broken only once.
- The breaking candle's body must be ≥ the *break candle body* setting × ATR (momentum).
- Frozen at this moment: the broken level, the **impulse origin** (the swing on the other side), the impulse extreme, and the ATR.

**2. Correction: a pullback into the zone**
- On a later candle, price must trade into the **pullback zone**: the 38.2–78.6% retracement of the impulse *or* a retest of the broken level ± 0.25 ATR (selectable).
- **Liquidity sweep:** a wick beyond a known swing or a previous session's high/low that closes back inside is marked as a sweep. It can optionally be required.
- The setup is cancelled if a candle **closes** beyond the impulse origin, if the higher-timeframe bias changes, if it expires, or if the session or news window closes.

**3. Continuation: the trigger**
- On a still later candle, a candle in the trend direction must **close** beyond the **trigger**: the high (low for shorts) of the deepest pullback candle so far. The trigger is saved before the candle being tested, so a candle cannot move its own trigger.
- Optional checks on that candle: correct side of VWAP, above-average volume.

**4. Validation before ENTER**
- **Stop:** beyond the deepest pullback extreme + buffer (*Structure*), or *ATR × multiple*, or *Wider of both*. Rounded to a valid tick. If it is tighter or wider than the allowed range, the setup is **skipped** and the stop is never squeezed.
- **Room:** the next opposing swing must leave space for TP1.
- **Size:** `risk $ ÷ (stop distance × USD per point)`, rounded down to whole contracts (futures) or your lot step. If even one unit is too much risk, the setup is skipped.

**Baselines.** *Trend pullback*: a close back through EMA20 after touching it, in the bias direction. *Breakout*: the first close beyond the active session's opening range in the bias direction, with the stop at the middle of the range. Both use the same filters, sizing, targets, costs and execution as the ICC hybrid, so the comparison is fair.

## 4. Entries and exits

**Entry order** (group 4):
- *Market at next open* (default): ENTER appears at the signal close and the fill is the next bar's open.
- *Limit at breakout retest*: a limit order rests at the trigger level for N bars. It counts as filled only if price **trades through it by 1 tick**, which avoids phantom fills from a mere touch; a gap through it fills at the open. If it isn't filled in time, it is cancelled and the *Setup canceled* alert fires.

**Targets.** TP1 / TP2 (/ TP3) at R multiples of the planned risk (R = entry reference − initial stop). The split is configurable: 50/50 by default, 50/30/20 with TP3. Sizes are whole units and always add up to the full position; leftover units go to the last target. A 1-unit position goes entirely to TP2.

**Target fills.** Profit targets are limit orders. They fill only when price trades **through** them by 1 tick (setting *Limit orders fill only when price trades through by*), or when a candle opens beyond them. This is the same rule as the strategy's declared *Verify price for limit orders = 1*.

**Touched vs reduced.** The dashboard shows each target as *open*, *touched, not filled*, or *filled* / *reached (simulated)*. A target is "touched" when price reached it; it is "filled" only when the position was actually reduced. That happens when the strategy's emulator fills the order, or when the indicator credits it under its rules below.

**Stops and management.**
- The **initial stop** protects the whole position from the first tick. In the strategy it is sent together with the entry order.
- **Break-even** (optional): once the **TP1 tranche has been filled** (a single-unit position, which has no TP1 tranche, uses a TP1 touch that certainly happened while it was open), the stop moves to the fill price from the next candle onward. It never acts on earlier prices. After costs a break-even exit can still lose a little.
- **Trailing** (optional, after TP1): *ATR* (close − N × ATR) or *Swing structure* (latest confirmed swing ± buffer). It only ever tightens and is updated at candle closes.
- **Early invalidation exits** (decided at a close, executed at the next open): structure breaks against the trade (on by default), higher-timeframe bias flips (optional), maximum holding time, session end or flat window, end of test dates. One extra exit: if the entry gapped so far that the real risk exceeds 1.5× the planned risk, the trade is closed.

**What the indicator assumes (it cannot see inside a candle).**
- If a candle touches both the stop and a target, the **stop is assumed first** by default. This is conservative and counted in the performance table footer. Setting *Indicator: stop and target in the same candle* to **Match TradingView emulator** uses the emulator's rule instead: price visits the extreme nearer the open first. Use it to check the indicator against the strategy trade by trade.
- A limit entry filled *inside* a candle: on that candle only the stop is checked; targets wait for the next candle, and nothing seen in that candle counts as a touch or moves a stop. In emulator mode, only prices the emulator's path visits after the fill can fill a target.
- Gaps fill at the open: worse for stops, better for targets.
- The strategy uses TradingView's broker emulator instead, which has its own intrabar assumptions (and Bar Magnifier if enabled). Expect small differences between the two scripts on such candles. The **signals themselves are identical**, because both scripts contain the byte-identical signal engine.

## 5. Dashboard and chart

**Dashboard order:** the status, then **NEXT** (the instruction, largest text), then **MISSING / NOTE / WHY** (the explanation), then the trade levels with each target's state. Background details come last and smaller.

**Dashboard rows (Detailed view):** status · next step · why / what's missing · instrument · mode · filters · session · market bias · setup · trade · entry · stop · TP1 / TP2 / TP3 with their state · risk and size. **Clean view:** status, next step, what's missing, and the trade levels when a trade is active.

Examples of what it says:
- *WAIT* — "Higher timeframes are not aligned (15m up, 1H flat). Waiting for agreement."
- *WATCH LONG* — "Bullish break confirmed at 4021.30. Waiting for a pullback into 4015.20 – 4018.40."
- *WATCH LONG* — "Pullback reached the zone with a liquidity sweep. Buy trigger: a bullish close above 4019.80."
- *ENTER LONG* — "Buy at the next open (about 4021.40) with stop and targets."
- *TAKE PROFIT* — "Take profit: TP1 filled. Hold the remaining 2 with the stop at 4016.10."
- *EXIT* — "Close the long at the next open. Market structure broke against the trade."
- *NO TRADE* — "Outside your trading sessions." / "Daily loss limit reached. No more entries today."

**Chart.** Context is faint so the candles stay readable. The active trade is prominent: a bold entry line, a thick red stop, shaded red risk and green reward areas, and solid price tags for entry, stop and targets (a filled target gets ✓).
- *Clean:* BUY/SELL labels, entry (dashed), stop (red) and target (green dotted) lines with price tags, plus TP and EXIT/STOP markers.
- *Detailed* adds:
  - BOS / CHoCH lines and labels
  - "Sweep" markers
  - the shaded ICC pullback zone
  - EMA20/50, and VWAP when that filter is used
  - previous Asia / London / New York highs and lows
  - the active session's opening range

## 6. Measuring performance (the strategy)

The performance table is **off by default**: *8 · Display → Show performance table*. Splits use two dates (group 6): **Development** before *Validation period starts*, **Validation**, and **Holdout** from *Holdout period starts*. Each win rate shows its 95% range. The footer prints a **settings fingerprint**; record it before you first look at the holdout. Full procedure: `MEKA_ALPHA_PRO_4_TESTING_PLAN.md`.


The strategy draws a **performance table** with these columns:
- trades
- win rate
- average win and average loss (in R)
- profit factor (USD)
- expectancy (R per trade)
- maximum drawdown (R)
- net USD after modeled costs

It shows them for all trades, long, short, Asia, London, New York, long and short within each session, trending (ADX ≥ 25 at entry), ranging, high-volatility (ATR > 1.25 × its 100-bar average), normal-volatility, and the **Development**, **Validation** and **Holdout** periods.

- A **trade** is a complete position. Partial targets are not counted as separate wins.
- A **win** is net R > 0 after costs, so a break-even exit that loses the commission counts as a loss.
- Counts under 30 are shown in amber. Treat them as anecdotes.
- Instrument and mode are whatever the chart is set to: run one chart per instrument × mode and record each.
- The indicator draws the same table from its simulated trades. The strategy's numbers are the ones to trust.

**Validation procedure (chronological, never random):**
1. Choose the out-of-sample date **before** looking at any result. A typical layout is 12 months to develop, the next 3 to validate, the next 3 untouched. Change rules only on in-sample data.
2. Run each instrument × mode with *ICC hybrid*, then *Trend pullback*, then *Breakout*, with identical dates, costs and sessions. ICC has to beat the simpler baselines out-of-sample to justify its complexity.
3. **Break-even test:** run with *Move stop to entry after TP1* off and on over the same out-of-sample period. Keep it only if expectancy and drawdown both improve and the out-of-sample trade count is meaningful.
4. **Walk-forward:** roll the window forward (develop → validate → test) and record each fold's out-of-sample row. A setting that works in only one fold is not robust.
5. **Costs:** repeat the final out-of-sample run with costs × 1.5 and × 2 (group 4). If the edge disappears, it was never there.
6. **Neighbourhood check:** nudge key settings (break candle body, swing strength, stop range) by ±20%. Results should degrade gently, not collapse.
7. Only then paper-trade with alerts for several weeks and compare against the backtest.

## 7. Alerts

| Event | When it fires |
|---|---|
| `SETUP_FORMING` | ICC indication confirmed (flat only) |
| `LONG_ENTRY_CONFIRMED` / `SHORT_ENTRY_CONFIRMED` | Signal close; contains entry, stop, targets, size, risk |
| `ENTRY_FILLED` | Market fill at the next open, or a limit fill (indicator: simulated; strategy: emulator) |
| `TP1_REACHED` / `TP2_REACHED` / `TP3_REACHED` | Target tranche reduced (not a mere touch) |
| `STOP_HIT` | Stop filled |
| `EARLY_EXIT` | A close-based exit decision; the exit happens at the next open |
| `SETUP_CANCELED` | ICC setup cancelled, or a limit order expired / entry not filled |

Each alert is one JSON object, ready for a Telegram bot. Fields: `app`, `version`, `event`, `symbol`, `market`, `timeframe`, `mode`, `logic`, `side`, `session`, `entry`, `stop`, `tp1`, `tp2`, `tp3`, `qty`, `risk_usd`, `basis` (`next_open` / `limit_order` / `simulated_fill` / `emulator_fill` / `close_decision`), `trade_id`, `bar_close_utc`, and a human-readable `message`. Alerts fire once per candle close, on closed candles only. HOLD candles never repeat alerts.

For a future Telegram bridge, forward `message` as the chat text and use `trade_id` + `event` to drop duplicates.

## 8. Markets and quotes

- Sizing uses **USD per 1.0 price move per unit**. USD-quoted symbols use TradingView's point value. **USDJPY** uses point value ÷ price, which is exact at that candle's rate. Other quotes need the manual value in group 2.
- **6J is quoted in USD per yen**: a 6J LONG means long yen, the opposite of a USDJPY LONG. The script always trades the chart's own direction and never inverts orders.
- Futures trade whole contracts. Spot and CFD use your lot step.
- **Trading hours:** futures pause daily (17:00–18:00 New York) and spot FX closes at the weekend. The trading day (daily limits) resets at 17:00 New York, not midnight. Entry windows are local-time research windows (DST handled per city), not exchange calendars: holidays and early closes are not modelled.

## 9. Known limitations

- **Not compiled by the author in TradingView;** not backtested; no calibrated settings.
- **Intrabar order is unknown.** Both the indicator's conservative rules and the emulator's assumptions are approximations. Bar Magnifier helps but doesn't recreate every tick.
- **TradingView fills are not broker fills:**
  - spreads change during news
  - stops can slip more than the model
  - CFD prices differ between brokers
- **News:** only three manual times plus the pause switch. There is no live economic calendar in Pine.
- **Room check** uses the latest opposing swing only.
- **Performance table** groups by session at entry, using one label when windows overlap (priority New York > London > Asia). Regime labels use the entry candle's ADX/ATR.
- **One chart = one instrument and mode.** There is no portfolio-level result.
- **Continuous futures (e.g. NQ1!)** are roll-adjusted; check actual contracts too.
- **Limit fill** requires trade-through by 1 tick. This matches the strategy's declared "verify price for limit orders = 1". Keep them equal if you change one.

## 10. Validation checklist

Tick these in TradingView before trusting anything (full matrix in `MEKA_ALPHA_PRO_4_VALIDATION.md`):

- [ ] Both scripts compile; note any warnings.
- [ ] Data Window: *Signal*, *Candidate before filters* and *ICC stage* identical between indicator and strategy on the same chart.
- [ ] Reload the chart: past signals don't move or disappear.
- [ ] Bar Replay through one ICC long and one short: indication, correction and trigger appear on three different candles.
- [ ] A signal candle whose high already passed TP1 does not get TP1 credit.
- [ ] A gap entry: fill price is the real open; the gap exit triggers when risk exceeds 1.5×.
- [ ] A candle touching stop and TP1: the indicator shows the stop; compare the strategy with Bar Magnifier off and on.
- [ ] One-contract trade: no TP1 tranche; everything exits at TP2 or the stop.
- [ ] List of Trades: tranche quantities add up to the entry quantity; every unit had a stop.
- [ ] Limit mode: an order that only touches the price doesn't fill; it cancels after N candles with an alert.
- [ ] DST weeks (March and late October/early November): session windows start at the correct local times.
- [ ] TVC:GOLD shows "this feed has no volume"; GC shows VWAP and volume filters on.
- [ ] 6J dashboard direction vs USDJPY.
- [ ] Alerts: JSON arrives once per event; ENTER and FILLED are separate messages.
- [ ] Performance table vs List of Trades for 10 trades by hand (net of modeled costs).
