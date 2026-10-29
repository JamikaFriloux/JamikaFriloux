# Changelog

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
