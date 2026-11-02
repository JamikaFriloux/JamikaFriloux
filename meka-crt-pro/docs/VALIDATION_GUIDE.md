# How to export TradingView data for MEKA validation

The validation script (`tools/replay/validate.py`) replays every MEKA model separately: **A (CRT)**, **C (Range Break)**, **AMD**, and **FVG (research only)**. There is no Model B in the code. Each replay includes commissions, slippage, the entry windows, and an in-sample / out-of-sample split.

## 1. What to export

| Market | TradingView symbol | Timeframe | Minimum | Recommended |
|---|---|---|---|---|
| MNQ | `CME_MINI:MNQ1!` | **5 minutes** | 12 months + 45 days | 24 months or more |
| MGC | `COMEX:MGC1!` | **5 minutes** | 12 months + 45 days | 24 months or more |
| ES | `CME_MINI:ES1!` | **5 minutes** | 12 months + 45 days | 24 months or more |

* **Timeframe:** use 5 minutes. MEKA runs on a 5M chart, and 5M gives five times more history per export than 1M. 1M files also work (the script resamples them to 5M), but they cover far fewer days.
* **Date range:** the most recent data first, going back as far as you can. The first 45 days are only used to warm up the indicators (ATR(100), 4H EMA, swings) and are never scored. With at least 180 days of data the last 40% becomes the out-of-sample period. With 24 months, that is roughly the last 9–10 months.
* **Chart settings, before exporting:**
  * **Session: Extended / electronic trading hours** (*Chart settings → Symbol → Session*), not "Regular". MEKA needs the Asia and London sessions.
  * **Back-adjustment for contract rolls: ON** if your plan offers it (*Chart settings → Symbol → "Adjust for contract changes" / back-adjust*). If it is not available, export anyway; roll-day gaps then add a little noise.
  * Remove the other indicators from the chart. They don't break the import (extra columns are ignored), but they make the files bigger.

## 2. How to export

1. Open the symbol on a **5-minute** chart with the settings above.
2. Chart menu (⋯ / camera icon area) → **Export chart data…** → *Time format: **UNIX timestamp*** → Export. The file contains the bars currently loaded on the chart.
3. TradingView only loads a limited number of bars per chart, and the limit depends on your plan. To get more history:
   * press **Alt + G** (Go to date), jump back about 2–3 months, and let the chart load;
   * export again;
   * repeat until you reach the start date you want.
   * Let consecutive files **overlap by a few days**. The script merges and de-duplicates them.
4. Name the files clearly, e.g. `MNQ_5m_part1.csv`, `MNQ_5m_part2.csv`, …

### Required CSV columns
```
time,open,high,low,close,Volume
1725228000,20125.25,20131.50,20120.00,20128.75,3120
```
* `time` = UNIX seconds, the bar **open** time, in UTC. ISO times with an offset (e.g. `2025-03-04T09:30:00-05:00`) are also accepted.
* `open, high, low, close` are required. `Volume` is optional. Upper/lower case does not matter, and any other columns are ignored.

## 3. Run the validation

```bash
python3 tools/replay/validate.py --tv MNQ_5m_part1.csv,MNQ_5m_part2.csv,MNQ_5m_part3.csv:mnq --tv MGC_5m_part1.csv,MGC_5m_part2.csv:mgc --tv ES_5m_part1.csv,ES_5m_part2.csv:es
```

Optional: `--oos-from 2025-01-01` fixes the first out-of-sample day yourself. Pick it **before** looking at any results.

The output is `docs/VALIDATION_RESULTS.md`. For each market and period it contains:
* Per model: trades, win %, profit factor, net R, average R per trade, average win / loss, max drawdown in R, **net $ and max drawdown $ per 1 contract**, and the median stop in points and $.
* Long vs short and per session (London / NY / Asia / other).
* **The funnel of every setup that formed and how it ended** (failed setups included): planned stop hit, missed entry, conflict, expired, not tradable (window / stop / R:R), accepted breakout, expansion, and so on.

### Cost model used (per contract, round trip)
| Market | Tick / point value | Commission (assumed) | Slippage | Total in points |
|---|---|---|---|---|
| MNQ | 0.25 / $2 | $1.24 | 1 tick per side | 1.12 |
| MGC | 0.10 / $10 | $1.24 | 1 tick per side | 0.32 |
| ES | 0.25 / $50 | $4.50 | 1 tick per side | 0.59 |
| MES | 0.25 / $5 | $1.24 | 1 tick per side | 0.75 |

If your broker's all-in cost differs, edit `MK` at the top of `validate.py` **before** running. Never change it after looking at the results.

### Data-quality check
The report header shows the bar count per trading day. Electronic-hours futures should show **about 270–276 5M bars per day** (about 225 when weekend/holiday days are counted). A much lower number means the export was Regular-hours only or has gaps. Re-export with the Extended session.

## 4. Confirm in TradingView (companion strategy)

The replay is not TradingView's broker emulator. Confirm each result in the **Strategy Tester**:
1. Add `MEKA CRT PRO — Strategy` to the same 5M chart.
2. *Model traded by this strategy*: test **one model at a time** (A, C, AMD). FVG is research only.
3. *Properties*: commission = your broker's per-contract cost, slippage = 1 tick, sizing = Fixed 2 contracts (or Risk cash). Turn Bar Magnifier on if your plan has it.
4. *Trade from / until*: run the in-sample period, then the out-of-sample period **once**.
5. Note: trades, win %, profit factor, net profit, max drawdown, and the results table (All / Long / Short / sessions).

## 5. What to send back
The CSV files, or simply the generated `docs/VALIDATION_RESULTS.md`, plus the Strategy Tester summary for each model/market. No rule will be changed to improve historical results. Changes are made only for logic errors, and are then re-tested out-of-sample.
