# MEKA CRT PRO

A private, Candle Range Theory trading assistant for TradingView, written in Pine Script v6. Built from scratch. None of the previous MEKA ALPHA PRO architecture is reused.

| File | Purpose |
|---|---|
| `MEKA CRT PRO — Indicator.pine` | The chart assistant: ranges, liquidity, sweeps, 15M/5M confirmation, BUY/SELL, SL/TP1/TP2, dashboard, alerts. **Source of truth for the engine.** |
| `MEKA CRT PRO — Strategy.pine` | Backtest version, generated from the indicator, so the entry/exit rules are identical. |
| `tools/build_strategy.py` | Regenerates the strategy after you edit the indicator. |
| `docs/CRT_RULES.md` | The exact, objective setup rules. |
| `docs/SETTINGS.md` | Starting settings for Gold (XAUUSD / GC / MGC) and NQ / MNQ. |
| `docs/TESTING.md` | Verification checklist, backtest protocol, known limitations. |
| `docs/UPGRADE_STAGES.md` | Stage 1 (FVG, inverse FVG, supply & demand, MSS, minimal dashboard): rules, measurements, defaults, testing, and the Stage 2–3 plan. |
| `docs/MODEL_C.md` | Model C (15M double-range confirmation): exact rules, MTF handling, measured results, checklist, open decisions. |
| `docs/STATE_MACHINE_AUDIT.md` | Why setups kept invalidating, what was fixed, measured before/after on real gold data. |
| `tools/replay/` | Python bar-for-bar replay of the engine + no-future-information test. |

## Models

* **Model A: CRT sweep/reclaim.** A 4H/1H CRT sweep and reclaim, confirmed on 15M, entered on 5M. Labels: `A · BUY` / `A · SELL`.
* **Model C: 15M double-range confirmation.** Two completed 15M candles are frozen as a range, and a later 15M close beyond it triggers the trade. It is drawn in purple, with labels `C · BUY` / `C · SELL`. Settings are in input group ⑭; see `docs/MODEL_C.md`.
* There is no Model B in the code (see `docs/MODEL_C.md`, decisions).
* **Model AMD: Power of Three (Stage 2, optional).** Accumulation range → confirmed manipulation sweep → displacement distribution. Labels: `AMD · BUY` / `AMD · SELL`, M/D markers. Settings are in input group ⑱; see `docs/UPGRADE_STAGES.md`.
* **Context overlays (Stage 1):** FVG / inverse FVG (group ⑮), supply & demand / order blocks (group ⑯), BOS / CHoCH / MSS and liquidity lines (group ⑰). They inform; they do not create trades.

The strategy trades **one model per run** (*Model traded by this strategy*), so each model is tested independently.

## Installation

1. Open TradingView and load a **5-minute** chart of XAUUSD, GC, MGC, NQ or MNQ.
2. Open the **Pine Editor**, click **New → Blank indicator**, delete the template, and paste the entire contents of `MEKA CRT PRO — Indicator.pine`.
3. Click **Save** (name it *MEKA CRT PRO*), then **Add to chart**.
4. For the backtest: create a new blank **strategy**, paste `MEKA CRT PRO — Strategy.pine`, save it, add it to the chart, and open **Strategy Tester**. Set the commission and slippage for your market in *Settings → Properties* (see `docs/SETTINGS.md`).
5. **Alerts**: on the indicator, choose *Create alert → Condition: MEKA CRT PRO → "Any alert() function call"*. One alert covers every event, each event fires once, and the toggles are in input group ⑪. Turn on **JSON payloads** for a Telegram/webhook bot and paste your webhook URL. Individual `alertcondition` entries (MEKA · BUY confirmed, …) are also available.
6. To share with your partner privately, use *Publish → Invite-only* or share the source directly.

If you change the indicator code, regenerate the strategy:

```bash
python3 tools/build_strategy.py
```

## What you see on the chart

**Clean mode** (default): the current 1H CRT HIGH (red), LOW (green) and 50% (gold dashed); CRT sweep labels; BUY/SELL; entry, SL, TP1 and TP2 with risk/reward zones; the compact dashboard.

**Detailed mode** adds the 4H range (thicker), previous ranges, BSL/SSL pools (PDH/PDL, PWH/PWL, Asia/London/NY, 15M swings, EQH/EQL), all pool sweeps with zones, breakouts, 15M CHoCH/BOS, and optional premium/discount shading.

**Dashboard (Compact, default):** Bias (4H/1H) · Setup (model + what it waits for) · **Signal** (`BUY`/`SELL` only for an actionable trade, otherwise `WAIT` or `SETUP · NOT TRADABLE`, with the reason in the tooltip) · Entry · Stop (pts) · TP1 · TP2 (R) · Session (entries ON/OFF). Hover a value for details. *Dashboard style → Full* restores the diagnostic dashboard.

**Clean mode** hides minor event labels (fills, TP1 markers, 15M ticks, invalidation tags, every CRT sweep, pending guide lines, reference-candle segments). They are still computed, alerted and logged, and *Detailed* mode shows them.

Status values: `WATCHING RANGE`, `SWEEP IN PROGRESS`, `SWEEP CONFIRMED & RECLAIMED · WATCH LONG/SHORT`, `15M CONFIRMED · WATCH …`, `BUY/SELL CONFIRMED`, `TRADE ACTIVE`, `TP1 HIT · RUNNER ACTIVE`, `TP2 HIT`, `STOP HIT`, `BE STOP`, `EARLY EXIT`, and the no-trade endings `SETUP INVALIDATED` (structural), `SETUP CANCELLED · CONFLICT`, `MISSED ENTRY`, `SETUP EXPIRED`, `EXPIRED · SESSION CLOSED`, `SETUP REPLACED`, plus `IDLE · NO VALID RANGE`. The "Last setup" row always shows the latest ending in plain English. Turn on **Diagnostic log** for the last 20.

## Honesty notes

* No win rate, profit factor or accuracy is claimed. Measure them with the strategy as described in `docs/TESTING.md`.
* The code has been statically reviewed but **not compiled inside TradingView**, because no compiler is available outside it. Report any compiler message with its line number and it will be fixed.
