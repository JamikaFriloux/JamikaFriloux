# MEKA ALPHA PRO 4.0-r2 (research build)

Pine v6 indicator + companion strategy rebuilt from the audited MEKA ALPHA PRO v3. Trend filter + ICC (indication → correction → continuation) research hypothesis. Honest execution model, no performance claims.

**Not compiled in TradingView, not backtested.** See `MEKA_ALPHA_PRO_4_VALIDATION.md` for exactly what was checked.

| Start here | |
|---|---|
| Copy into TradingView | `MEKA_ALPHA_PRO_4_INDICATOR.pine`, `MEKA_ALPHA_PRO_4_STRATEGY.pine` |
| How it works / setup | `MEKA_ALPHA_PRO_4_GUIDE.md` |
| What was tested | `MEKA_ALPHA_PRO_4_VALIDATION.md` |
| v3 audit | `MEKA_ALPHA_PRO_v3_AUDIT.md` (original source: `MEKA_ALPHA_PRO_v3_SOURCE.pine`) |
| r1 → r2 changes | `CHANGELOG.md` |
| Brief | `MEKA_ALPHA_PRO_4_Claude_Brief.md` |

Developer commands (Python 3.9+):

```bash
python3 tools/build.py            # regenerate both .pine files from src/
python3 tools/build.py --check    # fail if the shipped files are stale
python3 -I tools/test_reference.py
pip install pynescript && python3 -I tools/parse_check.py MEKA_ALPHA_PRO_4_*.pine   # grammar only, slow
```
