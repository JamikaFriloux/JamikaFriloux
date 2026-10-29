# Changelog

## 4.0.1 — October 29, 2026 (execution accuracy + chart experience)

Kept: ICC hybrid, market presets, session intelligence, Scalp / Day modes, two-target system. **No trading parameter was changed** in response to the user's 10-trade Gold sample.

### Execution audit: findings and corrections

| # | Problem in 4.0 | Why it mattered | Correction |
|---|---|---|---|
| E1 | Break-even and trailing started when TP1 was **touched**, in **both** scripts. The touch could be on the candle where a limit entry filled *inside* the candle, so the touch may have happened **before** the entry existed. | A stop could move to break-even off a price the position never saw. That changes later exits and results. | They now start only after the **TP1 tranche is filled** (indicator: simulated fill; strategy: emulator fill read from the trade list). A position too small to have a TP1 tranche uses a TP1 touch, but only one that *certainly* happened while it was open: the position existed from the candle's open and survived the candle. |
| E2 | The strategy declares that limit orders must **trade through by 1 tick** (`backtest_fill_limits_assumption=1`), which applies to profit-target limits as well as entries. The indicator credited targets on an exact touch. | The indicator booked target fills that the strategy never received, so it looked better than the strategy. | Indicator targets now fill only when the reachable price trades through by *fillTicks* (default 1), or when the candle opens beyond the target. Exact touches show as **touched, not filled**. |
| E3 | On a candle that hit both the stop and a target, the indicator always assumed the stop came first. TradingView's emulator assumes the extreme nearer the open is visited first. | The two scripts disagreed on those candles, with no way to check parity. | New input *Indicator: stop and target in the same candle*. **Stop first (conservative)** stays the default. **Match TradingView emulator** reproduces the emulator path, so the indicator can be checked trade by trade against the strategy. |
| E4 | On a candle where a limit entry filled inside the candle, the indicator ignored targets correctly, but recorded touches from the whole candle. The strategy counted the same uncertain touches. | Inflated "touched" statistics; it fed E1. | Touches count only when the position certainly existed at that moment. In emulator mode an intrabar fill credits only what the emulator path visits after the fill. |
| E5 | TP alerts reported the target price, not the actual fill price (a gap open beyond the target fills at the open). | Alert prices could be wrong on gap fills. | Alerts and messages use the actual fill price in both scripts. |

Checked and found consistent (no change needed): next-open market fills; gap fills through stops (worse open) and targets (better open); stop orders trigger at a touch; limit-entry trade-through and expiry; one cancel path for expired limits and rejected market orders; exits requested at a close fill at the next open with brackets still live; cost model identical in both scripts; same-candle re-entry blocked.

**Known, documented remaining difference:** for a limit entry filled inside a candle, the emulator can fill a target later in that candle in cases the conservative indicator mode defers. Use emulator mode when checking parity.

### Chart experience

- Performance table **OFF by default**. Session levels and opening ranges are off by default too.
- **Hierarchy:**
  - Context (EMAs, VWAP, session levels, zones, structure) is faint and thin, so candles stay readable.
  - The **entry line (bold) and stop line (thicker, red)** are prominent, with shaded risk (red) and reward (green) areas.
  - Targets are dashed green with solid price tags; a filled target turns dotted, with ✓.
  - The actual fill replaces the reference price once known.
  - When the stop moves, the old segment fades and a new one starts.
- **Detailed view:** BOS / CHoCH drawn on the candle that closed through the level, small labels, capped to the last N marks (default 12). Sweeps are small lowercase marks. Only the last 3 ICC zones are kept. Finished trades fade; Clean view removes them.
- **Dashboard** order: status, then **NEXT** (the instruction, largest text), then **MISSING / NOTE / WHY** (the explanation), then the trade levels. Background (bias, setup, session, filters, mode) comes last, smaller and muted, in Detailed view.

### Validation tooling

- Performance table: three periods (**Development / Validation / Holdout**) with two dates; long and short split by session; a 95% Wilson range on every win rate; a **settings fingerprint** so you can show the holdout was evaluated with frozen settings.
- New `MEKA_ALPHA_PRO_4_TESTING_PLAN.md`: execution check first, then ICC vs both baselines per market / mode / timeframe / session / direction, with honest labels and a results log.
- Reference model updated to the corrected rules; **42 tests** (6 new execution-correction tests).

## 4.0 — October 29, 2026 (new development requirements)

Rebuilt on the 4.0-r2.1 code following the user's new 4.0 specification, which takes priority over earlier design decisions.

**Gap audit of 4.0-r2.1 against the new specification (highest priority first)**

1. No WATCH / NO TRADE / TAKE PROFIT states and no "next action". The dashboard used internal codes, IDs and timestamps.
2. No CHoCH, liquidity sweeps, VWAP, session highs/lows or opening ranges. Bias used a single higher timeframe (no 1H + 4H for DAY).
3. Identical thresholds for every market.
4. Allocations hard-coded; no ATR stop, structure trail or early invalidation exit; no touched-vs-filled distinction.
5. No pending limit entries, so no "pending entry filled / canceled" events. The indicator simulation ignored costs.
6. No in-script statistics (win rate, PF, expectancy, drawdown) by session/regime, no in/out-of-sample split, no breakout baseline.
7. No Clean/Detailed views and no BOS/CHoCH, sweep or zone drawings.
8. Found during implementation: the Gold preset would have required VWAP on TVC:GOLD, which has no volume, so every entry would have been blocked.

**Implemented**

- **States and dashboard:** WAIT, WATCH LONG/SHORT, ENTER LONG/SHORT, HOLD, TAKE PROFIT, EXIT, NO TRADE. Premium dashboard in plain English (next step + what is missing). Clean and Detailed layouts, position and text size. No IDs, timestamps or programming terms.
- **Market presets** (Gold, Nasdaq-100, S&P 500, EUR/USD, USD/JPY) per mode: confirmation timeframes, swing strength, break-candle body, ADX, ATR % minimum, stop range and buffer, extension limit, VWAP/volume filters, sessions, illustrative costs. Custom thresholds group for every value.
- **Two confirmation timeframes:** 15m + 1H for Scalp, 1H + 4H for Day. Both use confirmed-candle `request.security` with `[1]` + `lookahead_on`.
- **Structure engine:** confirmed swings, BOS vs CHoCH (each swing broken once), liquidity sweeps of swings and previous session highs/lows.
- **ICC:**
  - Correction = retracement 38.2–78.6% of the impulse and/or broken-level retest.
  - Invalidation = close beyond the impulse origin.
  - Trigger = high/low of the deepest pullback candle.
  - Optional VWAP side, volume and required sweep.
- **Sessions:** Asia/London/New York tracking (IANA zones) of highs, lows and opening ranges. Market-specific entry windows and full-session hours (FX/gold NY 08:00–17:00 vs index cash 09:30–16:00).
- **Baselines:** trend pullback and opening-range breakout with identical execution and costs.
- **Management:**
  - Structure / ATR / wider stop.
  - Configurable 2- and 3-target allocations (50/50, 50/30/20).
  - Optional BE (default off, to be tested), ATR or swing trail after TP1.
  - Early exits on structure break or bias flip; max hold; gap-risk exit.
- **Execution:** market-at-next-open or limit-at-retest entries with trade-through fills, expiry and cancel events. Conservative intrabar rules in the indicator. Modeled commission, spread and slippage in both scripts. Strategy declares `backtest_fill_limits_assumption=1`.
- **Measurement:** performance table by all/long/short/session/trend regime/volatility regime/in-sample/out-of-sample, with targets touched vs filled and stop-first counts.
- **Alerts:** JSON for SETUP_FORMING, LONG/SHORT_ENTRY_CONFIRMED, ENTRY_FILLED, TP1/2/3_REACHED, STOP_HIT, EARLY_EXIT and SETUP_CANCELED, each with a human `message` for Telegram, plus named `alertcondition`s in the indicator.
- **Feed-aware filters:** VWAP/volume presets only switch on when the feed reports volume; the dashboard says so.
- **Tests:** reference model rewritten for the 4.0 rules; 36 tests.

## 4.0-r2.1 — October 29, 2026 (first TradingView feedback)

- The user reported the strategy compiled and ran on `TVC:GOLD` 1m. The family showed **Unknown**, so every entry was blocked. Auto-detection now also matches common CFD and spot tickers: `GOLD`, `XAUUSD`, `GOLDUSD`, `NAS100`, `US100`, `USTEC`, `SPX500`, `US500`, `EURUSD`, `USDJPY` and their variants. The manual *Market family* override still wins.
- Dashboard: compact by default (9 rows when flat; levels appear while a position is open). New *Full dashboard*, *position* and *text size* inputs. Shorter execution label.

## 4.0-r2 — October 29, 2026 (review of the supplied 4.0-r1)

The r1 research files were reviewed against the brief, the v3 source and the v3 audit. r1's core architecture was sound and is kept: one shared signal engine, next-tick market entry with pre-submitted absolute brackets, whole-unit tranches, stop-first indicator simulation, and confirmed HTF offset. The defects and gaps below were fixed. **Neither r1 nor r2 has been compiled in TradingView.**

### Defects fixed

| # | r1 location | Problem | r2 fix |
|---|---|---|---|
| 1 | engine L146 | ICC stop used only *earlier* correction extremes, so the continuation bar's own low could lie below the stop. The stop sat inside a range the signal bar had already traded through. | Stop = min(correction lows **including the continuation bar**) − pad (mirror for shorts). This uses only closed-bar data. |
| 2 | engine L190–199 | Float rounding: `floor(0.3 / 0.1)` = 2, and the residual tranche `q − a − b` carried float error, so a quantity step of 0.1 or 0.01 could lose a unit or produce a non-step remainder. | Epsilon-guarded floor/ceil. Tranches computed in integer units, then × step. Conservation tested for 1–10,000 units at steps 1, 0.01 and 1000. |
| 3 | engine L76–79 | "Whole bar inside window" depended on undocumented `time_close(tf, session, tz)` semantics for a bar crossing the end. | Explicit local-minute arithmetic on bar open and (close − 1 ms) per IANA zone, plus a same-local-day check. A Python port was tested on US/UK DST-mismatch weeks. |
| 4 | engine L61 | USDJPY (quote JPY) blocked every entry unless a fixed manual USD value was entered, which goes stale over a long backtest. | USD-base symbols use `pointvalue / close` (exact at the bar's rate). Other non-USD quotes are still blocked unless overridden. The source is shown on the dashboard. |
| 5 | strategy L256–266 | Fill and round-trip detection relied on `strategy.closedtrades[1]` history. `filledBar` stayed `na` when entry and full exit happened within one bar. | `closedAtSubmit` count. Fill price and bar come from `closedtrades` when the position already closed. Order: evidence → fill → flat/no-fill → manage → new intent. |
| 6 | strategy L250 / indicator L284 | BE trigger was "TP1 tranche filled at profit". A 1–unit position has no TP1 tranche, so BE never activated. | One rule in both scripts: BE/trail activate after a close that saw the TP1 **level** traded through, and apply from the next tick. |
| 7 | both, `f_payload` | `str.tostring(na)` writes `NaN`, which is invalid JSON (for example `reference_price` before fill). The fill alert reused the field name `reference_price` for the fill. | `null` for unknown values. Separate `price` and `fill_basis` fields, `event_id`, `setup_id`. |
| 8 | both | No setup ID. Event text for several same-bar events was partly overwritten. | Setup IDs (`L…`/`S…`/`P…`), all events of a bar concatenated, 4-entry history row. |

### Brief requirements added

- Trading-day boundary (timezone + HHMM, default 17:00 New York). Optional daily loss gate in R, max entries per day, loss-streak pause. All execution-side; exits are never blocked.
- Latest-entry cutoff (minutes before window end), weekday mask, per-window timezone inputs, and an optional force-flat window ("no overnight holding").
- Three manual news events + one recurring daily exclusion (own zone) + emergency block. The setup is cancelled on a block.
- Optional close-updated ATR trail after the TP1 level is seen.
- Executable gap policy: exit request if fill risk > N × planned risk (default 1.5×). Fill-risk ratio shown.
- Mode-specific cooldown and min/max stop distance.
- Configurable structure-break buffer in ticks.
- Dashboard: setup state with end reason, initial vs current stop, FLAT/PENDING/OPEN/PARTIAL/COOLDOWN, trading-day row, tick / USD-per-unit source / step, volume status, USDJPY-equivalent for JPY, ambiguous-bar count (indicator), commission-unit warning for non-futures (strategy).
- Data Window parity outputs: raw candidate, eligible signal, ICC state.

### Kept deliberately out

Setup score (the brief allows it, but an uncalibrated score invites misuse), EMA200/VWAP/FVG overlays, watch labels, five targets, resting limit/stop entries. Reasons are in the guide.

### Tooling

`tools/build.py` assembles both files from `src/` and asserts the shared blocks are byte-identical. `tools/parse_check.py` runs a grammar parse (pynescript). `tools/test_reference.py` has 26 scenario, property, session and static tests against `tools/reference_model.py`, a Python port of the rules.
