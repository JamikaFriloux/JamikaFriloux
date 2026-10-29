# MEKA ALPHA PRO 4.0

Private TradingView trading assistant (Pine v6 indicator) plus a companion backtesting strategy. It uses a trend-following ICC (indication → correction → continuation) method and gives plain-English instructions: WAIT, WATCH, ENTER, HOLD, TAKE PROFIT, EXIT, NO TRADE. It covers Gold, Nasdaq-100, S&P 500, EUR/USD and USD/JPY, in Scalp and Day Trade modes.

**Not yet compiled by the author in TradingView; not backtested; no performance claims.** See `MEKA_ALPHA_PRO_4_VALIDATION.md`.

| | |
|---|---|
| Paste into TradingView | `MEKA_ALPHA_PRO_4_INDICATOR.pine`, `MEKA_ALPHA_PRO_4_STRATEGY.pine` |
| Install, settings, logic, limitations, checklist | `MEKA_ALPHA_PRO_4_GUIDE.md` |
| What was tested | `MEKA_ALPHA_PRO_4_VALIDATION.md` |
| v3 audit | `MEKA_ALPHA_PRO_v3_AUDIT.md` (source: `MEKA_ALPHA_PRO_v3_SOURCE.pine`) |
| Changes | `CHANGELOG.md` |

Developer commands (Python 3.9+):

```bash
python3 tools/build.py            # regenerate both .pine files from src/
python3 tools/build.py --check    # fail if the shipped files are stale
python3 -I tools/test_reference.py
pip install pynescript && python3 -I tools/parse_check.py MEKA_ALPHA_PRO_4_*.pine   # grammar only, slow
```
