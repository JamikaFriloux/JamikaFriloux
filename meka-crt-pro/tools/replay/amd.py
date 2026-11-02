#!/usr/bin/env python3
"""MEKA CRT PRO — Model AMD (accumulation → manipulation → distribution) bar-for-bar replay.

Mirrors the Pine section "MODEL AMD": closed-bar decisions, signal at the distribution close,
fill at the next 5M open, stop-first exits, TP1 partial, per-trade costs, entry windows.
Logic replay on rebuilt data — not a TradingView backtest.

  python3 tools/replay/amd.py gold XAU_5m.csv
  python3 tools/replay/amd.py nq   NQ_1m.csv
"""
import math
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import meka_replay as M  # noqa: E402
import model_c as C      # noqa: E402

DEF = dict(len=24, rangeATR=3.0, compress=0.8, accExp=48, reclaim=2, accept=2, maxSweep=2.0, distExp=24,
           dispATR=1.0, distLvl="opposite", struct=False, bias="off", stopMode="extreme", stopTk=2, maxRisk=4.0,
           tp1R=1.0, tp2R=2.0, minRR=1.5, needWin=True, tp1Pct=50.0, sweepTicks=1, rcl15=True, capMode="range")


def run(df, mk, P, D, t_from=None, t_to=None, stop_at=None):
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    n = len(df) if stop_at is None else stop_at
    atr = M.atr(h, l, c)
    atrS = M.atr(h, l, c, 100)
    L = P["len"]
    hiN = pd.Series(h).rolling(L).max().values
    loN = pd.Series(l).rolling(L).min().values
    ph5, pl5 = M.pivots(h, 3, 2, True), M.pivots(l, 3, 2, False)
    tick = mk["tick"]
    pen = P["sweepTicks"] * tick
    tms = (df.utc.astype("int64") // 1).values  # only for in-range checks via index below
    utc = df.utc
    inR = np.ones(len(df), bool)
    if t_from is not None:
        ms_ = M.ms(utc.dt.tz_convert("UTC").dt.tz_localize(None).values)
        inR = (ms_ >= t_from) & (ms_ < t_to)
    swH = swL = np.nan
    swHB = swLB = True
    A = dict(state=0)
    T = None
    lastEnd = None
    trades, ends = [], Counter()
    w1 = P["tp1Pct"] / 100

    def end(st, why):
        A.update(state=st, why=why, endBar=i)
        if A.get("inR", True):
            ends[why if st != 7 else "TRADE"] += 1

    for i in range(n):
        bull5 = bear5 = False
        if not math.isnan(ph5[i]):
            swH, swHB = ph5[i], False
        if not math.isnan(pl5[i]):
            swL, swLB = pl5[i], False
        if not swHB and c[i] > swH:
            swHB, bull5 = True, True
        if not swLB and c[i] < swL:
            swLB, bear5 = True, True
        a = atr[i]
        # trade lifecycle
        if T is not None:
            if T["state"] == 5 and i > T["sig"]:
                T.update(state=6, entry=o[i])
            if T["state"] == 6:
                d = T["dir"]
                if (l[i] <= T["stop"]) if d == 1 else (h[i] >= T["stop"]):
                    xp = min(o[i], T["stop"]) if d == 1 else max(o[i], T["stop"])
                    rl = d * (xp - T["entry"]) / T["risk"]
                    T["R"] = T["R"] + (1 - w1) * rl if T["tp1"] else rl
                    T["state"] = 8
                else:
                    if not T["tp1"] and ((h[i] >= T["t1"]) if d == 1 else (l[i] <= T["t1"])):
                        T["tp1"] = True
                        T["R"] = w1 * d * (T["t1"] - T["entry"]) / T["risk"]
                    if T["tp1"] and ((h[i] >= T["t2"]) if d == 1 else (l[i] <= T["t2"])):
                        T["R"] += (1 - w1) * d * (T["t2"] - T["entry"]) / T["risk"]
                        T["state"] = 8
                if T["state"] == 8:
                    T["Rnet"] = T["R"] - mk["cost_pts"] / T["risk"]
                    if T["inR"]:
                        trades.append(T)
        buf = P["stopTk"] * tick
        # manipulation watch
        if A["state"] == 1 and i > A["lock"]:
            upB, dnB = h[i] - A["hi"] >= pen, A["lo"] - l[i] >= pen
            if upB and dnB:
                end(9, "both sides same candle")
            elif upB or dnB:
                A.update(state=2, side=1 if upB else -1, ext=h[i] if upB else l[i], mBar=i, out=0)
            elif i - A["lock"] > P["accExp"]:
                end(10, "no manipulation")
        if A["state"] == 2:
            A["ext"] = max(A["ext"], h[i]) if A["side"] == 1 else min(A["ext"], l[i])
            depth = A["ext"] - A["hi"] if A["side"] == 1 else A["lo"] - A["ext"]
            back = c[i] < A["hi"] if A["side"] == 1 else c[i] > A["lo"]
            out = c[i] > A["hi"] if A["side"] == 1 else c[i] < A["lo"]
            evalNow = (not P["rcl15"]) or D["last"][i]   # 15M mode: judge only on a completed 15M close
            win = P["reclaim"] * (3 if P["rcl15"] else 1)
            if not evalNow:
                back = out = False
            if depth > P["maxSweep"] * a:
                end(9, "expansion (too deep)")
            elif back:
                A.update(state=3, dir=-A["side"], conf=i, structOK=False)
                if A.get("inR", True):
                    ends["manipulation confirmed"] += 1
            else:
                if out:
                    A["out"] += 1
                if A["out"] >= P["accept"] or i - A["mBar"] + 1 >= win:
                    end(9, "accepted breakout")
        # distribution
        if A["state"] == 3 and i > A["conf"]:
            d = A["dir"]
            mid = (A["hi"] + A["lo"]) / 2
            if bull5 if d == 1 else bear5:
                A["structOK"] = True
            lost = l[i] < A["ext"] if d == 1 else h[i] > A["ext"]
            disp = (c[i] > o[i] and c[i] - o[i] >= P["dispATR"] * a) if d == 1 else (c[i] < o[i] and o[i] - c[i] >= P["dispATR"] * a)
            lvl = mid if P["distLvl"] == "mid" else (A["hi"] if d == 1 else A["lo"])
            beyond = c[i] > lvl if d == 1 else c[i] < lvl
            if lost:
                end(9, "manipulation extreme broken")
            elif disp and beyond and (not P["struct"] or A["structOK"]):
                why = ""
                b4, b1 = D["b4"][i], D["b1"][i]
                if P["bias"] == "4H+1H" and (b4 != b1 or b4 != d):
                    why = "bias"
                elif not (D["win"][i] or not P["needWin"]):
                    why = "entries off"
                elif T is not None and T["state"] in (5, 6):
                    why = "trade open"
                e = c[i]
                stp = (mid - d * buf) if P["stopMode"] == "mid" else ((l[i] - buf) if d == 1 else (h[i] + buf)) if P["stopMode"] == "candle" else ((A["ext"] - buf) if d == 1 else (A["ext"] + buf))
                risk = d * (e - stp)
                if not why and risk <= 0:
                    why = "beyond stop"
                elif not why and risk > (P["maxRisk"] * a if P["capMode"] == "atr" else (A["hi"] - A["lo"]) + P["maxSweep"] * a + buf):
                    why = "stop too wide"
                if why:
                    end(11, "not tradable: " + why)
                else:
                    T = dict(state=5, dir=d, sig=i, stop=stp, risk=risk, t1=e + d * P["tp1R"] * risk, t2=e + d * P["tp2R"] * risk,
                             tp1=False, R=0.0, inR=bool(inR[i]), bar=i)
                    end(7, "trade")
            elif i - A["conf"] > P["distExp"]:
                end(10, "no distribution")
        # accumulation detection
        if A["state"] == 0 or A["state"] >= 7:
            ws = i - L + 1
            fresh = (lastEnd is None or ws > lastEnd) and (A["state"] < 7 or ws > A["endBar"])
            if fresh and not math.isnan(atrS[i]) and not math.isnan(hiN[i]) and hiN[i] - loN[i] <= P["rangeATR"] * atrS[i] and a <= P["compress"] * atrS[i]:
                A = dict(state=1, hi=hiN[i], lo=loN[i], lock=i, inR=bool(inR[i]))
                lastEnd = i
                if A["inR"]:
                    ends["accumulation locked"] += 1
        if A["state"] >= 7 and A.get("endBar") is not None:
            lastEnd = max(lastEnd or 0, A["endBar"])
    return trades, ends


def stats_line(name, tr):
    return C.fmt(C.stats(tr, name)).split("avgW")[0] + (f"| avg R gross {np.mean([t['R'] for t in tr]):+.3f}" if tr else "")


if __name__ == "__main__":
    kind, path = sys.argv[1], sys.argv[2]
    mk = C.MARKETS[kind]
    df = C.load(kind, path)
    periods = {"gold": [("IS 2023-02→2024-02", "2023-02-01", "2024-02-01"), ("OOS 2024-02→2025-02", "2024-02-01", "2025-02-01")],
               "nq": [("NQ 2008-01→2008-05", "2008-01-01", "2008-06-01")]}[kind]
    lo_t = pd.Timestamp(periods[0][1], tz="UTC") - pd.Timedelta(days=40)
    df = df[(df.utc >= lo_t) & (df.utc < pd.Timestamp(periods[-1][2], tz="UTC"))].reset_index(drop=True)
    D = C.prep(df, mk, dict(C.DEF))
    variants = [("DEFAULT (raw, entry windows)", dict(DEF)),
                ("+ 4H+1H bias", dict(DEF, bias="4H+1H")),
                ("+ structure confirmation", dict(DEF, struct=True)),
                ("distribution close beyond midpoint", dict(DEF, distLvl="mid")),
                ("stop = range midpoint", dict(DEF, stopMode="mid")),
                ("stop = displacement candle", dict(DEF, stopMode="candle")),
                ("no entry windows (any time)", dict(DEF, needWin=False))]
    print(f"{kind}: {len(df)} 5M bars · cost {mk['cost_pts']} pts/trade")
    for pname, a, b in periods:
        tf = int(pd.Timestamp(a, tz="UTC").value // 10**6)
        tt = int(pd.Timestamp(b, tz="UTC").value // 10**6)
        print(f"\n######## {pname} ########")
        for name, P in variants:
            tr, ends = run(df, mk, P, D, tf, tt)
            print(stats_line(name, tr))
            if name.startswith("DEFAULT"):
                print("   funnel:", dict(ends.most_common()))
                for dn, dv in (("long", 1), ("short", -1)):
                    print("   " + stats_line("  " + dn, [t for t in tr if t["dir"] == dv]))
