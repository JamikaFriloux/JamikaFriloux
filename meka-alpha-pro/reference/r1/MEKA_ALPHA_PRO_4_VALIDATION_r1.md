# MEKA 4.0-r1 validation ledger

Date: October 29, 2026. **Research prototype, not compiled in TradingView.**

## Completed

- Read all 1,595 lines of v3; preserved original bytes and verified SHA-256.
- Produced 18 source findings plus documented protections/non-findings. No v3 runtime or profit claims were inferred.
- Wrote standalone indicator and strategy from one common raw signal engine; verified those embedded engine blocks are identical.
- Reviewed next-tick planned-bracket architecture, whole-unit partial allocations, gap conventions, BE update timing and rejected-order recovery.
- Ran 18 local checks successfully. They cover source identity, common-engine identity, balanced delimiters/strings, allocation conservation, small-position allocation, tick ordering, long/short stop-first scenarios, long/short stop gaps, multiple target scenarios, next-open time exits, stage guards, bracket-submission presence, no-same-bar re-entry guards, HTF offsets/pivot ordering, IANA DST reference conversions, and native JPY direction/unknown-sizing guards.
- Allocation reference checks covered each integer quantity from 1 to 10,000 with both target modes. Three-target quantities below 3 and two-target quantities below 2 route entirely to the final target.
- DST reference checks used March 6, March 10 and April 2, 2026 to show independent New York/London changes and stable Tokyo time.

**What these checks mean:** some inspect generated text; some exercise small independent Python reference calculations for desired behavior. They do not execute Pine, implement the full ICC engine, verify TradingView's session functions, or reproduce its broker emulator. Balanced delimiters are not compilation. Passing these checks is not evidence of profitability or end-to-end correctness.

## Not completed

| Required check | Status | Procedure / acceptance |
|---|---|---|
| Pine v6 compile, indicator | NOT RUN | Paste full file into Pine Editor; compile without errors; record warnings |
| Pine v6 compile, strategy | NOT RUN | Same, independently; review inferred types and order API usage |
| Standard chart/timeframe guard | Static inspected only | Nonstandard charts and HTF<=chart must fail clearly |
| No-history / warm-up handling | Static inspected only | No entries until required data exists |
| Indicator/strategy raw-signal parity | Identical source only | Compare Data Window direction per closed bar under identical inputs |
| Reload / realtime confirmation | NOT RUN | Save signal IDs, reload after bar close; IDs/confirmed signal bars must match |
| ICC stage sequencing | Guard text inspected only | Replay: indication, correction, continuation each on a later bar; consumed pivot never reused |
| Filled entry plus full exit same bar | NOT RUN | Emulator position must return flat; no stale pending state |
| Rejected entry / insufficient margin | Recovery text inspected only | No fill at next close should reset intent with reason, not remain pending |
| Partial exit reservation / OCA | NOT RUN | Every remaining unit protected; no duplicate closed tranche orders |
| One and two futures contracts | Reference allocation passed | Confirm TradingView actual order quantities match allocation |
| TP1 then BE | Static inspected only | BE update after observed profitable TP1; no earlier-candle retroactive stop |
| Stop+target candle ambiguity | Reference convention passed | Indicator flags ambiguity; strategy outcome reflects configured emulator, not presumed parity |
| Gap beyond bracket | Reference stop logic passed | Inspect actual fills/risk; no assumed reference-price fill in strategy |
| Session boundary fragments | NOT RUN in Pine | Compare 1/5/15-minute charts around start/end; reject partial session bars |
| US/UK DST mismatch weeks | External timezone reference passed | Verify actual Pine session timestamps in March/October/November |
| Session overlap | Static union gate only | One raw candidate and one entry intent per setup/bar |
| Overnight / holiday / missing bars | NOT RUN | Record that weekday research windows are not exchange calendars |
| Manual news event | Static inspected only | Blocks intersecting bars; protects existing position; does not claim complete news coverage |
| USDJPY conversion / 6J orientation | Static inspected only | Verify actual broker units, sizing conversion and native strategy direction |
| Fees / slippage / spread approximation | NOT CALIBRATED | Replace defaults by venue/feed; reconcile at least 10 trades manually |
| Alert JSON / IDs / fill templates | Static inspected only | Realtime test; record intent and each fill; deduplicate by trade/event/time |
| Forced exit at test end | NOT RUN | Close request at first qualifying close; account for missing next tick |
| Empirical backtest / walk-forward | NOT RUN | No return, win rate, profit factor or drawdown results available |
| Paper forward test | NOT RUN | Observe confirmed decisions and execution differences across multiple sessions |

## Release gates

1. Compile and repair both scripts. Preserve the audit's original source file and line numbers.
2. Run deterministic execution/replay cases above before tuning parameters. Fix accounting issues before reading performance statistics.
3. Verify each exact feed's tick value, contract/unit size, margin and cost configuration; compare planned and actual fill risk.
4. Freeze baseline parameters, train/validate chronologically, then evaluate unseen folds and final holdout. Publish exact symbol, dates, timeframes, version and settings.
5. Report complete-position net results, not partial-exit “wins”; include trade counts and uncertainty. Compare against simpler trend-pullback baseline.
6. Stress costs and gaps, examine parameter neighborhoods, and paper-forward-test before considering an execution integration.

The comprehensive Claude brief includes the intended fuller release requirements. Passing the prototype's local checks does not satisfy those release gates.
