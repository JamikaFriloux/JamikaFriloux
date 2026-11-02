#!/usr/bin/env python3
"""MEKA CRT PRO — cost-inclusive, out-of-sample validation of every model (logic replay).

Datasets (any of):
  --mgc  PATH   MGC 1-minute parquet/CSV, exchange time America/Chicago
  --mes  PATH   MES 1-minute parquet/CSV, exchange time America/Chicago
  --tv   PATH:MARKET   TradingView "Export chart data" CSV (time column = UNIX seconds), MARKET in mnq|mes|es|mgc|gc
  --gold PATH   XAUUSD 5M CSV (server time NY+7)

Each market is split chronologically into in-sample (first 60%) and out-of-sample (last 40%) unless the
dataset is shorter than 18 months (then reported as a single period). Defaults are NOT re-tuned per split.
Writes docs/VALIDATION_RESULTS.md. This is a replay of the Pine rules, not a TradingView backtest.
"""
import argparse
import math
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import amd as AMDm          # noqa: E402
import fvg_model as FM      # noqa: E402
import meka_replay as M     # noqa: E402
import model_c as C         # noqa: E402

SESS = dict(ASIA=("Asia/Tokyo", 900, 1500), LDN=("Europe/London", 800, 1630), NY=("America/New_York", 800, 1600))
IDX_WIN = [("America/New_York", 930, 1130)]
GOLD_WIN = [("Europe/London", 800, 1100), ("America/New_York", 830, 1130)]
# cost_pts = round-trip cost per contract in points: commission/pointvalue + 1 tick slippage per side
MK = {
    "mgc": dict(name="MGC (micro gold)", tick=0.1, pv=10.0, day_start_ny=18, cost_pts=1.24 / 10 + 0.2, windows=GOLD_WIN, sessions=SESS),
    "gc": dict(name="GC (gold)", tick=0.1, pv=100.0, day_start_ny=18, cost_pts=4.5 / 100 + 0.2, windows=GOLD_WIN, sessions=SESS),
    "mes": dict(name="MES (micro S&P)", tick=0.25, pv=5.0, day_start_ny=18, cost_pts=1.24 / 5 + 0.5, windows=IDX_WIN, sessions=SESS),
    "es": dict(name="ES (S&P)", tick=0.25, pv=50.0, day_start_ny=18, cost_pts=4.5 / 50 + 0.5, windows=IDX_WIN, sessions=SESS),
    "mnq": dict(name="MNQ (micro Nasdaq)", tick=0.25, pv=2.0, day_start_ny=18, cost_pts=1.24 / 2 + 0.5, windows=IDX_WIN, sessions=SESS),
    "gold": dict(name="XAUUSD (spot)", tick=0.01, pv=1.0, day_start_ny=17, cost_pts=0.30, windows=GOLD_WIN, sessions=SESS),
}


def load_1m(path, tz="America/Chicago", tv=False):
    """Load one or more files (comma-separated) of 1M or 5M OHLCV, merge, de-duplicate, resample to 5M."""
    if "," in path:
        parts = [load_1m(p.strip(), tz, tv) for p in path.split(",") if p.strip()]
        out = pd.concat(parts).drop_duplicates("utc", keep="last").sort_values("utc").reset_index(drop=True)
        return out
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    need = {"open", "high", "low", "close"}
    if not need <= set(df.columns) or ("time" not in df.columns and "datetime" not in df.columns):
        raise SystemExit(f"{path}: needs columns time (or datetime), open, high, low, close[, volume] — found {list(df.columns)}")
    if tv:
        t = pd.to_datetime(df["time"], unit="s", utc=True) if np.issubdtype(df["time"].dtype, np.number) else pd.to_datetime(df["time"], utc=True)
    else:
        t = pd.to_datetime(df["datetime"]).dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    x = pd.DataFrame({"utc": t, "o": df["open"], "h": df["high"], "l": df["low"], "c": df["close"], "v": df.get("volume", pd.Series(0, index=df.index))}).dropna(subset=["utc"])
    g = x.set_index("utc").resample("5min", label="left", closed="left")
    out = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "v": g.v.sum()}).dropna().reset_index()
    return out


def to_server(df):
    """meka_replay (Model A) expects broker server time = New York wall clock + 7h."""
    ny = df.utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return pd.DataFrame({"t": ny + pd.Timedelta(hours=7), "o": df.o.values, "h": df.h.values, "l": df.l.values, "c": df.c.values})


def stat(rs):
    if len(rs) == 0:
        return dict(n=0)
    R = np.asarray(rs, float)
    w, ls = R[R > 0], R[R <= 0]
    eq = np.r_[0, np.cumsum(R)]
    return dict(n=len(R), win=100 * len(w) / len(R), pf=(w.sum() / -ls.sum()) if ls.sum() < 0 else float("inf"),
                net=R.sum(), exp=R.mean(), avgW=w.mean() if len(w) else float("nan"), avgL=ls.mean() if len(ls) else float("nan"),
                dd=float(np.max(np.maximum.accumulate(eq) - eq)))


def row(label, s, extra=""):
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — | {extra} |"
    return f"| {label} | {s['n']} | {s['win']:.1f} | {s['pf']:.2f} | {s['net']:+.1f} | {s['exp']:+.3f} | {s['avgW']:+.2f} / {s['avgL']:+.2f} | {s['dd']:.1f} | {extra} |"


def session_of(ms_, mk):
    t = pd.Timestamp(ms_, unit="ms", tz="UTC")
    for nm in ("NY", "LDN", "ASIA"):
        tz, a, b = mk["sessions"][nm]
        hm = int(t.tz_convert(tz).strftime("%H%M"))
        if a <= hm < b:
            return nm
    return "OTHER"


def model_a(df, mk, a, b):
    M.WINDOWS = [(tz, f"{x:04d}-{y:04d}") for tz, x, y in mk["windows"]]
    P = dict(M.DEFAULTS, mintick=mk["tick"])
    sdf = to_server(df)
    srv_start = a.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
    res = M.run(sdf, P, "v2", start=str(srv_start))
    out = []
    lo = int(a.value // 10**6)
    hi = int(b.value // 10**6)
    from collections import Counter
    fn = Counter()
    for x in res["outcomes"]:
        ts0 = pd.Timestamp(x["t"]) - pd.Timedelta(hours=7)
        u0 = ts0.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
        if not pd.isna(u0) and lo <= int(u0.tz_convert("UTC").value // 10**6) < hi:
            fn[(x["cat"] + (": " + x["reason"] if x["cat"] != "TRADE" else "")).replace("traded through planned stop", "planned stop hit before entry")] += 1
        if x["cat"] == "TRADE" and x["risk"]:
            # sigT is server-time ms; convert back to UTC for the split
            ts = pd.Timestamp(x["sigT"], unit="ms") - pd.Timedelta(hours=7)
            u = int(ts.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC").value // 10**6) if not pd.isna(ts) else 0
            if lo <= u < hi:
                out.append(dict(Rnet=x["R"] - mk["cost_pts"] / x["risk"], dir=x["dir"], kT=u, risk=x["risk"]))
    return out, dict(fn.most_common(8))


def run_market(key, df, lines, oos_from=None):
    mk = MK[key]
    start, end = df.utc.min(), df.utc.max()
    span = (end - start).days
    warm = start + pd.Timedelta(days=45)          # indicator warm-up (ATR(100), 4H EMA, swings) — never scored
    if oos_from:
        cut = pd.Timestamp(oos_from, tz="UTC")
        periods = [("in-sample", warm, cut), ("out-of-sample", cut, end)]
    elif span >= 180:
        cut = warm + (end - warm) * 0.6
        periods = [("in-sample", warm, cut), ("out-of-sample", cut, end)]
    else:
        periods = [("single period (TOO SHORT for out-of-sample — export more history)", warm, end)]
    days = df.utc.dt.tz_convert("America/New_York").dt.date.nunique()
    lines += [f"\n## {mk['name']} — {start:%Y-%m-%d} → {end:%Y-%m-%d} ({len(df):,} 5M bars, {days} trading days, ~{len(df) / max(days, 1):.0f} bars/day)",
              f"Costs per round trip: {mk['cost_pts']:.3f} pts (= commission + 1 tick slippage per side; point value ${mk['pv']:g}). Entry windows: " +
              ", ".join(f"{tz.split('/')[-1]} {x:04d}-{y:04d}" for tz, x, y in mk["windows"]) + "."]
    t0 = time.time()
    D = C.prep(df, mk, dict(C.DEF))
    for pname, a, b in periods:
        tf, tt = int(a.value // 10**6), int(b.value // 10**6)
        lines += [f"\n### {pname}: {a:%Y-%m-%d} → {b:%Y-%m-%d}", "",
                  "| Model / variant | Trades | Win % | PF | Net R | Exp R/trade | Avg win / loss R | Max DD R | Net $ / Max DD $ (1 contract) · median stop |",
                  "|---|---|---|---|---|---|---|---|---|"]
        res, fun = {}, {}
        res["A · CRT (defaults)"], fun["A · CRT"] = model_a(df, mk, a, b)
        lines_b = "| B · (not implemented in the code) | — | — | — | — | — | — | — | there is no Model B in MEKA |"
        res["C · Range break (defaults)"], ce = C.run(D, mk, dict(C.DEF), tf, tt)
        fun["C · Range break"] = {"pairs locked": ce["locked"], "TRADE": ce[7], "invalidated (disqualified / filtered)": ce[9], "expired": ce[10], "not tradable (window / stop / R:R / trade open)": ce[11]}
        res["C · Range break (no bias filter)"] = C.run(D, mk, dict(C.DEF, bias="off"), tf, tt)[0]
        res["AMD · Asia → London/NY (defaults)"], ae = AMDm.run(df, mk, dict(AMDm.DEF), D, tf, tt)
        fun["AMD"] = dict(ae.most_common())
        res["AMD · + 4H/1H bias"] = AMDm.run(df, mk, dict(AMDm.DEF, bias="4H+1H"), D, tf, tt)[0]
        res["FVG · research only (signals OFF by default)"], fe = FM.run(df, mk, dict(FM.DEF), D, tf, tt)
        fun["FVG (research)"] = fe
        for k, tr in res.items():
            rs = [t["Rnet"] for t in tr]
            risk = [t["risk"] for t in tr]
            usd = [t["Rnet"] * t["risk"] * mk["pv"] for t in tr]
            eq = np.r_[0, np.cumsum(usd)]
            note = (f"${sum(usd):+,.0f} / ${float(np.max(np.maximum.accumulate(eq) - eq)):,.0f} · {np.median(risk):.2f} pts (${np.median(risk) * mk['pv']:.0f})") if risk else ""
            lines.append(row(k, stat(rs), note))
            if k.startswith("A ·"):
                lines.append(lines_b)
        lines += ["", "**Failed and completed setups (funnel)** — every setup the rules formed in this period, and how it ended:", ""]
        for k, f in fun.items():
            lines.append(f"* **{k}:** " + ", ".join(f"{n} {v}" for n, v in f.items() if v))
        lines += ["", "| Split (defaults) | Trades | Win % | PF | Net R | Exp R/trade | Avg win / loss R | Max DD R | |", "|---|---|---|---|---|---|---|---|---|"]
        for k in ["A · CRT (defaults)", "C · Range break (defaults)", "AMD · Asia → London/NY (defaults)"]:
            tr = res[k]
            short = k.split(" (")[0]
            for dn, dv in (("long", 1), ("short", -1)):
                lines.append(row(f"{short} · {dn}", stat([t["Rnet"] for t in tr if t["dir"] == dv])))
            for sn in ("LDN", "NY", "ASIA", "OTHER"):
                sub = [t["Rnet"] for t in tr if "kT" in t and session_of(t["kT"], mk) == sn]
                if sub:
                    lines.append(row(f"{short} · {sn}", stat(sub)))
    print(f"{key}: done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mgc")
    ap.add_argument("--mes")
    ap.add_argument("--gold")
    ap.add_argument("--tv", action="append", default=[], help="FILE[,FILE2,...]:MARKET  (TradingView export, UNIX time)")
    ap.add_argument("--oos-from", default=None, help="YYYY-MM-DD: first day of the out-of-sample period (default: last 40%%)")
    ap.add_argument("--out", default=__file__.rsplit("/tools/", 1)[0] + "/docs/VALIDATION_RESULTS.md")
    a = ap.parse_args()
    lines = ["# MEKA CRT PRO — Validation results (generated by tools/replay/validate.py)", "",
             "Logic replay of the Pine rules on real market data, costs included, defaults unchanged between periods. "
             "Not a TradingView backtest — confirm every result with the companion strategy before trusting it. "
             "R = multiples of the planned stop distance; results are per 1 contract, 50 % closed at TP1.", ""]
    if a.mgc:
        run_market("mgc", load_1m(a.mgc), lines, a.oos_from)
    if a.mes:
        run_market("mes", load_1m(a.mes), lines, a.oos_from)
    for spec in a.tv:
        path, key = spec.rsplit(":", 1)
        run_market(key, load_1m(path, tv=True), lines, a.oos_from)
    if a.gold:
        g = C.load("gold", a.gold)
        run_market("gold", g[g.utc >= pd.Timestamp("2023-01-01", tz="UTC")].reset_index(drop=True), lines)
    open(a.out, "w").write("\n".join(lines) + "\n")
    print("wrote", a.out)
