# MEKA ALPHA PRO 4.0 — copy-paste engineering brief for Claude

## Source and handoff status

Updated October 29, 2026 after receiving the full upload. Source: `MEKA_ALPHA_PRO_v3_SOURCE.pine`, Pine v6, 1,595 lines, SHA-256 `d4bad2fe5a60949e0e2a2bdbcf9518b7ec96d325facdeba6e0d382a58dc988ed`. Full static audit is supplied in `MEKA_ALPHA_PRO_v3_AUDIT.md`.

Also supplied: standalone `MEKA_ALPHA_PRO_4_INDICATOR.pine` and `MEKA_ALPHA_PRO_4_STRATEGY.pine`, explicitly **4.0-r1 research builds, not compiled in TradingView**; guide and validation ledger. These rebuild v3 concepts rather than preserving its complete visual feature set. No market calibration or profitability validation has been performed.

Upload the files together to Claude, then copy this brief. Ask Claude to verify the audit against v3, inspect the research implementation against this specification, repair omissions, and compile/test if its environment supports TradingView. The broad requirements below describe the intended 4.0 release, not a claim that the research build already implements every item.

### Verified findings to address first

1. Pending fills at v3 lines 873–877 / 911–915 construct brackets from the completed fill candle, then management at 952 onward evaluates that candle's entire range. Default Signal Close entry occurs AFTER management and does not have that same pre-entry-range defect.
2. Pending gaps always fill at requested price (874/912), regardless of open.
3. Quantity is recalculated from the moving stop (1495), so it does not represent actual remaining units.
4. TP flags at 962–1062 do not reduce a tracked position; costs and trade accounting are absent.
5. London/Asia share New York timezone (137–143); overnight permission bypasses the entry windows (145–146).
6. Freshness windows can reuse setups; cooldown zero permits close/re-entry on one bar.
7. Smart stops clamp inside far structure rather than rejecting risk (652–666).
8. Score duplicates volume evidence, but v3 does NOT claim that its score is a probability or contain an 87–97% win-rate claim.
9. HTF offsets and closed-bar trade management are worth preserving. Do not falsely label them future lookahead.
10. FVG bounds, stop-line cleanup, event coalescing and rejection diagnostics need the documented fixes.

### Research-build decisions and remaining work

- Fixed absolute brackets are submitted alongside next-tick market entries. R and sizing use signal-close planned risk; actual fill risk changes with gaps. No live gap cancellation guarantee is claimed.
- Both files share identical raw signal logic; their execution conventions can diverge, so accepted entries later in the sequence can also diverge.
- Two default targets, optional third; too few tradable units become one final-target tranche. Break-even is optional and updates after close.
- Profiles detect family/quote and sizing applicability; numeric edge calibration is NOT provided. USDJPY requires an explicit USD-per-point-per-order-unit override. Strategy profit accounting still uses TradingView symbol metadata, so verify overrides against that feed.
- One manual news blackout, fixed reference balance risk sizing, no daily loss/entry cap, no trailing stop, no custom spread engine, no confidence score, and no portfolio testing. These limitations are explicit in the guide.
- The original EMA200/VWAP/FVG overlays, watch labels, multi-row MTF scores, alternative resting entry types and five-target system were intentionally not copied into r1. Evaluate whether to restore each, rather than blindly porting them.
- Audit strategy rejected-order recovery, same-bar round trips, stop reservation, BE timing, session cutoff semantics, and raw-signal parity before extending the code.

---

## Your assignment

Act as a senior Pine Script v6 engineer and systematic trading researcher. Read the entire attached MEKA ALPHA PRO v3 source before editing. Upgrade it into MEKA ALPHA PRO 4.0 with a companion strategy for honest backtesting. Preserve useful existing features after auditing them. Prefer clear, testable logic over adding many loosely related indicators.

First confirm the exact filename, version declaration, total line count, and source completeness. If the attachment is missing or truncated, ask for it and stop source-dependent work. Never invent an audit, line references, compiler results, backtest statistics, or prior implementation details. You may continue refining this specification while waiting.

Deliver:

1. `MEKA_ALPHA_PRO_v3_AUDIT.md`: evidence-based audit with source line references, severity, impact, example failure, proposed repair, and regression test.
2. `MEKA_ALPHA_PRO_4_INDICATOR.pine`: complete standalone Pine v6 indicator.
3. `MEKA_ALPHA_PRO_4_STRATEGY.pine`: complete standalone Pine v6 companion strategy.
4. `MEKA_ALPHA_PRO_4_GUIDE.md`: setup, market profiles, sessions, signal meanings, execution assumptions, alerts, limitations, and validation instructions.
5. `MEKA_ALPHA_PRO_4_VALIDATION.md`: actual checks performed, unresolved checks, and reproducible test matrix. Distinguish static inspection, TradingView compilation, replay, backtesting, and forward testing.

No pseudocode or omitted function bodies in final Pine files. If an environment cannot run Pine, say “not compiled in TradingView” and give precise verification steps. Do not claim production readiness merely because the script compiles.

## Product scope

Support five market families, on the chart’s actual tradable symbol:

| Family | Supported examples | Required distinction |
|---|---|---|
| Gold | XAUUSD, GC, MGC | Spot/CFD feed conventions versus full and micro futures |
| Nasdaq | NQ, MNQ | Different contract risk and fees despite similar price movement |
| S&P 500 | ES, MES | Separate contract sizing and liquidity assumptions |
| EUR/USD | EURUSD, 6E | Broker spot units versus futures contracts |
| USD/JPY | USDJPY, 6J | Opposite quote orientation; never silently copy a directional signal |

Run on one chart symbol at a time. These profiles do not constitute a five-symbol portfolio backtest. Avoid fragile substring-only detection; use available root/type/currency metadata, manual profile override, and an explicit unknown-symbol state. Never guess contract sizing on an unrecognized feed.

For 6J, display that a LONG is long JPY versus USD and directionally opposite a USDJPY LONG. Native chart trend signals and orders remain in native chart direction. Only invert external USDJPY-normalized bias when intentionally mapping it to 6J. If constructing reciprocal OHLC, use O'=1/O, H'=1/L, L'=1/H, C'=1/C with valid nonzero prices; compute transformed indicators from transformed prices. Do not invert native trade P&L or swap order sides twice. Futures basis means reciprocal spot is not an exact futures price.

Use `syminfo.mintick` and suitable symbol metadata with verified overrides. Round prices to valid ticks and quantities to actual tradable increments. Show profile, mode, chart direction, tick size, and cost assumptions in settings or diagnostics.

## Audit the complete v3 script

Produce a module inventory covering inputs, calculations, security requests, sessions, structure, scoring, entry/exit logic, persistent state, drawing objects, dashboard, alerts, and any performance counters. Identify dead code and contradictory conditions.

For every finding, quote a small exact excerpt and give real line numbers. Mark inspected sections with no findings as inspected rather than inventing problems. Audit especially:

- Independent `if` blocks allowing WAIT → ENTER → TP → EXIT on one historical bar using its already-completed high/low.
- A close-confirmed signal receiving credit for targets touched before the close or before entry existed.
- Entry price recorded at signal close while strategy fills at next open; missing gap treatment.
- Stops/targets retroactively changed by the current candle, including break-even applied before the TP that authorized it.
- Both stop and target touched on one bar; assumed best-case ordering and inconsistent long/short handling.
- Targets counted repeatedly; partial quantities exceeding the original position; residual quantities left unprotected; resetting trade state too early.
- Pivot labels back-plotted to their originating candle while signals pretend the pivot was known then.
- Unconfirmed higher-timeframe data, unoffset lookahead, intrabar signals that vanish after reload, and inappropriate use of `varip` or tick recalculation.
- Scores labeled probability, “confidence,” or win rate without calibrated out-of-sample evidence.
- Wins counted per TP rather than per complete position; losses omitted; fees, spread, gaps, and slippage excluded.
- Session timezone assumptions, DST errors, overnight windows, overlapping-session duplicate entries, and daily reset boundaries.
- Alert timing different from chart signals, repeated alerts, stale script snapshots, and ambiguous entry-versus-fill messages.
- Invalid initialization, insufficient history, missing volume, zero risk distances, quantity rounding, divisions by zero, and excessive drawing/resource use.

Do not label ordinary past confirmed-bar calculations as repainting merely because a future data-vendor correction is possible. State exactly which behavior changes historical decisions.

## Core trading hypothesis: trend plus ICC

Use ICC here to mean **indication → correction → continuation**. Treat this as a transparent research hypothesis, not a standardized proprietary method or the “most proven” approach. Do not confuse it with ICT or imply demonstrated edge. Document every discretionary term as an equation or state transition.

Proposed baseline, subject to audited v3 compatibility and subsequent testing:

1. Trend filter: confirmed higher-timeframe price/EMA direction and EMA slope. Flat or conflicting bias blocks entries. Optional ADX or normalized range filter may block low-quality conditions, but avoid stacking correlated filters into artificial confidence.
2. Market structure: confirmed pivot highs/lows with user-defined left/right strengths. A pivot is usable only on its confirmation bar. Store both its origin and availability times. Identify BOS/structure invalidation using close breaks by a configurable tick or ATR buffer.
3. Indication: a confirmed close breaks previously available structure in the trend direction with a configurable displacement condition. Freeze broken level, direction, impulse bounds, ATR reference, and indication bar. Thresholds must use information available at the time.
4. Correction: on a strictly later bar, price revisits a defined retracement band of the frozen impulse or a buffered broken-level retest. Choose one documented baseline definition. Reject correction if structural invalidation occurs or timeout expires. Record correction extremes without moving frozen impulse anchors.
5. Continuation: on a strictly later bar than correction confirmation, a confirmed close breaks a correction trigger in the original trend direction. Compare against the trigger saved before the current bar; do not move a trigger using the very bar being tested.
6. Enter only if session, trend, volatility, stop-distance, news-block, cooldown, position, and reward-space gates pass. One setup produces at most one entry. Re-arm only through a new qualifying indication.

Expose separately a trend-pullback mode, ICC mode, and combined mode if useful. Combined signals on one bar must deduplicate to one entry. Show reason codes for blocked setups. A confluence score may be displayed as “setup score X/100,” with explicit weights; it is never a success probability. Hard validity/risk gates cannot be overridden by a high score.

## Modes and calibration

Provide Scalp and Day Trade modes. Initial research presets may suggest scalp charts of 1–5 minutes and day charts of 5–15 minutes; these are starting hypotheses, not recommendations with demonstrated returns. Higher-timeframe choices must be strictly higher than the chart, or fail clearly. Define independent mode defaults for structure strength, trend timeframe, timeout, volatility normalization, cooldown, stop limits, and time-based exits.

Provide a compact profile table of proposed starting values with units and rationale, explicitly marked unvalidated. Prefer ATR/tick-normalized thresholds over a shared fixed point distance. Calibrate separately for symbol/feed, session, and mode without producing dozens of freely optimized knobs. Treat XAUUSD broker feeds and currency futures as distinct execution datasets. Missing or unsuitable spot volume must disable volume-dependent gates visibly or use an explicit alternative; never silently treat missing data as valid volume confirmation.

## Sessions and trading-day semantics

Provide independently enabled Asia, London, and New York windows using editable local times and IANA timezones: `Asia/Tokyo`, `Europe/London`, `America/New_York`. “Asia” means the chosen Tokyo window, not a universal Asian exchange session. Example research windows: Tokyo 09:00–15:00, London 08:00–12:00, New York 08:30–12:00 local. Label these as configurable entry windows, not exchange opening hours or proven optimal periods.

Use timezone-aware `time()`/`time_close()` logic and explicit weekday masks. Account for the weeks when US and UK DST dates differ. Session overlap must not duplicate a signal; show all active windows or a documented display priority. Define whether signal-bar open and close must both be inside the window, how boundary-crossing chart bars behave, and how pending next-bar fills are handled near window end. A close-confirmed signal near the boundary can fill outside the entry window: disclose or prevent this with a documented cutoff.

Entry filtering never disables protective exit management. Separately configure forced session exits, overnight holding, and latest-entry cutoff. No open-position state resets at midnight. Trading-day loss counters need an explicit timezone/reset boundary, including overnight futures trading. Holidays, half-days, and exchange maintenance breaks require data-aware behavior; the three local windows alone do not encode an exchange calendar.

## Execution contract and state machines

Separate setup state from position/order state. Suggested setup states: IDLE, INDICATED, CORRECTING, READY, EXPIRED. Suggested position states: FLAT, PENDING, OPEN, PARTIAL, CLOSED/COOLDOWN. Persist unique setup/trade IDs and entry, signal, and fill bar indexes.

Take a snapshot of prior state, calculate events, apply prioritized transitions once, then emit visuals/alerts from those events. Distinct indication/correction/continuation stages must not collapse into one bar. Entry and exit can legitimately occur within one bar if an entry existed early enough and execution data supports it; do not “fix” the indicator by globally banning all entry-bar protective exits.

Default strategy research contract: confirmed-bar signals, no pyramiding, no automatic reversal, `calc_on_every_tick=false`, and `process_orders_on_close=false`. Normally orders created at signal-bar close fill at the next available tick, often next bar open. Record signal, order submission, emulator fill, and external broker fill as different events.

Explain `calc_on_order_fills` tradeoffs before using it. It can help initialize fill-relative protection but can also produce unrealistic historical recalculation behavior. Choose and document a bracket approach that protects the earliest eligible fill without using information unavailable at order creation. Consider pre-submitted tick-distance brackets versus frozen absolute structure levels, and explicitly state what gaps do to actual risk. Never leave an unmentioned bar of unprotected exposure while waiting to observe a fill.

Use TradingView’s broker emulator as the companion strategy’s execution record. An indicator has no broker fill knowledge: label its position state simulated, and its entry price assumed until an external execution system confirms it. Keep signal generation identical across both scripts; explain unavoidable differences in simulated fills.

For custom indicator simulation, a pending market entry may be assigned next-bar open, then existing bracket events considered under a documented intrabar assumption. If OHLC cannot establish stop/TP ordering, flag ambiguity and use a conservative documented convention rather than assuming profit. Report such bars separately. Enable optional Bar Magnifier in the strategy, document coverage limits, and do not claim it reconstructs every tick.

## Risk, targets, and partial exits

Default to two targets, with optional third. Proposed unvalidated research defaults: TP1=1R, TP2=2R, allocations 50%/50%; optional TP3=3R with 40%/30%/30%. R is explicitly defined from the entry assumption or actual fill to the initial protective stop; never redefine historical R after moving a stop. If gap fills alter R or target ordering, record the effect and apply a documented reject/cancel/exit policy where executable.

Base initial stops on correction/structure invalidation with configurable tick/ATR padding; enforce minimum and maximum distance. Freeze the initial stop and target rules at the defined time. Reject zero/negative risk and invalid ordering. Long stop < entry < TP1 < TP2 (< TP3), with reverse ordering for shorts, after tick rounding.

Use separate, stable exit IDs tied to the correct entry ID. Account for `strategy.exit` reservation and OCA behavior. Every remaining unit must stay protected. Track TP fills from execution evidence rather than just high/low touches. No duplicate TP1 events. Optional break-even after confirmed TP1 and optional trailing stops activate only after their triggering event; stop updates cannot retroactively affect earlier prices. A scratch at entry may still lose after fees.

Futures partial closes must use whole contracts: one contract cannot become two half-contract fills. Provide an explicit small-position policy, such as one final target for a single contract, or rejecting quantities below the selected scale-out requirement. Round allocations deterministically and send residual units to the final tranche. Spot/CFD units and minimum lot increments require broker-specific inputs.

Position size derives from user risk budget and stop risk in account currency, with appropriate point value/currency conversion, quantity step, and size cap. Use cash-risk conversion rather than treating percent-of-equity notional as stop risk. Unknown sizing metadata must block sizing or require an override. Suggested conservative research defaults are configurable; do not represent any fixed risk percentage as universally safe. Add optional daily loss gate, max entries per trading day, cooldown, and loss-streak gate, with exits always active.

## Costs, news, and data limitations

Backtests must explicitly configure commission, slippage in ticks, and a documented spread approximation. Futures fees may be per contract per side; spot/CFD commission units differ. Charge partial exits correctly and avoid double counting spread as both commission and price adjustment. Explain which parameters belong in strategy Properties rather than ordinary runtime inputs. Show cost assumptions, and require users to replace illustrative values with their venue’s values before interpreting results. Stress costs at baseline, 1.5×, and 2× plus gap scenarios.

Do not claim native Pine access to a complete live economic-news calendar. Implement optional manual timestamp blackout windows with pre/post buffers and an emergency “block new entries” control. Clearly label calendar coverage manual/incomplete. `request.economic` is not an event-news calendar. Separate recurring time exclusions from event-specific timestamps. Timezones must be explicit. A strategy-side manual block does not cancel an already-submitted broker order unless the integration implements that behavior. Keep protective orders active during news. If an external calendar/execution bridge is proposed, document it as a separate dependency, not a built-in capability.

Use standard OHLC candles for execution testing. Document continuous-futures rollover and adjustment effects, actual contract testing, feed differences, missing bars, and available history. No multi-symbol aggregate performance claims from one chart backtest.

## Dashboard and alerts

Make the main dashboard readable: **WAIT / ENTER / HOLD / TP / EXIT**.

- WAIT: no qualified actionable setup; show one concise reason.
- ENTER: a new confirmed signal/order intent, with LONG or SHORT; never label it broker-confirmed fill.
- HOLD: simulated or emulator position remains open.
- TP: a newly observed partial-exit event; show TP1/TP2/TP3 and remaining quantity, then return to HOLD if appropriate.
- EXIT: final exit event with reason; then WAIT/cooldown.

Define one-bar event duration and deterministic priority when multiple events occur. Final closure takes priority over a partial-state display; preserve all execution events in diagnostic history. Include small secondary fields for market/mode/session, direction, entry assumption, stop, targets, setup score, and news-block status. Show pending execution in secondary text without misleading HOLD status. Do not crowd the main panel with unvalidated statistics.

Provide indicator signal alerts and strategy emulator order-fill alerts with different event types. Payloads should include version, ticker ID, chart timeframe, native side, setup/trade ID, event timestamp, assumed/actual fill marker, stop, target, and quantity where known. Use closed-bar signal alerts and stable event IDs; no repeated alerts on every HOLD bar. Document exit alert timing for resting stop/limit fills versus close-based decisions. Order-fill alerts describe emulator fills, not brokerage acknowledgments. Users must recreate alerts after changing script/settings because alerts retain snapshots.

## Validation and acceptance tests

Perform the following tests or mark them explicitly unrun:

| Test | Required outcome |
|---|---|
| Signal bar already touched target before its close | No fabricated pre-entry profit |
| Gap between signal close and next open | Actual modeled fill/risk recorded; no silent close-price substitution |
| Stop and TP both touched | Emulator assumption or conservative ambiguity rule disclosed |
| TP1 and stop in same bar | Correct partial quantity and event ordering; no retroactive break-even |
| Multiple stages appear on one bar | No collapsed indication/correction/continuation |
| Pivot confirmation delay | No signal before pivot becomes available |
| Open HTF candle changes | Confirmed signal unchanged after reload |
| HTF <= chart timeframe | Clear rejection or documented supported alternative |
| One futures contract with scale-out | No fractional futures exits |
| TP allocations after rounding | Sum equals original quantity; remainder protected |
| Three overlapping sessions | One trade per setup |
| US/UK DST transition weeks | Local windows remain correct independently |
| Midnight while position open | Position protection retained |
| News blackout/session ends while holding | New entries blocked; protective exits active |
| 6J vs USDJPY | Native direction and normalized bias correct; no double inversion |
| Missing volume/unknown metadata | Explicit fallback/block, no false confidence |
| Repeated reload/replay | Same confirmed signals with same data/settings |
| Alerts versus plotted signals | Same IDs and signal times; fills distinguished |
| Indicator versus strategy | Signal parity; execution differences explained |
| Date-range boundaries | Warm-up preserved; outside-window entries excluded; final exits specified |

Use chronological train/validation/test partitions, not random bar splits. Establish parameter ranges and acceptance criteria before seeing final test results. One possible research schedule is rolling 12-month training, 3-month validation, and 3-month out-of-sample blocks, adjusted to data availability and disclosed. Reserve a final untouched period. Provide indicator warm-up before scored windows without allowing future-dependent labels or optimized parameters to leak backward. Specify how positions crossing fold boundaries are handled. Do not optimize on the final holdout; changing rules after examining it requires a new holdout.

Evaluate each symbol/feed, mode, session, and long/short direction separately, plus combined summaries that do not double count overlapping trades. Record complete-position wins/losses, trade count, net expectancy in R and currency, profit factor, drawdown, exposure, average win/loss, cost sensitivity, and month/fold variability. Partial target hits are not separate full-trade wins. Report uncertainty and sparse samples; neither many scalp trades nor one profitable month proves robustness. Check parameter neighborhoods and simplify rules that only work at one precise setting. Compare ICC against a simpler trend-only baseline under identical costs and splits. Aggregate correlated trade outcomes cautiously.

No 87–97% win-rate claims, guaranteed returns, or “institutional accuracy” language. Any reported rate must come from named data, dates, costs, exact version/settings, complete trade accounting, and unseen evaluation. An uncalibrated score is never probability. Finish with a paper-forward-test checklist and unresolved risks, not a profitability promise.

## Implementation sequence

1. Read source and produce the audit before edits.
2. Define the execution contract, state transition table, ICC equations, profile schema, and assumptions.
3. Implement shared signal logic consistently in the indicator and strategy; keep both standalone unless an accessible published library is explicitly chosen.
4. Implement position management, costs, sessions, dashboard, and alerts.
5. Compile each file in Pine v6 if available, repair errors, then run the acceptance matrix.
6. Provide complete files, a concise change log, migration notes, and an honest validation ledger. If you cannot run TradingView, stop short of claiming compiler or backtest success.

## Official references to consult

Use current official documentation and verify any version-sensitive API details before implementation:

- [TradingView strategies and broker emulator](https://www.tradingview.com/pine-script-docs/concepts/strategies/): order timing, fill assumptions, costs, partial exits, Bar Magnifier, recalculation.
- [TradingView repainting](https://www.tradingview.com/pine-script-docs/concepts/repainting/): confirmation and historical/realtime consistency.
- [Other timeframes and data](https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/): HTF requests. For strictly higher timeframes, the confirmed-data pattern uses an offset expression with `barmerge.lookahead_on`; unoffset lookahead leaks future data. Do not apply the pattern indiscriminately to lower timeframes.
- [TradingView sessions](https://www.tradingview.com/pine-script-docs/concepts/sessions/) and [time](https://www.tradingview.com/pine-script-docs/concepts/time/): explicit session timezones and IANA DST behavior.
- [TradingView alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/): signal events, order-fill events, and alert snapshots.
- [CME Japanese yen contract specifications](https://www.cmegroup.com/markets/fx/g10/japanese-yen/specs): USD-per-JPY quote orientation. Verify exact selected contract/feed metadata separately.

END OF CLAUDE BRIEF
