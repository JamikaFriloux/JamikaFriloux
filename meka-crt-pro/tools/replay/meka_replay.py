#!/usr/bin/env python3
"""MEKA CRT PRO — bar-for-bar Python replay of the Pine engine (diagnostic harness).

Purpose: measure WHY setups end (invalidation reasons), compare engine versions,
and run a no-future-information (repaint) test. This is a faithful port of the
Pine logic, not TradingView itself: HTF candles are rebuilt from the 5M data, so
bucket boundaries/ATR seeds can differ slightly from a TradingView feed.

Input CSV: Date;Open;High;Low;Close;Volume with broker server time = New York + 7h
(the common MT4 "NY close = 00:00" convention). Usage:

  python3 tools/replay/meka_replay.py DATA.csv --start 2024-02-01 --end 2025-02-01 --version v2
"""
import argparse
import json
import math
import sys
from collections import Counter

import numpy as np
import pandas as pd

NaN = float("nan")


def isnan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


# ───────────────────────────── settings (indicator defaults) ─────────────────────────────
DEFAULTS = dict(
    minRangeATR=0.35, maxRangeATR=3.0, rangeMaxAge=2, src4=True, src1=True, usePools=True,
    sweepTicks=1, reclaimBars=6, acceptBars=3, maxSweepATR=3.0,
    confMode="MSS or Displacement", reqChoch=False, pivL15=3, pivR15=2, dispMult=0.8, confExpiry=48,
    trigMode="Break or Retest", pivL5=3, pivR5=2, retestTol=0.15, entryExpiry=24, maxRiskATR=4.0,
    reqDiscount=True, htfFilter=True,
    stopBufATR=0.10, stopBufTk=2, minRR=2.0, tp1Mode="CRT 50%", tp1MinR=0.8, tp1R=1.0,
    tp2Mode="Opposite CRT / liquidity", tp2R=2.0, tp1Pct=50.0, useBE=False, maxBars=0, wickInval=True,
    trackPD=True, trackPW=True, trackSess=True, trackSw=True, eqTolATR=0.10, poolMax=8, poolDays=3,
    mintick=0.01, primHigh=False,
    # v2-only
    pairBars=12, invalAtStop=True, pairedConfirm=True, roomCheck=True,
    reclaimTF="15M", reclaimWin15=2, reclaimWinRef=1, conflictInval=True, extLook=2,
)
# Market preset for GOLD (Pine: usePresetWin = true)
WINDOWS = [("Europe/London", "0800-1100"), ("America/New_York", "0830-1130")]
SESS = {"ASIA": ("Asia/Tokyo", "0900-1500"), "LDN": ("Europe/London", "0800-1630"), "NY": ("America/New_York", "0800-1600")}


def in_sess(minutes_of_day, spec):
    a, b = spec.split("-")
    s = int(a[:2]) * 60 + int(a[2:])
    e = int(b[:2]) * 60 + int(b[2:])
    return (minutes_of_day >= s) & (minutes_of_day < e) if s < e else (minutes_of_day >= s) | (minutes_of_day < e)


# ───────────────────────────── series helpers (Pine semantics) ─────────────────────────────
def atr(h, l, c, n=14):
    tr = np.empty(len(h))
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    out = np.full(len(h), NaN)
    if len(h) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(h)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def pivots(x, L, R, high):
    n = len(x)
    out = np.full(n, NaN)
    for i in range(L + R, n):
        c = i - R
        v = x[c]
        left = x[c - L:c]
        right = x[c + 1:i + 1]
        if high and v > left.max() and v > right.max():
            out[i] = v
        if (not high) and v < left.min() and v < right.min():
            out[i] = v
    return out


def ms(ts):
    return (ts.astype("datetime64[ns]").astype("int64") // 1_000_000)


# ───────────────────────────── data & multi-timeframe (expr[1] + lookahead_on) ─────────────────────────────
def load(path, start, end, warm_days=40):
    df = pd.read_csv(path, sep=";")
    df["t"] = pd.to_datetime(df["Date"], format="%Y.%m.%d %H:%M")
    t0 = pd.Timestamp(start) - pd.Timedelta(days=warm_days)
    df = df[(df.t >= t0) & (df.t < pd.Timestamp(end))].reset_index(drop=True)
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c"})
    return df


def htf(df, key):
    """Aggregate chart bars into HTF candles keyed by `key`; return per-chart-bar arrays of the
    PREVIOUS completed candle (exactly what request.security(expr[1], lookahead_on) returns)."""
    g = df.groupby(key, sort=True)
    agg = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    agg["t"] = agg.index
    a = atr(agg.h.values, agg.l.values, agg.c.values)
    idx = agg.index.get_indexer(key)  # bucket index for each chart bar
    prev = idx - 1
    ok = prev >= 0
    def take(arr):
        out = np.full(len(df), NaN)
        out[ok] = arr[prev[ok]]
        return out
    tms = ms(agg.t.values).astype(float)
    def prior(arr, k, fn):
        out = np.full(len(df), NaN)
        if k <= 0:
            return out
        roll = getattr(pd.Series(arr).rolling(k), fn)().values  # window ending at candle j
        p2 = idx - 2
        ok2 = p2 >= 0
        out[ok2] = roll[p2[ok2]]
        return out
    return dict(H=take(agg.h.values), L=take(agg.l.values), T=take(tms), ATR=take(a), idx=idx, agg=agg,
                PH=lambda k: prior(agg.h.values, k, "max"), PL=lambda k: prior(agg.l.values, k, "min"))


def struct15(agg, L, R, dm):
    """Port of f_struct, evaluated on 15M candles. Returns list of dicts per 15M candle (un-shifted)."""
    h, l, o, c = agg.h.values, agg.l.values, agg.o.values, agg.c.values
    t = ms(agg.t.values)
    tc = t + 15 * 60_000
    ph = pivots(h, L, R, True)
    pl = pivots(l, L, R, False)
    a = atr(h, l, c)
    st = dict(swH=NaN, swL=NaN, swHT=None, swLT=None, swHB=True, swLB=True, trend=0,
              bullT=None, bullLvl=NaN, bullPT=None, bullCh=False, bullDs=False,
              bearT=None, bearLvl=NaN, bearPT=None, bearCh=False, bearDs=False, bullDT=None, bearDT=None)
    out = []
    for i in range(len(h)):
        disp = (not math.isnan(a[i])) and abs(c[i] - o[i]) >= dm * a[i]
        if not math.isnan(ph[i]):
            st.update(swH=ph[i], swHT=int(t[i - R]), swHB=False)
        if not math.isnan(pl[i]):
            st.update(swL=pl[i], swLT=int(t[i - R]), swLB=False)
        if not st["swHB"] and c[i] > st["swH"]:
            st.update(swHB=True, bullCh=st["trend"] <= 0, bullDs=disp and c[i] > o[i], trend=1,
                      bullT=int(tc[i]), bullLvl=st["swH"], bullPT=st["swHT"])
        if not st["swLB"] and c[i] < st["swL"]:
            st.update(swLB=True, bearCh=st["trend"] >= 0, bearDs=disp and c[i] < o[i], trend=-1,
                      bearT=int(tc[i]), bearLvl=st["swL"], bearPT=st["swLT"])
        if i > 0 and c[i] > o[i] and disp and c[i] > h[i - 1]:
            st["bullDT"] = int(tc[i])
        if i > 0 and c[i] < o[i] and disp and c[i] < l[i - 1]:
            st["bearDT"] = int(tc[i])
        out.append(dict(st))
    return out


# ───────────────────────────── engine objects ─────────────────────────────
class Liq:
    __slots__ = ("price", "side", "kind", "tf", "isCRT", "hiTF", "rHi", "rLo", "rT0", "state", "breachBar",
                 "breachTime", "ext", "beyond", "resolvedBar", "created", "expires", "retired", "aligned", "fav", "tfCnt", "pend")

    def __init__(self, price, side, kind, created, expires=None, tf="", isCRT=False, hiTF=False, rHi=NaN, rLo=NaN, rT0=None):
        self.price, self.side, self.kind, self.created, self.expires = price, side, kind, created, expires
        self.tf, self.isCRT, self.hiTF, self.rHi, self.rLo, self.rT0 = tf, isCRT, hiTF, rHi, rLo, rT0
        self.state, self.breachBar, self.breachTime, self.ext, self.beyond = 0, None, None, NaN, 0
        self.resolvedBar, self.retired, self.aligned = None, False, False
        self.fav, self.tfCnt, self.pend = NaN, 0, False


class Rng:
    def __init__(self, tf):
        self.tf, self.hi, self.lo, self.mid, self.t0 = tf, NaN, NaN, NaN, None
        self.age, self.active, self.lastFail, self.hiLiq, self.loLiq = 0, False, False, None, None


class Setup:
    def __init__(self, **kw):
        self.state = 0
        self.dir = 0
        self.__dict__.update(kw)


# ───────────────────────────── the engine ─────────────────────────────
def run(df, P, version="v2", start=None, log=None, stop_at=None):
    v2 = version == "v2"
    n = len(df)
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    t_srv = df.t
    tms = ms(t_srv.values)
    ny_wall = t_srv - pd.Timedelta(hours=7)
    utc = ny_wall.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    def mod(tz):
        lt = utc.dt.tz_convert(tz)
        return (lt.dt.hour * 60 + lt.dt.minute).fillna(-1).values
    mods = {tz: mod(tz) for tz in {"Asia/Tokyo", "Europe/London", "America/New_York"}}
    inS = {k: in_sess(mods[tz], s) for k, (tz, s) in SESS.items()}
    entryOK = np.zeros(n, bool)
    for tz, s in WINDOWS:
        entryOK |= in_sess(mods[tz], s)

    k15 = t_srv.dt.floor("15min")
    k1 = t_srv.dt.floor("1h")
    k4 = t_srv.dt.floor("4h")       # server time buckets → 17/21/01/05/09/13 NY
    kD = t_srv.dt.floor("1D")       # → 17:00 NY daily
    kW = (t_srv.dt.floor("1D") - pd.to_timedelta(t_srv.dt.weekday, unit="D"))
    X4, X1, XD, XW = htf(df, k4), htf(df, k1), htf(df, kD), htf(df, kW)
    K = P["extLook"] if v2 else 0
    PH4, PL4, PH1, PL1 = X4["PH"](K), X4["PL"](K), X1["PH"](K), X1["PL"](K)
    X15 = htf(df, k15)
    s15 = struct15(X15["agg"], P["pivL15"], P["pivR15"], P["dispMult"])
    i15 = X15["idx"] - 1  # [1] shift → last completed 15M candle
    def closes(X, mins):
        agg = X["agg"]; prev = X["idx"] - 1; ok = prev >= 0
        cc = np.full(n, NaN); tc = np.full(n, NaN)
        cc[ok] = agg.c.values[prev[ok]]; tc[ok] = ms(agg.t.values)[prev[ok]] + mins * 60_000
        new = np.r_[False, X["idx"][1:] != X["idx"][:-1]]
        return cc, tc, new
    CL = {"15M": closes(X15, 15), "1H": closes(X1, 60), "4H": closes(X4, 240)}
    lastBull5 = lastBear5 = -10**9

    atrE = atr(h, l, c)
    ph5 = pivots(h, P["pivL5"], P["pivR5"], True)
    pl5 = pivots(l, P["pivL5"], P["pivR5"], False)
    mt = P["mintick"]
    minPen = P["sweepTicks"] * mt
    w1 = P["tp1Pct"] / 100.0
    dayMs = 86_400_000

    pools = []
    r4, r1 = Rng("4H"), Rng("1H")
    S = Setup()
    h4Bias = 0
    sw5H = sw5L = NaN
    sw5HB = sw5LB = True
    sess_state = {k: dict(sH=NaN, sL=NaN, sT=None) for k in SESS}
    outcomes, signals, blocks, rejects = [], [], Counter(), Counter()
    alive_across_roll = Counter()
    start_ms = ms(np.array([np.datetime64(pd.Timestamp(start))]))[0] if start else -1
    end_i = n if stop_at is None else stop_at

    def rec(Sx, cat, why):
        Sx.cat, Sx.reason, Sx.doneBar = cat, why, i
        if Sx.created_ms >= start_ms:
            outcomes.append(dict(t=str(t_srv[Sx.reclaimBar]), dir=Sx.dir, src=Sx.srcKind, cat=cat, reason=why,
                                 bars=i - Sx.reclaimBar, conf15=Sx.confBar is not None,
                                 rolls=Sx.rolls, R=getattr(Sx, "resultR", None), crBar=Sx.reclaimBar,
                                 inval=Sx.invalLvl, mid=Sx.rMid, lvl=Sx.level, ext=Sx.ext, rng=Sx.rHi - Sx.rLo,
                                 atr=float(atrE[Sx.reclaimBar]), depth=abs(Sx.ext - Sx.level)))

    def nearest(side, frm, minDist, maxP):
        best, bk = NaN, ""
        for q in pools:
            if q.state == 0 and not q.retired and q.side == side:
                dist = side * (q.price - frm)
                inCap = isnan(maxP) or side * (maxP - q.price) >= 0
                if dist >= minDist and inCap and (isnan(best) or dist < side * (best - frm)):
                    best, bk = q.price, q.kind
        return best, bk

    def targets(d, entry, risk, rHi, rLo, rMid, rTF):
        opp = rHi if d == 1 else rLo
        tp2, tp2s = NaN, ""
        if P["tp2Mode"] == "R multiple":
            tp2, tp2s = entry + d * P["tp2R"] * risk, "R"
        elif d * (opp - entry) >= P["minRR"] * risk:
            tp2, tp2s = opp, rTF + " CRT"
        else:
            px, kx = nearest(d, entry, P["minRR"] * risk, opp + d * (rHi - rLo))
            if not isnan(px):
                tp2, tp2s = px, kx
        tp1, tp1s = NaN, ""
        if not isnan(tp2):
            if P["tp1Mode"] == "R multiple":
                tp1 = entry + d * P["tp1R"] * risk
            else:
                if P["tp1Mode"] == "CRT 50%" and d * (rMid - entry) >= P["tp1MinR"] * risk and d * (tp2 - rMid) > 0:
                    tp1, tp1s = rMid, "CRT 50%"
                if isnan(tp1):
                    p1, k1_ = nearest(d, entry, P["tp1MinR"] * risk, tp2)
                    if not isnan(p1) and d * (tp2 - p1) > 0:
                        tp1, tp1s = p1, k1_
                if isnan(tp1):
                    tp1 = entry + d * P["tp1R"] * risk
            if d * (tp2 - tp1) <= 0:
                tp1 = entry + (tp2 - entry) * 0.5
        return tp1, tp2, tp1s, tp2s

    def add_pool(p, side, kind, tol, expT, isSwing):
        if isnan(p):
            return
        for q in pools:
            if not q.isCRT and q.state == 0 and q.side == side and abs(q.price - p) <= tol:
                if isSwing and ("SWING" in q.kind or q.kind.startswith("EQ")):
                    q.kind = "EQH" if side == 1 else "EQL"
                    q.price = max(q.price, p) if side == 1 else min(q.price, p)
                elif kind not in q.kind:
                    q.kind += " + " + kind
                q.expires = max(q.expires, expT)
                return
        pools.append(Liq(p, side, kind, int(tms[i]), expT))
        cnt = [q for q in pools if not q.isCRT and q.state == 0 and q.side == side]
        while len(cnt) > P["poolMax"]:
            oldest = min(cnt, key=lambda q: q.created)
            pools.remove(oldest)
            cnt.remove(oldest)

    def roll(r, hi, lo, t0, atrH, isHigh, ph=NaN, pl=NaN):
        rng = hi - lo
        valid = not isnan(hi) and not isnan(atrH) and rng > 0 and P["minRangeATR"] * atrH <= rng <= P["maxRangeATR"] * atrH
        if valid:
            if r.active:
                r.hiLiq.retired = r.loLiq.retired = True
            r.hi, r.lo, r.mid, r.t0, r.age, r.active, r.lastFail = hi, lo, (hi + lo) / 2, t0, 0, True, False
            r.hiLiq = Liq(hi, 1, r.tf + " CRT HIGH", int(tms[i]), None, r.tf, True, isHigh, hi, lo, t0)
            r.loLiq = Liq(lo, -1, r.tf + " CRT LOW", int(tms[i]), None, r.tf, True, isHigh, hi, lo, t0)
            pools.extend([r.hiLiq, r.loLiq])
            r.hiLiq.aligned = isnan(ph) or hi > ph   # 'aligned' reused as: boundary is EXTERNAL liquidity
            r.loLiq.aligned = isnan(pl) or lo < pl
        else:
            r.lastFail = True
            r.age += 1
            if r.active and r.age > P["rangeMaxAge"]:
                r.hiLiq.retired = r.loLiq.retired = True
                r.active = False

    def process(q):
        ev = 0
        if q.state == 0:
            br = (h[i] - q.price >= minPen - mt * 0.01) if q.side == 1 else (q.price - l[i] >= minPen - mt * 0.01)
            if br:
                q.state, q.breachBar, q.breachTime, q.ext, q.beyond, ev = 1, i, int(tms[i]), (h[i] if q.side == 1 else l[i]), 0, 1
        elif q.state == 1:
            q.ext = max(q.ext, h[i]) if q.side == 1 else min(q.ext, l[i])
        if q.state == 1:
            q.fav = (max(q.fav, h[i]) if not isnan(q.fav) else h[i]) if q.side == -1 else (min(q.fav, l[i]) if not isnan(q.fav) else l[i])
        if q.state == 1 and v2 and P["reclaimTF"] != "CHART":
            tfk = (q.tf if (P["reclaimTF"] == "REF" and q.isCRT) else "15M")
            cc, tc, new = CL[tfk]
            q.pend = (c[i] < q.price) if q.side == 1 else (c[i] > q.price)
            if new[i] and tc[i] > q.breachTime:
                back = cc[i] < q.price if q.side == 1 else cc[i] > q.price
                if back:
                    q.state, q.resolvedBar, ev = 2, i, 2
                else:
                    q.tfCnt += 1
                    win = P["reclaimWinRef"] if tfk != "15M" else P["reclaimWin15"]
                    if q.tfCnt >= win:
                        q.state, q.resolvedBar, ev = 3, i, 3
            return ev
        if q.state == 1:
            back = c[i] < q.price if q.side == 1 else c[i] > q.price
            bey = c[i] > q.price if q.side == 1 else c[i] < q.price
            if back:
                q.state, q.resolvedBar, ev = 2, i, 2
            else:
                if bey:
                    q.beyond += 1
                if q.beyond >= P["acceptBars"] or i - q.breachBar + 1 >= P["reclaimBars"]:
                    q.state, q.resolvedBar, ev = 3, i, 3
        return ev

    for i in range(end_i):
        bull5 = bear5 = False
        if not math.isnan(ph5[i]):
            sw5H, sw5HB = ph5[i], False
        if not math.isnan(pl5[i]):
            sw5L, sw5LB = pl5[i], False
        if not sw5HB and c[i] > sw5H:
            sw5HB, bull5 = True, True
            lastBull5 = i
        if not sw5LB and c[i] < sw5L:
            sw5LB, bear5 = True, True
            lastBear5 = i

        new4 = i > 0 and X4["idx"][i] != X4["idx"][i - 1]
        new1 = i > 0 and X1["idx"][i] != X1["idx"][i - 1]
        if new4:
            roll(r4, X4["H"][i], X4["L"][i], X4["T"][i], X4["ATR"][i], True, PH4[i], PL4[i])
        if new1:
            roll(r1, X1["H"][i], X1["L"][i], X1["T"][i], X1["ATR"][i], False, PH1[i], PL1[i])
        if (new4 or new1) and S.state in (3, 4):
            S.rolls += 1
        pr = (r4 if r4.active else r1) if P["primHigh"] else (r1 if r1.active else r4)

        tol = P["eqTolATR"] * (atrE[i] if not math.isnan(atrE[i]) else 0)
        expD = int(tms[i]) + P["poolDays"] * dayMs
        if P["trackPD"] and i > 0 and XD["idx"][i] != XD["idx"][i - 1]:
            add_pool(XD["H"][i], 1, "PDH", tol, expD, False)
            add_pool(XD["L"][i], -1, "PDL", tol, expD, False)
        if P["trackPW"] and i > 0 and XW["idx"][i] != XW["idx"][i - 1]:
            add_pool(XW["H"][i], 1, "PWH", tol, int(tms[i]) + 3 * P["poolDays"] * dayMs, False)
            add_pool(XW["L"][i], -1, "PWL", tol, int(tms[i]) + 3 * P["poolDays"] * dayMs, False)
        if P["trackSess"] and i > 0:
            for k in SESS:
                ss = sess_state[k]
                a, b = inS[k][i], inS[k][i - 1]
                if not a and b and not isnan(ss["sH"]):
                    add_pool(ss["sH"], 1, k + " H", tol, expD, False)
                    add_pool(ss["sL"], -1, k + " L", tol, expD, False)
                if a and not b:
                    ss.update(sH=h[i], sL=l[i])
                elif a:
                    ss.update(sH=max(ss["sH"], h[i]), sL=min(ss["sL"], l[i]))
        j = i15[i]
        st15 = s15[j] if j >= 0 else None
        stp15 = s15[i15[i - 1]] if i > 0 and i15[i - 1] >= 0 else None
        if P["trackSw"] and st15 is not None:
            if st15["swHT"] is not None and (stp15 is None or stp15["swHT"] != st15["swHT"]):
                add_pool(st15["swH"], 1, "15M SWING H", tol, expD, True)
            if st15["swLT"] is not None and (stp15 is None or stp15["swLT"] != st15["swLT"]):
                add_pool(st15["swL"], -1, "15M SWING L", tol, expD, True)

        # sweeps
        best, bestScore, bHi, bLo, bTF, bT0 = None, 0, NaN, NaN, "", None
        for q in list(pools):
            if q.retired and q.state != 1:
                continue
            ev = process(q)
            if ev == 2:
                qual, score = False, 0
                if q.isCRT:
                    if (P["src4"] if q.hiTF else P["src1"]) and (q.aligned or not v2):
                        qual, score, qHi, qLo, qTF, qT0 = True, (3 if q.hiTF else 2), q.rHi, q.rLo, q.tf, q.rT0
                elif P["usePools"] and pr.active:
                    q.aligned = q.price >= pr.mid if q.side == 1 else q.price <= pr.mid
                    if q.aligned:
                        qual, score, qHi, qLo, qTF, qT0 = True, 1, pr.hi, pr.lo, pr.tf, pr.t0
                qual = qual and abs(q.ext - q.price) <= P["maxSweepATR"] * atrE[i]
                if qual and score > bestScore:
                    best, bestScore, bHi, bLo, bTF, bT0 = q, score, qHi, qLo, qTF, qT0

        h4Bias = 0
        if r4.active:
            bu = r4.loLiq.state == 2 or r4.hiLiq.state == 3
            bd = r4.hiLiq.state == 2 or r4.loLiq.state == 3
            h4Bias = 1 if bu and not bd else -1 if bd and not bu else 0

        # fill
        if S.state == 5 and i > S.sigBar:
            S.entry, S.fillBar, S.state = o[i], i, 6
        # manage
        if S.state == 6:
            d = S.dir
            outc = ""
            if (l[i] <= S.stop) if d == 1 else (h[i] >= S.stop):
                xp = min(o[i], S.stop) if d == 1 else max(o[i], S.stop)
                rl = d * (xp - S.entry) / S.riskRef
                S.resultR = S.resultR + (1 - w1) * rl if S.tp1Done else rl
                outc = "BE STOP" if S.tp1Done and S.beOn else "STOP HIT"
            else:
                hit1 = (not S.tp1Done) and ((h[i] >= S.tp1) if d == 1 else (l[i] <= S.tp1))
                if hit1:
                    S.tp1Done = True
                    S.resultR = w1 * d * (S.tp1 - S.entry) / S.riskRef
                    if w1 >= 1:
                        outc = "TP1 HIT"
                if outc == "" and S.tp1Done and ((h[i] >= S.tp2) if d == 1 else (l[i] <= S.tp2)):
                    S.resultR += (1 - w1) * d * (S.tp2 - S.entry) / S.riskRef
                    outc = "TP2 HIT"
                if hit1 and P["useBE"] and outc == "":
                    S.beOn, S.stop = True, S.entry
            if outc:
                S.state = 8
                rec(S, "TRADE", outc)

        # pending invalidation (v1 vs v2)
        if S.state in (3, 4):
            d = S.dir
            why, cat = "", ""
            lvl = S.invalLvl if v2 and P["invalAtStop"] else S.ext
            if v2 and P["invalAtStop"]:
                through = (l[i] <= lvl if P["wickInval"] else c[i] <= lvl) if d == 1 else (h[i] >= lvl if P["wickInval"] else c[i] >= lvl)
            else:
                through = (l[i] < lvl if P["wickInval"] else c[i] < lvl) if d == 1 else (h[i] > lvl if P["wickInval"] else c[i] > lvl)
            ran = h[i] >= S.rMid if d == 1 else l[i] <= S.rMid
            if through:
                cat, why = "STRUCTURAL", "traded through " + ("planned stop" if v2 and P["invalAtStop"] else "sweep extreme")
            elif ran:
                cat, why = "MISSED", "reached CRT 50% before entry" + ("" if S.confBar is not None else " (before 15M)")
            elif v2 and P["conflictInval"] and S.state == 3 and st15 is not None and (
                    (st15["bearT"] if d == 1 else st15["bullT"]) is not None and (st15["bearT"] if d == 1 else st15["bullT"]) > S.reclaimT):
                cat, why = "CONFLICT", "opposite 15M structure break after reclaim"
            elif S.state == 3 and i - S.reclaimBar > P["confExpiry"]:
                cat, why = "EXPIRED", "no 15M confirmation"
            elif S.state == 4 and i - S.confBar > P["entryExpiry"]:
                cat = "SESSION" if (v2 and "entry window" in S.reject) else "EXPIRED"
                why = "no valid 5M entry" + (" (last block: " + S.reject + ")" if S.reject else "")
            if why:
                S.state = 9
                rec(S, cat, why)

        # new setup
        if best is not None:
            d = -best.side
            bMid = (bHi + bLo) / 2
            buf = max(P["stopBufTk"] * mt, P["stopBufATR"] * atrE[i])
            invalLvl = best.ext - buf if d == 1 else best.ext + buf
            block = ""
            if P["htfFilter"] and h4Bias == -d and not best.hiTF:
                block = "against 4H bias"
            elif (h[i] >= bMid) if d == 1 else (l[i] <= bMid):
                block = "reclaim candle reached 50%"
            elif v2 and not isnan(best.fav) and ((best.fav >= bMid) if d == 1 else (best.fav <= bMid)):
                block = "50% reached before reclaim confirmed"
            elif S.state in (5, 6):
                block = "trade active"
            elif v2 and P["roomCheck"]:
                # best plausible entry = the swept level itself (a retest); if even that has no valid
                # target / R:R, the setup can never produce a trade → reject instead of "forming"
                riskBest = d * (best.price - invalLvl)
                _, t2, _, _ = targets(d, best.price, riskBest, bHi, bLo, bMid, bTF) if riskBest > 0 else (0, NaN, 0, 0)
                if riskBest <= 0 or isnan(t2):
                    block = "no room to a ≥" + str(P["minRR"]) + "R target"
            if block == "":
                if S.state in (3, 4) and S.dir != d:
                    S.state = 9
                    rec(S, "REPLACED", "opposite sweep")
                if S.state in (0, 8, 9):
                    S = Setup(state=3, dir=d, srcKind=best.kind, srcTF=bTF, hiTF=best.hiTF, level=best.price,
                              ext=best.ext, invalLvl=invalLvl, breachTime=best.breachTime, reclaimBar=i,
                              rHi=bHi, rLo=bLo, rMid=bMid, confBar=None, rtLvl=NaN, reject="", rolls=0,
                              created_ms=int(tms[i]), c5Bar=None, resultR=0.0, tp1Done=False, beOn=False,
                              breachBar=best.breachBar, reclaimT=int(tms[i]))
                else:
                    block = "setup pending"
            if block and int(tms[i]) >= start_ms:
                blocks[block] += 1

        # 15M confirmation
        if S.state == 3 and st15 is not None:
            d = S.dir
            mT = st15["bullT"] if d == 1 else st15["bearT"]
            mCh = st15["bullCh"] if d == 1 else st15["bearCh"]
            mDs = st15["bullDs"] if d == 1 else st15["bearDs"]
            mL = st15["bullLvl"] if d == 1 else st15["bearLvl"]
            dT = st15["bullDT"] if d == 1 else st15["bearDT"]
            mss = mT is not None and mT > S.breachTime and (not P["reqChoch"] or mCh)
            dsp = dT is not None and dT > S.breachTime
            okc = mss if P["confMode"] == "MSS / CHoCH" else (mss and mDs) if P["confMode"] == "MSS + Displacement" else (mss or dsp)
            if okc:
                S.state, S.confBar, S.rtLvl = 4, i, (mL if mss else S.level)

        # v2: remember a 5M structure break that happened after the reclaim but before 15M confirmation
        if v2 and P["pairedConfirm"] and S.state == 3 and (bull5 if S.dir == 1 else bear5):
            S.c5Bar = i

        # 5M entry
        if S.state == 4:
            d = S.dir
            tolR = P["retestTol"] * atrE[i]
            brk = bull5 if d == 1 else bear5
            rt = (l[i] <= S.rtLvl + tolR and c[i] > S.rtLvl and c[i] > o[i]) if d == 1 else (h[i] >= S.rtLvl - tolR and c[i] < S.rtLvl and c[i] < o[i])
            l5 = lastBull5 if d == 1 else lastBear5
            paired = v2 and P["pairedConfirm"] and S.confBar == i and l5 >= S.breachBar and i - l5 <= P["pairBars"]
            mom = (c[i] > o[i] and c[i] > h[i - 1]) if d == 1 else (c[i] < o[i] and c[i] < l[i - 1])
            tm = P["trigMode"]
            trig = brk if tm == "5M structure break" else rt if tm == "Retest of 15M break" else mom if tm == "Momentum candle" else (brk or rt)
            if tm in ("Break or Retest", "5M structure break"):
                trig = trig or paired
            if trig:
                eRef = c[i]
                buf = max(P["stopBufTk"] * mt, P["stopBufATR"] * atrE[i])
                stp = (S.ext - buf if d == 1 else S.ext + buf) if not v2 else S.invalLvl
                risk = d * (eRef - stp)
                rej = ""
                if risk <= 0:
                    rej = "entry beyond stop"
                elif risk > P["maxRiskATR"] * atrE[i]:
                    rej = "too far from stop"
                elif P["reqDiscount"] and ((eRef >= S.rMid) if d == 1 else (eRef <= S.rMid)):
                    rej = "not in discount/premium"
                elif not entryOK[i]:
                    rej = "outside entry window"
                elif P["htfFilter"] and h4Bias == -d and not S.hiTF:
                    rej = "against 4H bias"
                else:
                    t1, t2, _, _ = targets(d, eRef, risk, S.rHi, S.rLo, S.rMid, S.srcTF)
                    if isnan(t2):
                        rej = "no target"
                    elif d * (t2 - eRef) / risk < P["minRR"]:
                        rej = "R:R below min"
                if rej == "":
                    S.state, S.sigBar, S.entryRef, S.stop, S.riskRef, S.tp1, S.tp2 = 5, i, eRef, stp, risk, t1, t2
                    if S.created_ms >= start_ms:
                        signals.append(dict(t=str(t_srv[i]), dir=d, entry=eRef, sl=stp, tp1=t1, tp2=t2, src=S.srcKind, paired=bool(paired)))
                else:
                    S.reject = rej
                    if S.created_ms >= start_ms:
                        rejects[rej] += 1

        # housekeeping
        for q in list(pools):
            if q.isCRT:
                rm = q.retired and q.state != 1
            else:
                rm = (q.state == 0 and tms[i] > q.expires) or (q.state in (2, 3) and i - q.resolvedBar > 144)
            if rm:
                pools.remove(q)

    return dict(outcomes=outcomes, signals=signals, blocks=blocks, rejects=rejects, arrays=(o, h, l, c))


def summarize(res, title):
    oc = res["outcomes"]
    print(f"\n=== {title} ===")
    print(f"setups that reached SWEEP CONFIRMED & RECLAIMED: {len(oc) + (0)}")
    cats = Counter(x["cat"] for x in oc)
    for k, v in cats.most_common():
        print(f"  {k:<11} {v:>5}")
    print("  reasons:")
    for k, v in Counter((x["cat"], x["reason"]) for x in oc).most_common(12):
        print(f"    {v:>5}  {k[0]:<10} {k[1]}")
    print(f"  setups alive across ≥1 HTF candle roll: {sum(1 for x in oc if x['rolls'] > 0)}  (none invalidated BY the roll)")
    print(f"  signals: {len(res['signals'])}  (paired 5M-before-15M: {sum(1 for s in res['signals'] if s['paired'])})")
    print("  trigger rejections:", dict(res["rejects"].most_common()))
    print("  creation blocks:", dict(res["blocks"].most_common()))
    tr = [x for x in oc if x["cat"] == "TRADE"]
    print("  trade outcomes:", dict(Counter(x["reason"] for x in tr)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--start", default="2024-02-01")
    ap.add_argument("--end", default="2025-02-01")
    ap.add_argument("--version", default="both", choices=["v1", "v2", "both"])
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    df = load(a.csv, a.start, a.end)
    out = {}
    for ver in (["v1", "v2"] if a.version == "both" else [a.version]):
        res = run(df, dict(DEFAULTS), ver, start=a.start)
        summarize(res, f"{ver}  {a.start} → {a.end}")
        out[ver] = dict(outcomes=res["outcomes"], signals=res["signals"])
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1, default=str)
