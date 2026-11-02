#!/usr/bin/env python3
"""MEKA CRT PRO — Model FVG (first retest of a strong, structure-breaking FVG) + confluence count.

Mirrors the Pine sections "FVG + SUPPLY / DEMAND ENGINES", "CONFLUENCE ENGINE" and "MODEL FVG".
Confluence factors reproduced here: 4H/1H bias, 15M structure, 1H premium/discount, FVG support /
FVG before TP1, demand-supply support / zone before TP1, recent opposite-side swing sweep.
(The Pine engine also counts AMD and CRT/pool sweeps; those are not modelled in this port.)
"""
import math
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import meka_replay as M  # noqa: E402

DEF = dict(fvgMinATR=0.15, fvgStrongATR=1.0, fvgMaxAge=288, sdDispATR=1.2, sdLook=3, sdMaxTouch=3, sdMaxAge=576,
           strong=True, bos=True, maxWait=36, trigWin=3, stopTk=2, maxRisk=2.0, tp1R=1.0, tp2R=2.0, minRR=1.5,
           needWin=True, tp1Pct=50.0, cfFilter=False, cfMinPro=2, cfMaxCon=1)


def conf(i, d, e, t1, D, fvgs, zones, atr, lastSSL, lastBSL):
    pro = con = 0
    b4, b1 = D["b4"][i], D["b1"][i]
    if b4 == d and b1 == d:
        pro += 1
    elif b4 == -d and b1 == -d:
        con += 1
    j = D["i15"][i] - 1
    tr = D["s15"][j]["trend"] if j >= 0 else 0
    pro += tr == d
    con += tr == -d
    pm = D["pmid"][i]
    if not math.isnan(pm):
        if (d == 1) == (e < pm):
            pro += 1
        else:
            con += 1
    a = atr[i]
    fs = any(g["state"] < 2 and g["dir"] == d and ((g["bot"] <= e and e - g["top"] <= a) if d == 1 else (g["top"] >= e and g["bot"] - e <= a)) for g in fvgs)
    fo = any(g["state"] < 2 and g["dir"] == -d and ((e < g["bot"] < t1) if d == 1 else (t1 < g["top"] < e)) for g in fvgs)
    zs = any(z["state"] == 0 and z["dir"] == d and ((z["bot"] <= e and e - z["top"] <= a) if d == 1 else (z["top"] >= e and z["bot"] - e <= a)) for z in zones)
    zo = any(z["state"] == 0 and z["dir"] == -d and ((e < z["bot"] < t1) if d == 1 else (t1 < z["top"] < e)) for z in zones)
    pro += zs
    con += fo + zo
    sw = lastSSL if d == 1 else lastBSL
    pro += sw is not None and i - sw <= 12
    return pro, con, fs   # fs (FVG support) is excluded for the FVG model itself, as in Pine


def run(df, mk, P, D, t_from=None, t_to=None, stop_at=None):
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    n = len(df) if stop_at is None else stop_at
    atr = M.atr(h, l, c)
    ph5, pl5 = M.pivots(h, 3, 2, True), M.pivots(l, 3, 2, False)
    ms_ = M.ms(df.utc.dt.tz_convert("UTC").dt.tz_localize(None).values)
    inR = np.ones(len(df), bool) if t_from is None else (ms_ >= t_from) & (ms_ < t_to)
    tick = mk["tick"]
    swH = swL = np.nan
    swHB = swLB = True
    lb5 = lB5 = -10**9
    lastSSL = lastBSL = None
    fvgs, zones = [], []
    T = None
    trades, funnel = [], dict(cand=0, notTradable=0, cfRejected=0, entriesOff=0)
    w1 = P["tp1Pct"] / 100
    for i in range(n):
        bull5 = bear5 = False
        if not math.isnan(ph5[i]):
            swH, swHB = ph5[i], False
        if not math.isnan(pl5[i]):
            swL, swLB = pl5[i], False
        # sweep proxy (Pine counts swept & reclaimed liquidity pools): wick beyond the last confirmed swing, close back inside
        if not swHB and h[i] > swH and c[i] <= swH:
            lastBSL = i
        if not swLB and l[i] < swL and c[i] >= swL:
            lastSSL = i
        if not swHB and c[i] > swH:
            swHB, bull5, lb5 = True, True, i
        if not swLB and c[i] < swL:
            swLB, bear5, lB5 = True, True, i
        a = atr[i]
        # ---- FVG engine (identical rules to context_zones.py / Pine) ----
        for g in list(fvgs):
            if g["bar"] < i and g["state"] < 2:
                if g["dir"] == 1:
                    if c[i] < g["bot"]:
                        if g["inv"]:
                            g["state"] = 3
                        else:
                            g.update(inv=True, dir=-1, state=0, bar=i, used=True)
                    elif l[i] <= g["bot"]:
                        g["state"] = 2
                    elif l[i] < g["top"]:
                        g["state"] = 1
                        g["tap"] = g["tap"] if g["tap"] is not None else i
                else:
                    if c[i] > g["top"]:
                        if g["inv"]:
                            g["state"] = 3
                        else:
                            g.update(inv=True, dir=1, state=0, bar=i, used=True)
                    elif h[i] >= g["top"]:
                        g["state"] = 2
                    elif h[i] > g["bot"]:
                        g["state"] = 1
                        g["tap"] = g["tap"] if g["tap"] is not None else i
            if g["state"] >= 2 or i - g["bar"] > P["fvgMaxAge"]:
                fvgs.remove(g)
        if i >= 2 and not math.isnan(a):
            body1 = abs(c[i - 1] - o[i - 1])
            if l[i] - h[i - 2] > 0 and l[i] - h[i - 2] >= P["fvgMinATR"] * a:
                fvgs.append(dict(dir=1, top=l[i], bot=h[i - 2], bar=i, inv=False, state=0, tap=None, used=False,
                                 strong=c[i - 1] > o[i - 1] and body1 >= P["fvgStrongATR"] * a, bos=lb5 >= i - 1))
            if l[i - 2] - h[i] > 0 and l[i - 2] - h[i] >= P["fvgMinATR"] * a:
                fvgs.append(dict(dir=-1, top=l[i - 2], bot=h[i], bar=i, inv=False, state=0, tap=None, used=False,
                                 strong=c[i - 1] < o[i - 1] and body1 >= P["fvgStrongATR"] * a, bos=lB5 >= i - 1))
            while len(fvgs) > 40:
                fvgs.pop(0)
        # ---- supply / demand engine ----
        for z in list(zones):
            if z["state"] == 0 and z["bar"] < i:
                thru = c[i] < z["bot"] if z["dir"] == 1 else c[i] > z["top"]
                touch = l[i] <= z["top"] if z["dir"] == 1 else h[i] >= z["bot"]
                if thru:
                    z.update(state=1, end=i)
                elif touch:
                    if not z["inside"]:
                        z["touches"] += 1
                        z["inside"] = True
                        if z["touches"] > P["sdMaxTouch"]:
                            z.update(state=2, end=i)
                else:
                    z["inside"] = False
            if i - z["bar"] > P["sdMaxAge"] or (z["state"] != 0 and i - z["end"] > 48):
                zones.remove(z)
        if i > P["sdLook"] and not math.isnan(a):
            bullD = c[i] > o[i] and c[i] - o[i] >= P["sdDispATR"] * a and c[i] > h[i - 1]
            bearD = c[i] < o[i] and o[i] - c[i] >= P["sdDispATR"] * a and c[i] < l[i - 1]
            if bullD or bearD:
                d = 1 if bullD else -1
                k = 1
                for j in range(1, P["sdLook"] + 1):
                    if (c[i - j] < o[i - j]) if d == 1 else (c[i - j] > o[i - j]):
                        k = j
                        break
                zt, zb = h[i - k], l[i - k]
                if not any(z["state"] == 0 and z["dir"] == d and zb <= z["top"] and zt >= z["bot"] for z in zones):
                    zones.append(dict(dir=d, top=zt, bot=zb, bar=i, touches=0, inside=False, state=0, end=None))
                while len(zones) > 30:
                    zones.pop(0)
        # ---- trade lifecycle ----
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
        # ---- FVG model ----
        best = None
        for g in fvgs:
            if not g["used"] and not g["inv"] and g["state"] == 1 and g["tap"] is not None and (not P["strong"] or g["strong"]) and (not P["bos"] or g["bos"]):
                if g["tap"] - g["bar"] > P["maxWait"] or i - g["tap"] >= P["trigWin"]:
                    g["used"] = True
                else:
                    ce = (g["top"] + g["bot"]) / 2
                    rej = (c[i] > ce and c[i] > o[i]) if g["dir"] == 1 else (c[i] < ce and c[i] < o[i])
                    if rej and (best is None or g["bar"] > best["bar"]):
                        best = g
        if best is not None:
            best["used"] = True
            d = best["dir"]
            e = c[i]
            stp = best["bot"] - P["stopTk"] * tick if d == 1 else best["top"] + P["stopTk"] * tick
            risk = d * (e - stp)
            if inR[i]:
                funnel["cand"] += 1
            why = ""
            if P["needWin"] and not D["win"][i]:
                why = "entries off"
            elif T is not None and T["state"] in (5, 6):
                why = "trade open"
            elif risk <= 0 or risk > P["maxRisk"] * a:
                why = "stop"
            elif P["tp2R"] < P["minRR"]:
                why = "rr"
            t1 = e + d * P["tp1R"] * risk
            cp = cn = 0
            if not why:
                cp, cn, _ = conf(i, d, e, t1, D, fvgs, zones, atr, lastSSL, lastBSL)
                if P["cfFilter"] and (cp < P["cfMinPro"] or cn > P["cfMaxCon"]):
                    why = "confluence"
            if why:
                if inR[i]:
                    funnel["entriesOff" if why == "entries off" else "cfRejected" if why == "confluence" else "notTradable"] += 1
            else:
                T = dict(state=5, dir=d, sig=i, stop=stp, risk=risk, t1=t1, t2=e + d * P["tp2R"] * risk, tp1=False, R=0.0,
                         inR=bool(inR[i]), bar=i, pro=cp, con=cn, kT=int(ms_[i]))
    return trades, funnel
