# MEKA ALPHA PRO 4.0-r2 — research build guide

> **Status:** research prototype. The author has **not compiled either file in TradingView**. Both were only parsed by an open-source Pine grammar, and the decision rules were exercised in a Python port (see `MEKA_ALPHA_PRO_4_VALIDATION.md`). Nothing here has been replayed or backtested, and there are **no performance results** of any kind. No parameter is calibrated. Do not trade it live.

## Files

| File | What it is |
|---|---|
| `MEKA_ALPHA_PRO_4_INDICATOR.pine` | Standalone Pine v6 indicator: signals, dashboard, alerts, and a **simulated** position (assumed fills, no costs). |
| `MEKA_ALPHA_PRO_4_STRATEGY.pine` | Standalone Pine v6 strategy: identical signal engine, with TradingView's broker emulator as the execution record. |
| `MEKA_ALPHA_PRO_v3_AUDIT.md` | Static audit of v3, re-verified, with one correction (A17) and three added notes. |
| `MEKA_ALPHA_PRO_4_VALIDATION.md` | What was actually checked, what was not, and the test matrix to run in TradingView. |
| `CHANGELOG.md` | r1 → r2 review findings and fixes. |
| `src/`, `tools/` | Sources the two `.pine` files are generated from; build, parse and test scripts. |
| `reference/r1/` | The supplied r1 files, unchanged, for diffing. |

The two `.pine` files are complete and copy-paste ready. Each is standalone and needs no library. If you change logic, edit `src/*.pine`, then run `python3 tools/build.py`. The build refuses to produce files whose shared blocks differ.

## Setup in TradingView

1. Open the **exact feed and contract** you want to research on **standard candles** with a **minute timeframe**: 1–5 min for Scalp, 5–15 min for Day Trade (starting hypotheses, not recommendations). Heikin Ashi, Renko, range, seconds and daily charts stop with a runtime error.
2. Pine Editor → new script → paste the **whole** indicator file → Save → Add to chart. Repeat separately for the strategy. Record any compiler error with its line number. The build has not been through TradingView's compiler, so errors are possible.
3. Check the dashboard row **Tick / USD per unit / step**. If the family shows `Unknown`, choose it under *Market family*. If the USD per unit shows `UNKNOWN`, set *USD per 1.0 price move per order unit*.
4. Strategy only: open **Properties** and set initial capital, order size handling, **commission**, **slippage**, **margin**, and **Bar Magnifier** (premium plans) to your venue's values. The declared defaults ($2.50 per unit per fill, 1 tick, 100% margin) are placeholders. In particular:
   - $2.50 *per unit* is wrong for spot FX or CFD unit sizing (50,000 EURUSD units would be charged $125,000 per fill). Use a percent or per-order commission there.
   - 100% margin with $10,000 capital **rejects every full-size futures order** (ES notional ≫ $10k). Rejected orders show as `NO FILL` events, not as trades. Set margin deliberately and write down what you used.
5. Set *Sizing reference balance* and *Planned initial risk %*. Sizing does not compound with strategy equity.
6. Set mode, framework, windows, news events and evaluation dates. Warm-up history before *Entry evaluation start* is used for indicators but never for entries.

## Market families and sizing

| Family | Auto-detected by | Sizing source (when override = 0) | Notes |
|---|---|---|---|
| Gold | root `GC`/`MGC`, base `XAU`, or ticker `GOLD`/`XAUUSD`/`GOLDUSD` (e.g. `TVC:GOLD`, `OANDA:XAUUSD`) | USD quote → `syminfo.pointvalue` | Full vs micro differ 10× in point value and fees; broker XAUUSD unit = 1 oz or 100 oz depending on feed. |
| Nasdaq | root `NQ`/`MNQ`, or ticker `NAS100`/`US100`/`USTEC` | pointvalue | Whole contracts. Same signal ≠ same dollar risk. |
| S&P | root `ES`/`MES`, or ticker `SPX500`/`US500` | pointvalue | Whole contracts; small R targets suffer cost drag. |
| EURUSD | root `6E`/`M6E`, or EUR/USD currencies | pointvalue | Spot "unit" means 1 EUR; set *quantity step* to your lot step (e.g. 1000). |
| JPY | root `6J`, or USD/JPY currencies | USDJPY: `pointvalue / close`; 6J (USD-quoted): pointvalue | See orientation below. |
| anything else | — | **blocked** | Choose a family *and* check the unit value. |

**Orientation (6J vs USDJPY).** All signals and orders use the chart's **native** direction; nothing is ever inverted for trading. 6J is quoted in USD per JPY, so a 6J LONG is long JPY / short USD, the opposite of a USDJPY LONG. The dashboard prints the USDJPY-equivalent next to the side (for example, `LONG = long JPY (USDJPY-equiv SHORT)`). Reciprocal OHLC is not constructed anywhere. If you ever map an external USDJPY bias onto 6J, invert that bias exactly once, and remember that futures basis means 1/spot ≠ 6J.

**USD conversion.** The USDJPY sizing value `pointvalue / close` uses the bar's own rate, so it is exact for that bar at that rate. Other non-USD quotes need a manual value, which is a fixed approximation. TradingView's strategy P&L uses its own symbol metadata and FX conversion. The override changes *size*, not the P&L engine, so reconcile both.

## Signal model (exact rules)

**Trend gate:** the previous **completed** higher-timeframe close is above (below) its EMA50, that EMA is rising (falling) bar over bar, and chart EMA20 > EMA50 (<). The HTF data is `request.security(..., [close[1], ema[1], ema[2]], lookahead_on)`, the documented non-repainting pattern. The HTF must be strictly greater than the chart timeframe or the script stops.

**Quality gate:** ATR(14) ≥ *min ATR ticks* × tick, ADX(14) ≥ *min ADX*, |close − EMA20| ≤ *max extension* × ATR, and the optional volume filter (missing volume **blocks**).

**Structure:** `ta.pivothigh/low(strength, strength)`. A pivot becomes usable on its confirmation bar (origin + strength), never earlier. New pivots are committed **after** the bar's ICC logic runs, so a bar cannot break a pivot that only became known on that same bar.

**ICC (indication → correction → continuation).** This is a transparent research hypothesis, not an established edge.

| Stage | Bar | Condition (long; short mirrors) | Frozen at this stage |
|---|---|---|---|
| INDICATED | *i* | close > swingHigh + buf, previous close ≤ swingHigh + buf, close − open ≥ *displace* × ATR[1], trend long, entry + quality gates pass, and this pivot not yet consumed | side, broken level *L*, indication ATR *A* = ATR[1], invalidation = low − pad × ATR[1], consumed pivot ID, setup ID |
| CORRECTED | *j > i* | low ≤ *L* + *retest* × *A* and high ≥ *L* − *retest* × *A* and close ≥ *L* − *retest* × *A* | trigger = this bar's high; correction low/high |
| continuation (ENTER candidate) | *k > j* | close > trigger + buf and close > open | stop = min(all correction lows incl. bar *k*) − pad × *A* |

The setup is cancelled (and its end reason shown) by: trend loss, low ≤ invalidation, *k − i* > expiry, leaving every enabled window, news/exclusion, emergency block, or the force-flat window. A non-qualifying bar in the CORRECTED state widens the correction extremes. The trigger never moves. One setup yields at most one candidate, and the candidate is consumed even when a later gate rejects it.

**Trend pullback:** close crosses above EMA20, the previous bar's low touched EMA20, the bar is bullish, and trend is long. Stop = min(low, low[1]) − pad × ATR[1]. **Either** = ICC first; pullback only while no ICC setup is in progress. At most one candidate per bar.

**Candidate validation (all on the closed signal bar):** stop rounded away from price to a tick; planned risk = |close − stop| must be within [min stop × ATR, max stop × ATR], **otherwise reject (never clip)**; room: if the latest opposing pivot lies ahead, its distance must be ≥ TP1 R × risk + 1 tick; quantity ≥ 1 step.

**No score.** Setup scores were deliberately dropped. Nothing is labelled confidence or probability.

## Research presets (UNVALIDATED starting values)

| Parameter | Scalp | Day Trade | Unit | Rationale |
|---|---:|---:|---|---|
| Trend timeframe | 15 | 60 | minutes | Clearly above typical chart TF |
| Pivot strength | 3 | 5 | bars each side | Confirmation delay = strength bars |
| ICC expiry | 12 | 24 | bars from indication | ~1–2 hours on suggested charts |
| Max hold | 20 | 48 | bars from fill | Intraday intent |
| Cooldown | 2 | 3 | full bars after exit | Prevents instant re-entry |
| Stop distance | 0.5–2.5 | 0.6–3.0 | ATR(14) | Reject outside |
| Min ADX / ATR | 18 / 4 | 18 / 4 | ADX pts / ticks | Shared baseline |
| Displacement / retest | 0.6 / 0.25 | 0.6 / 0.25 | ATR | Shared baseline |
| Targets | 1R, 2R (opt. 3R) | same | planned R | 50/50 or 40/30/30 |

Calibrate per **feed × family × session × mode**, chronologically (see Validation). Keep the common baseline to detect overfitting. Measurement priorities: gold spot-vs-futures spreads and spikes; NQ/MNQ cost per tick; ES/MES small-target cost drag; EURUSD/6E volume semantics and lot units; USDJPY/6J orientation and conversion.

## Entry windows, trading day and news

- **Windows:** Tokyo 09:00–15:00 `Asia/Tokyo`, London 08:00–12:00 `Europe/London`, New York 08:30–12:00 `America/New_York`. All are editable, each with its own IANA zone, plus a weekday mask (default Mon–Fri, `23456`, 1 = Sunday). These are **research entry windows, not exchange hours**. TradingView applies each zone's own DST, so the 2–3 weeks a year when US and UK clocks differ are handled per window (the Python port of the formula was tested on March, October and November 2026 dates).
- **Whole-bar rule:** a signal bar must lie entirely inside a window (local open ≥ start, local close ≤ end, same local day). Bars crossing a boundary are not entry bars. Overlapping windows form one union gate, so each setup produces one entry at most.
- **Latest-entry cutoff:** a signal is rejected if its bar closes less than *cutoff* minutes before the window end (default 5), so the next-tick fill normally lands inside. After data gaps or halts the fill can still land outside the window or after a news boundary. That is disclosed, not prevented.
- **Holding:** windows gate entries only; protective orders always stay active. Optional *exit when outside every window* and optional *force-flat window* (in the trading-day zone) request a market exit at the close of the first qualifying bar, filling at the next tick. They are not exact flatten-at-time guarantees, and a missing bar delays them.
- **Trading day:** counters (daily R, entries, loss streak) reset at *reset time* in *trading-day timezone* (default 17:00 New York, the CME roll). They never reset at midnight and never touch an open position. Holidays, half-days and maintenance breaks are **not** modelled; the weekday mask is not an exchange calendar.
- **News:** up to three manual event timestamps with before/after minutes, plus one recurring daily exclusion with its own zone, plus an emergency block. They block **new** setups and entries on any bar that intersects them; protective orders stay active. There is **no calendar feed**; Pine has no complete economic-news calendar, and `request.economic` is not one. An intent already queued at a bar close can still fill inside a blackout after a gap.

## Execution contract

**Strategy (emulator is the record).** `calc_on_every_tick=false`, `calc_on_order_fills=false`, `process_orders_on_close=false`, `pyramiding=0`, no reversals.

1. On the signal-bar close the strategy sends a market `ENTRY` **and** every tranche's `strategy.exit` (fixed absolute stop + limit) in the same calculation. The first fill is therefore protected from its first tick, with no unprotected bar.
2. Planned R and size come from the signal close. A gap changes the real risk; the fill-risk ratio (fill risk ÷ planned risk) is shown. **Gap policy:** if the ratio exceeds *N* (default 1.5), a market exit is requested at the fill-bar close (next tick). The bracket stays live meanwhile. A fill beyond the stop is stopped by the emulator straight away.
3. `calc_on_order_fills` stays **off**. Recalculating on historical fills runs the script with the fill bar's completed OHLC, which can make history look better than live. Pre-submitted brackets remove the need for it.
4. Tranche orders `TP1`, `TP2`, `FINAL` each reserve their own quantity, and the three sum to the entry. Inside each `strategy.exit` the stop and limit are OCA-reduce. A stop hit closes every tranche at the same stop. TP flags and P&L come from `strategy.closedtrades` (exit ID and comment), so they are execution evidence, not touch tests.
5. Break-even and trailing turn on once a **close** has seen the TP1 *level* traded through (the same rule in both scripts, and it also works for 1-unit positions that have no TP1 tranche). The new stop is sent after that close and is never applied to earlier prices. BE = actual fill price; after costs it can still lose.
6. Time, window, force-flat, test-end and gap exits use `strategy.close` at a close and fill at the next tick, with brackets still active.
7. If the entry is not filled by the next bar's close (margin, capital, quantity), the intent is dropped with `NO FILL`, orders are cancelled, and cooldown applies. It is not counted as a trade.
8. Daily R uses `strategy.closedtrades.profit` summed over the position ÷ planned cash risk. Verify in your TradingView version whether that field is net of commission.

**Indicator (simulation; no fills exist).**
- ENTER is an **intent**. Its modeled fill is the **next bar's open** and is labelled `ASSUMED_SIMULATION`.
- From the fill bar onward each bar is judged from its open. **Stop-first:** if a bar touched both the stop and a target, the stop wins and the bar is counted as *ambiguous* (dashboard). Stop gaps fill at the worse open; target gaps at the better open.
- No pre-entry price is ever credited. The signal bar's own range is never tested.
- Results are **gross R, no costs**, used only for the trading-day gates. This is not a performance ledger.
- Expect the indicator and the strategy to diverge on ambiguous bars, with Bar Magnifier, on rejected orders, and with costs. Their **raw signals** cannot diverge, because the engine is byte-identical. Their accepted entries can, because position state and cooldowns follow different fills.

**Tranches.** 2 targets: 50/50. 3 targets: 40/30/30. Units are rounded down per tranche and the residual goes to the final target. Fewer than 2 units (or 3 with TP3) → **one tranche at the final target**; TP1 shows `skip`. Futures always step 1 contract, so a fractional contract cannot occur.

## Dashboard

Compact by default; enable *Full dashboard* for all 14 rows; position and text size are inputs. Main cell: **WAIT / ENTER / HOLD / TP / EXIT**. Each event status lasts exactly its event bar. Priority on a bar with several events: EXIT > TP > ENTER > HOLD > WAIT. A queued intent shows WAIT with the secondary text "Intent queued", never HOLD. Other rows: family/mode/framework; side (+ USDJPY-equivalent for JPY); active windows + detail or the one blocking reason; ICC setup state and last end reason; reference vs fill and fill-risk ratio; initial/current stop; targets (`done`/`skip`); initial/remaining units + FLAT/PENDING/OPEN/PARTIAL/COOLDOWN; trading-day R, entries, streak and active block; execution basis (simulation with the ambiguous-bar count, or emulator); news/block coverage; tick, USD per unit and its source, quantity step; volume status; last four events (all events of a bar are kept together).

## Alerts

| Script | How | Event types |
|---|---|---|
| Indicator | *Any alert() function call* (JSON) or the `alertcondition`s | `SIGNAL_INTENT_NOT_FILL`, `SIM_FILL`, `SIM_TP`, `SIM_EXIT` |
| Strategy | *Order fills and alert() function calls* | emulator order-fill alerts, plus `SIGNAL_INTENT_NOT_FILL` and `EMULATOR_*_OBSERVED` from `alert()` at the close where the script saw them |

Each JSON payload has `version`, `event`, `event_id` (= trade ID : event : bar-close ms), `detail`, `fill_basis` (`SIGNAL_CLOSE_REFERENCE` / `ASSUMED_SIMULATION` / `TV_EMULATOR`), `trade_id`, `setup_id`, `ticker`, `timeframe`, `native_side`, `bar_close_ms`, `price`, `qty`, `stop`, `tp1`–`tp3` (`null` when unknown). Deduplicate on `event_id`. Alerts fire once per bar close, never repeatedly while HOLD.

Suggested strategy order-fill message:

```json
{"source":"MEKA4_EMULATOR","trade_id":"{{strategy.order.alert_message}}","order_id":"{{strategy.order.id}}","action":"{{strategy.order.action}}","price":"{{strategy.order.price}}","contracts":"{{strategy.order.contracts}}","comment":"{{strategy.order.comment}}","ticker":"{{ticker}}","time":"{{timenow}}"}
```

Timing: stop/limit fills alert when the emulator fills them, intrabar in real time. Close-based decisions (intent, time exit request, observed events) alert at the bar close. An order-fill alert is an **emulator** fill, not a broker acknowledgment. **Re-create alerts after any code or input change**, because alerts keep a snapshot. No webhook bridge or broker integration is included.

## Validation before reading any number

Follow `MEKA_ALPHA_PRO_4_VALIDATION.md`. In short:

- Compile both files.
- Run the deterministic replay cases.
- Compare the Data Window outputs *Raw candidate*, *Raw eligible candidate direction* and *ICC setup state* bar by bar between the two scripts.
- Reconcile at least 10 trades by hand.
- Only then look at statistics, and only as complete-position results under chronological train / validation / test folds with an untouched holdout, cost stress at 1×, 1.5× and 2×, and a comparison against the simpler trend-pullback baseline.

## Known limitations

- Not compiled, replayed or backtested by the author.
- No calibrated parameters.
- Latest opposing pivot only for the room check.
- No exchange calendar.
- No live news feed.
- Fixed (non-compounding) sizing balance.
- Non-USD quotes other than USD-base need a fixed manual conversion.
- Spread is not modelled separately: put half-spread + slippage into the Properties slippage ticks and do not also add it to commission.
- One symbol per chart; no portfolio test.
- Continuous-futures roll adjustments change historical prices; test the actual contracts too.
- v3's EMA200/VWAP/FVG overlays, watch labels, five-target ladder, alternative resting entry types and scoring were evaluated and left out. They either had defects (A10/A11/A17) or had no execution model behind them. Restore one only with its own test.

References: [strategies](https://www.tradingview.com/pine-script-docs/concepts/strategies/), [repainting](https://www.tradingview.com/pine-script-docs/concepts/repainting/), [other timeframes](https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/), [sessions](https://www.tradingview.com/pine-script-docs/concepts/sessions/), [time](https://www.tradingview.com/pine-script-docs/concepts/time/), [alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/), [CME JPY specs](https://www.cmegroup.com/markets/fx/g10/japanese-yen/specs).
