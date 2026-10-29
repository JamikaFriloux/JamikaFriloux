# MEKA ALPHA PRO 4.0-r2 — validation ledger

Date: October 29, 2026. **Not compiled in TradingView. Not replayed. Not backtested. Not forward-tested.** No return, win rate, profit factor or drawdown figure exists for any version of this script.

Five kinds of evidence are kept separate here:

| Level | Meaning | Done for r2? |
|---|---|---|
| L1 Static inspection | Reading code; text and structure checks | **Yes** |
| L2 Reference model | Rules ported to Python and exercised on synthetic candles | **Yes** (port, not Pine) |
| L3 TradingView compilation | Pine Editor compiles the file | **No** |
| L4 Replay / backtest | Behaviour on real feed data, emulator ledger | **No** |
| L5 Forward test | Paper trading on live bars | **No** |

## What was actually done

1. **Source identity (L1).** `MEKA_ALPHA_PRO_v3_SOURCE.pine` re-hashed: SHA-256 `d4bad2fe…dc988ed`, 1,595 lines, Pine v6, complete. All 1,595 lines were read.
2. **Audit re-verification (L1).** Every A01–A18 line reference was re-opened. 17 confirmed; A17 corrected (only the bullish FVG box is reversed, and its mitigation can never fire). Three P3 notes added (A19–A21). See the audit.
3. **r1 review (L1).** Both r1 files read in full against the brief. 8 defects and the missing brief items are listed in `CHANGELOG.md`.
4. **Grammar parse (L1).** `pynescript` 0.3.0 (an open-source ANTLR Pine grammar) parsed both r2 files and both r1 files without error. As a control, it rejected two deliberately broken snippets (an unclosed parenthesis, a bad indent). **This is not compilation.** It does not check types, built-in names, argument signatures, qualifiers (const/input/simple/series), or v6-specific rules.
5. **Build parity (L1).** `tools/build.py --check` confirms the shipped files match `src/` and that the signal engine, shared execution helpers and display blocks are byte-identical in both files.
6. **Reference tests (L1 + L2): 26/26 passing** (`python3 -I tools/test_reference.py`):

| Group | Tests | What they establish (on the Python port) |
|---|---|---|
| ICC stages | 6 | Indication, correction and continuation fire on three different bars. A single bar meeting all three conditions only indicates. No indication before the first pivot is available (origin + strength). Trigger is frozen; the stop includes the continuation bar's low. Invalidation and expiry end the setup. Far structure is rejected, not clipped. |
| Execution | 10 | Signal-bar target touches are never credited. Favorable gap: fill at the real open, fill-risk ratio 2.5×, TP1 limit fills at the open, gap-policy exit next open. Adverse long/short gaps through the stop exit at the worse open. Stop and target on one bar → stop-first + ambiguity count. TP1 then BE: the dip on the TP1 bar does not stop out; BE applies next bar. One contract → single final tranche, no TP1. Allocation conserves quantity for 1–10,000 units at steps 1, 0.01, 1000, both target modes. Cooldown 0 never re-enters on the exit bar. Targets stay strictly ordered after coarse rounding. |
| Properties | 1 (150 random series × 600 bars, mixed settings) | Stage order always strictly increasing. No pivot ID ever indicates twice. Every indicated pivot was available on an earlier bar. Each trade: fill = intent bar + 1; no TP/stop before the fill; exited quantity = initial quantity. Every signal has stop < ref < TP1 < TP2 < TP3 (mirrored for shorts), all distinct, risk within limits. More than 100 trades and more than 20 ICC continuations were exercised. |
| Sessions | 3 | Port of the Pine window formula with `zoneinfo`: NY 08:30 = 13:30Z (EST) / 12:30Z (EDT); London 08:00 = 08:00Z in the March 9–27 and October 26–31, 2026 mismatch weeks, 07:00Z in BST; Tokyo fixed. A bar crossing the end is rejected; a 15-min bar ending at 12:00 has 0 min left (blocked by a 5-min cutoff). Saturday rejected. Trading-day key rolls at 17:00 New York across EST/EDT, not at midnight. |
| Static Pine | 6 | Shared blocks identical. Declarations and strategy flags as documented. No `strategy.*` in the indicator. HTF request uses `[1]` offsets with `lookahead_on`. No win-rate, probability, accuracy, institutional or `varip` text, and no percentage claims in user-visible strings. Balanced brackets and 4-space indents. Every `:=` target is a declared name. |

**What these do not show:** that TradingView compiles the files; that `hour()`/`minute()`/`dayofweek()` with an IANA zone match `zoneinfo` (they should, but this is unverified); that the emulator fills brackets as described; that `strategy.closedtrades.*` fields behave as assumed; or anything about profitability.

## Compile-risk notes for the first TradingView run

Places where Pine semantics were reasoned about rather than observed:

- `f_mins` divides ints (`hhmm / 100`) inside `math.floor`. This is correct whether v6 returns int or float for that division.
- `str.tonumber(str.substring(session, …))` parses `input.session` strings (`"0900-1500"`). If TradingView ever returns a different format, the bar-0 check stops the script with "sessions must be same-day HHMM-HHMM".
- `strategy.closedtrades.exit_comment()` / `exit_id()` / `size()` / `exit_price()` / `profit()`, `strategy.opentrades.entry_price()` / `entry_bar_index()`. Check the comment strings TP1 / TP2 / FINAL TP / STOP / exit reason appear in the List of Trades.
- `strategy.exit` called from inside a user function (`f_sendExits`), and before the entry fills.
- `var table dash = showDash ? table.new(...) : na`, `array.join` of a string array, and `text_halign` in `table.cell`.
- Any compiler warning about unused `plusDI`, `minusDI`, `highAvail`, `lowAvail` is expected. Those values are kept for diagnostics.

## Not done — the TradingView test matrix

Status for every row: **NOT RUN (L3–L5)** unless a Python port result is noted.

| # | Test | Procedure | Required outcome |
|---|---|---|---|
| 1 | Compile indicator | Paste the full file, save, add to chart | No errors; record warnings |
| 2 | Compile strategy | Same, separately | No errors; trades appear once capital/margin allow |
| 3 | Invalid chart / HTF | Open on 1D, Heikin Ashi, and with trend TF = chart TF | Runtime error with the MEKA message |
| 4 | Signal bar touched target | Find an ENTER whose signal-bar high ≥ TP1 | No TP on the signal bar; first event is the fill on the next bar (L2 pass) |
| 5 | Gap fill | Pick a signal before a session gap | Indicator fill = next open; strategy fill in List of Trades; dashboard ratio; gap exit if > N× (L2 pass) |
| 6 | Stop + TP same bar | Find a bar touching both | Indicator: STOP + ambiguous count; strategy: record the emulator's choice with Bar Magnifier off and on (L2 pass for indicator) |
| 7 | TP1 and stop on one bar | Two-unit position | Correct tranche quantities; BE not applied to that bar (L2 pass) |
| 8 | Stage separation | Bar Replay through an ICC sequence | Data Window state 0→1→2→signal on three different bars (L2 pass) |
| 9 | Pivot delay | Replay a breakout near a fresh pivot | No indication before origin + strength (L2 pass) |
| 10 | HTF reload | Note signal times, reload / reopen chart after bars close | Identical confirmed signals and IDs |
| 11 | Realtime vs history | Leave running through live bars, then reload | Signals on closed bars unchanged |
| 12 | One futures contract | Risk settings giving qty 1 on MES | Single FINAL exit; TP1 shows `skip` (L2 pass) |
| 13 | Allocation | qty 2, 3, 7 with and without TP3 | List of Trades quantities sum to entry; every unit had a stop (L2 pass) |
| 14 | Overlapping windows | London + NY overlap day | One entry per setup |
| 15 | DST weeks | March 9–27 and October 26–31, 2026 bars | Window starts at the local times above (L2 pass for formula) |
| 16 | Midnight / day reset | Position open across 00:00 and 17:00 NY | Protection unchanged; counters reset only at 17:00 |
| 17 | News / force-flat while holding | Enable an event covering an open trade | No new entries; brackets stay; force-flat requests exit next tick |
| 18 | 6J vs USDJPY | Same date on both | Native sides; dashboard USDJPY-equivalent correct; no double inversion; USD/unit = pointvalue / close on USDJPY |
| 19 | Unknown metadata / volume | Exotic CFD; enable volume on a no-volume FX feed | Entries blocked with the reason shown |
| 20 | Alerts vs plots | Create alerts, wait for events | Same trade IDs and bar-close times; fills tagged `ASSUMED_SIMULATION` vs `TV_EMULATOR` |
| 21 | Indicator vs strategy parity | Same inputs, export Data Window | *Raw candidate*, *Raw eligible candidate direction* and *ICC setup state* identical on every bar; accepted entries may differ after a divergent exit (explain each case) |
| 22 | No fill | Set margin 100%, capital $1,000 on ES | `NO FILL` event, no stuck PENDING, cooldown applied |
| 23 | Same-bar round trip | Find entry + full exit in one bar | Strategy returns FLAT, R recorded, no stale pending |
| 24 | Date range | Start/end inside the data | Warm-up used; no entries outside; open position gets an exit request at end |
| 25 | Cost reconciliation | 10+ trades by hand | Commission/slippage match Properties; daily R matches net P&L ÷ planned cash risk |

## Research protocol (before any statistic is quoted)

1. Pass rows 1–25 and fix any accounting defect first.
2. Freeze the baseline settings and record version, feed, contract, timeframe, dates, Properties (costs, margin, Bar Magnifier) and inputs.
3. Chronological folds, for example 12 months train / 3 months validation / 3 months test, rolling, plus a final untouched holdout. Set acceptance criteria before looking at the test folds. A position that crosses a fold boundary belongs to the fold where it was entered. Changing rules after seeing the holdout requires a new holdout.
4. Report per feed × mode × session × direction, plus combined results without double counting. Use complete-position results: trades, net expectancy (R and currency), profit factor, max drawdown, exposure, average win/loss, month/fold dispersion, and sample-size uncertainty. Partial targets are not separate wins.
5. Stress costs at 1×, 1.5×, 2× and gap scenarios. Check parameter neighbourhoods. Compare against the trend-pullback baseline under identical costs and folds.
6. Paper-forward-test across several sessions per market and log every difference between intent, emulator fill and paper fill.

## Release gates still open

TradingView compilation (both files) · deterministic replay rows · feed metadata and cost verification per market · walk-forward evaluation · paper forward test · external execution bridge (not part of this project). **Passing the L1/L2 checks above is not evidence of compiled correctness or of any trading edge.**
