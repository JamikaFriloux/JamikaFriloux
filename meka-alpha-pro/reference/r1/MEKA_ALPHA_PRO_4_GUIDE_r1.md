# MEKA ALPHA PRO 4.0-r1 — research build guide

## What is ready

The full v3 static audit, Claude engineering brief, and two standalone Pine v6 research files are supplied. **Neither Pine file has been compiled in TradingView, replayed, or backtested.** No claim of profitability, optimal settings, or production readiness is made. The code is a concrete starting point for that work.

The rebuild retains v3's useful ideas—confirmed higher-timeframe trend, pivots, ATR risk, selective filters, and a chart dashboard—and replaces its order/target simulation. It is not a line-by-line v3 patch. Read the audit before assuming v3 signals or visual overlays will match.

## Files

- `MEKA_ALPHA_PRO_4_Claude_Brief.md`: copy-paste engineering brief, updated with actual v3 findings and research-build limitations.
- `MEKA_ALPHA_PRO_v3_SOURCE.pine`: unchanged uploaded source with stable audit line numbers.
- `MEKA_ALPHA_PRO_v3_AUDIT.md`: full static audit with 18 findings and correctly implemented behavior.
- `MEKA_ALPHA_PRO_4_INDICATOR.pine`: chart signals and explicitly labeled position simulation.
- `MEKA_ALPHA_PRO_4_STRATEGY.pine`: the same raw signal engine with TradingView order simulation and partial exits.
- `MEKA_ALPHA_PRO_4_VALIDATION.md`: checks performed and required TradingView/empirical checks.

For Claude: upload these files together and paste the brief. The complete ZIP is a convenient archive; if Claude cannot inspect ZIP files, extract and upload the individual files.

## Setup in TradingView

1. Use standard time-based candles on the exact feed/contract you intend to research. Start with a 1–5 minute chart for Scalp or 5–15 minute chart for Day Trade. These are research starting points.
2. Paste one complete `.pine` file into Pine Editor, save and compile. Record any errors with their line numbers. Add the indicator and strategy separately; do not paste them into one script.
3. Select the market family if Auto shows Unknown. Verify tick size, symbol point value, quote currency, actual contract and quantity increment.
4. For strategy tests, configure initial capital, margin, commission and slippage in Properties. The declaration uses illustrative **$2.50 per order unit per fill, one tick slippage, and 100% margin**. These are not calibrated costs. In particular, $2.50 per spot currency unit is unsuitable for EURUSD unit sizing; change the commission type/value before interpreting any result. Full-notional margin can reject futures entries at the default $10,000 capital. Set the testing margin/capital deliberately and record it; do not interpret zero trades as proof that no signals occurred.
5. Set the fixed USD sizing reference balance to the intended research balance. It does not automatically compound with strategy equity or follow the Properties initial capital setting. Defaults: $10,000 and 0.5% planned initial risk, subject to unit rounding and cap.
6. Set evaluation dates, sessions, mode and framework. The selected trend timeframe must exceed the chart timeframe. Invalid ordering/settings fail explicitly. Wait for sufficient HTF/EMA history.
7. Run the validation matrix before using alerts. Use paper trading for forward observation; the scripts themselves do not place broker orders.

## Market families and sizing

| Family | Auto recognition | Execution considerations |
|---|---|---|
| Gold | GC/MGC root or XAU base currency | Verify full/micro point value and broker XAUUSD order units |
| Nasdaq | NQ/MNQ root | Native prices, integer futures contracts; full/micro costs differ |
| S&P | ES/MES root | Native prices, integer futures contracts; same signal settings do not imply same dollar risk |
| EURUSD | 6E root or EUR/USD currencies | Spot units/lot step differ from futures; change default strategy costs |
| JPY | 6J root or USD/JPY currencies | 6J LONG means JPY strength; USDJPY LONG means USD strength |

Profiles identify families and explain direction; **they do not supply statistically calibrated per-market parameters**. Unknown families block entries until manually selected. With a USD-quoted symbol, zero in “USD per 1.0 price move per order unit” uses `syminfo.pointvalue`. Non-USD quotes require an explicit positive override; USDJPY therefore blocks entries until configured. For spot FX, define what one order unit means on the selected feed. A USDJPY spot unit's approximate USD risk value per one-yen price change depends on the exchange rate; a fixed override is an approximation and must be updated or replaced by tested conversion logic. Do not reuse it over a long backtest without investigating distortion.

The override sizes the order; it does not rewrite TradingView's P&L engine. Reconcile strategy trade P&L with your selected feed metadata. Futures always use quantity step 1. Other symbols use the specified step. A manually selected family does not validate your broker metadata.

## Exact signal model

Trend requires the previous completed higher-timeframe close above/below its 50 EMA, the previous completed EMA rising/falling, and chart EMA20 above/below EMA50. ATR must meet the tick minimum, ADX the threshold, price not be excessively extended, and required volume be available. Volume filtering is off by default because feeds differ; when enabled, missing volume blocks signals.

ICC is an explicit research definition of indication → correction → continuation:

1. A closed candle breaks an already-available pivot by a tick, with directional body at least 0.6 prior ATR. Save broken level, indication ATR, indication candle extreme plus padding as invalidation, and the consumed pivot ID.
2. On a later candle, range overlaps the ±0.25 indication-ATR retest band and closes on the allowed side. Save correction extremes and its high (long) or low (short) as the fixed continuation trigger.
3. On another later candle, a directional close breaks the saved trigger by a tick. The stop uses accumulated correction extremes from earlier correction candles, padded by the frozen indication ATR. Reject too-close/far stops; do not clip them inside structure.

Trend loss, original invalidation, timeout, leaving all enabled windows, news blackout or manual entry block cancels the ICC setup. A consumed pivot cannot initiate another indication. The continuation candidate is consumed even if a risk/session gate later rejects it.

Trend pullback uses a close crossing EMA20 in the trend direction, after the prior bar touched the EMA, plus a directional candle; the stop is outside the current/prior pullback extremes. “Either” permits that simpler setup while no ICC sequence is active, with ICC priority. It is not an independent parallel ensemble.

Newly confirmed pivots are committed after ICC detection. They cannot initiate a breakout before they were known. The room check uses the latest opposing pivot only, not all historical support/resistance. No heuristic score is included in r1; there is no probability display.

## Research presets and calibration plan

| Parameter | Scalp | Day Trade | Interpretation |
|---|---:|---:|---|
| Trend timeframe | 15 minutes | 60 minutes | Confirmed context, must exceed chart |
| Pivot left/right strength | 3 / 3 | 5 / 5 | Confirmation delay in chart bars |
| ICC expiry | 12 bars | 24 bars | From indication |
| Maximum hold | 20 bars | 48 bars | Exit request after this duration |
| ADX / ATR ticks | 18 / 4 | 18 / 4 | Shared unvalidated baseline |
| Stop range | 0.6–3 ATR | 0.6–3 ATR | Reject outside interval |
| Target R | 1 / 2 (optional 3) | 1 / 2 (optional 3) | Based on signal-close planned risk |

Calibrate actual feed + market + session + mode separately. Gold: inspect volatility spikes and spot/futures spread differences. NQ/MNQ: inspect large point moves, ticks and micro costs. ES/MES: examine small-target cost drag. EURUSD/6E: verify volume semantics and quote units. USDJPY/6J: verify orientation, USD risk conversion and feed differences. These are measurement priorities, not proven parameter advantages. Preserve a simple common baseline to detect overfitting.

## Sessions, dates and news

Three independently enabled local windows: Tokyo 09:00–15:00 (`Asia/Tokyo`), London 08:00–12:00 (`Europe/London`), New York 08:30–12:00 (`America/New_York`). They use weekday masks and IANA zones. These are research entry windows, not exchange calendars. Overlaps produce one combined gate. A whole chart bar must fit a local window; session-fragment bars are rejected. Sunday futures trading, holiday calendars and early closes are not modeled by these weekday windows.

Entry windows gate the **signal**, not the guaranteed time of a subsequent market fill. A last-window signal or data gap can fill outside the window or after a news boundary. Protective brackets remain active. “Request exit outside all enabled windows” is off by default, so holding outside windows is allowed until stop/target/time exit. When enabled, it requests a market exit at the close of the first out-of-window bar, for the next tick; it is not an exact session-end flatten guarantee.

Manual news coverage is one timestamp and editable before/after minutes. It has no calendar connection and cannot detect unscheduled news. The dashboard always states its limited coverage. New setups are blocked for bars intersecting the blackout. Existing protective orders remain. Existing market intent cannot reliably be recalled before a gap fill.

Dates gate entries while prior bars supply indicator warm-up. At/end after the evaluation endpoint, an open position receives a next-tick close request. A missing subsequent bar can leave it open in the test. No training/optimization occurs inside the script; walk-forward runs are manual and must preserve dated parameter records.

## Orders, stops and partials

An ENTER event is a closed-bar signal and market-order intent. The strategy queues a market entry and all fixed absolute bracket orders together. Default engine settings avoid tick recalculation, fill recalculation and same-close fills. Planned R is signal close minus the frozen stop distance; targets stay tied to that reference, even if the actual fill gaps. Actual risk can exceed planned risk, and a gap can put a bracket beyond the fill. This build makes no promise to cancel an order after observing a future open. Inspect such trades explicitly in TradingView.

The indicator assumes the next available bar's open and then evaluates that bar. Unlike v3's resting-order model, its simulated position exists at the start of the fill bar; no pre-open range is credited. A touched stop takes precedence over targets; simultaneous stop/target ranges increment an ambiguity counter. Stop gaps use the adverse open. This conservative convention can differ from the strategy emulator's path or Bar Magnifier results. The indicator does not calculate returns or fees.

Two targets allocate 50%/50% subject to quantity increments. Three targets allocate approximately 40%/30%/30%, rounding units down and putting the residual in the final tranche. Fewer than two units for two targets, or fewer than three for three targets, becomes **one final-target tranche**. Thus a one-contract trade uses TP2 (or TP3 when enabled), with TP1 skipped. No fractional futures exits are invented. Initial and remaining quantity are separate; moving a stop never increases the order size.

Break-even is off by default. If enabled, after a profitable TP1 is observed at bar close, remaining stops tighten to actual modeled entry. The updated stop applies on subsequent ticks; a prior dip below entry on the TP1 candle does not retroactively stop the trade. Entry-price exits can still lose money after costs. Trailing stops are not implemented in r1.

Time exits queue at close and fill next tick, with protection retained. Cooldown waits the configured full bars and prevents same-bar re-entry even at zero. Strategy no-fill recovery marks EXIT with “NO FILL” if a submitted market intent is absent at the next bar close (for example due to margin); it does not count that as a profitable/loss-making trade. Inspect the emulator ledger for actual trades.

## Dashboard and alerts

WAIT = no entry intent/open modeled position; ENTER = new intent; HOLD = modeled position; TP = partial/final target event; EXIT = final closure or no-fill recovery. EXIT takes priority over TP. Event text lasts the event bar; pending intent is secondary text. Quotes, initial/remaining units, manual news coverage and uncalibrated status are visible. Some analytical fields can update intrabar; trade transitions require bar confirmation.

Indicator alerts: choose ENTER intent, simulated TP/EXIT conditions, or “Any alert() function call” for richer JSON messages. Simulation events are not broker instructions. Signal JSON includes symbol, timeframe, native side, bar-close timestamp, trade ID, reference entry, planned levels and initial units. Simulation-event messages include event details and remaining units. For small positions, a listed TP1 level can have zero allocated quantity; read the dashboard/tranche rules. Build event deduplication from trade ID + event type + timestamp.

Strategy alerts: select order fills, optionally with alert() calls. A usable custom order-fill message template is:

```json
{"source":"MEKA4_EMULATOR","trade_id":"{{strategy.order.alert_message}}","order_id":"{{strategy.order.id}}","action":"{{strategy.order.action}}","price":"{{strategy.order.price}}","contracts":"{{strategy.order.contracts}}","comment":"{{strategy.order.comment}}","symbol":"{{ticker}}","time":"{{timenow}}"}
```

Order-fill alerts describe TradingView emulator fills, not brokerage acknowledgments. Entry intent and fill messages are separate. Partial orders have stable IDs. Recreate alerts after source/settings changes; saved alerts use snapshots. No webhook/broker integration is included.

## Validation before interpreting results

Compile both scripts first. Use identical inputs and compare “Raw eligible candidate direction” in the Data Window: the shared signal engine should match. Accepted entries can diverge later because indicator stop-first exits and emulator fills produce different busy/cooldown states. This is not a promise of identical trade ledgers.

Use actual-contract as well as continuous-futures data, and record roll adjustment choices. Test costs at measured baseline, 1.5× and 2×; spread is not separately implemented, so use a documented approximation without double counting. Configure limit fill verification/Bar Magnifier explicitly and record settings. Reconcile whole-position results from partial trades rather than trusting a tranche-based win rate as position win rate.

Use chronological train/validation/test folds and an untouched final holdout. Example starting schedule: 12 months training, 3 validation, 3 out-of-sample, rolling forward when data suffices. Freeze parameters before each test. Retain warm-up history, specify positions crossing folds, and compare trend-only versus ICC under identical assumptions. Report net expectancy, drawdown, trade count, cost sensitivity and performance by fold/market/session/direction. No win rate has been measured for these files.

## Remaining release work

TradingView compilation/replay; data-feed validation; empirical market calibration; broader manual/external news scheduling; dynamic FX/account conversion; daily loss/max-entry gates; optional trailing; aggregate whole-position performance export; exact session-close policies; automated walk-forward analysis; and external execution integration remain future work. Original v3 VWAP/EMA200, FVG, scoring/grade panels, watch labels and resting entry modes are not retained in this research baseline. The Claude brief specifies the fuller intended release.

Official implementation references: [TradingView strategies](https://www.tradingview.com/pine-script-docs/concepts/strategies/), [repainting](https://www.tradingview.com/pine-script-docs/concepts/repainting/), [time](https://www.tradingview.com/pine-script-docs/concepts/time/), and [alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/).
