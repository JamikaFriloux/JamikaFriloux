#!/usr/bin/env python3
"""MEKA CRT PRO — Model C (15M double-range confirmation) bar-for-bar replay.

Mirrors the Pine rules in 'MEKA CRT PRO — Indicator.pine' (section MODEL C):
  * each completed 15M candle is processed once, on the 5M bar whose close = the 15M close
  * reference pair = two consecutive completed 15M candles (session-open / after structure / rolling)
  * boundaries frozen at lock; confirmation = later 15M CLOSE beyond a boundary (+ buffer)
  * opposite-boundary sweep disqualifier (strict / sweep+close-back / off), expiry, filters
  * entry = NEXT 5M bar open; stop-first exit ordering; TP1 partial; costs per trade

This is a logic replay on rebuilt candles, not a TradingView backtest. Usage:
  python3 tools/replay/model_c.py gold XAU_5m.csv     (server time NY+7, ';' separated)
  python3 tools/replay/model_c.py nq   NQ_1m.csv      (UTC ISO timestamps, 1-minute → 5M)
"""
import math
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import meka_replay as M  # noqa: E402  (atr, pivots, struct15, ms)

NaN = float("nan")

MARKETS = {
    # cost_pts: round-trip cost in price points per unit (spread/slippage + commission/pointvalue)
    "gold": dict(tick=0.01, day_start_ny=17, cost_pts=0.30, windows=[("Europe/London", 800, 1100), ("America/New_York", 830, 1130)], sessions=dict(ASIA=("Asia/Tokyo", 900, 1500), LDN=("Europe/London", 800, 1630), NY=("America/New_York", 800, 1600))),
    "nq": dict(tick=0.25, day_start_ny=18, cost_pts=0.5 + 4.5 / 20.0, windows=[("America/New_York", 930, 1130)], sessions=dict(ASIA=("Asia/Tokyo", 900, 1500), LDN=("Europe/London", 800, 1630), NY=("America/New_York", 800, 1600))),
}
OPENS = [("NY open", "America/New_York", 930), ("London open", "Europe/London", 800)]

DEF = dict(refMode="session", bufTk=0, sweepRule="strict", sweepWin=0, expiry=8,
           bias="4H+1H", conflict="block", emaLen=50, structF=False, sessions=("ASIA", "LDN", "NY"), anyTime=False,
           dispMin=0.0, volMult=0.0, stopMode="boundary", stopATR=1.5, stopTk=2, maxRiskATR=2.0, minStopATR=1.0, maxStopPts=0.0, needWin=True,
           tp1R=1.0, tp2R=2.0, minRR=1.5, tp1Pct=50.0, pivL15=3, pivR15=2, dispMult=0.8)


def load(kind, path):
    if kind == "gold":
        df = pd.read_csv(path, sep=";")
        srv = pd.to_datetime(df["Date"], format="%Y.%m.%d %H:%M")
        ny = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
        out = pd.DataFrame({"utc": ny.dt.tz_convert("UTC"), "o": df.Open, "h": df.High, "l": df.Low, "c": df.Close, "v": df.Volume})
        return out.dropna(subset=["utc"]).reset_index(drop=True)
    df = pd.read_csv(path)
    df["utc"] = pd.to_datetime(df["datetime"], utc=True)
    g = df.set_index("utc").resample("5min", label="left", closed="left")
    out = pd.DataFrame({"o": g.open.first(), "h": g.high.max(), "l": g.low.min(), "c": g.close.last(), "v": g.volume.sum()}).dropna()
    return out.reset_index()


def prep(df, mk, P):
    n = len(df)
    utc = df.utc
    ny_wall = utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
    k15 = utc.dt.floor("15min")
    k1 = utc.dt.floor("1h")
    k4 = (ny_wall + pd.Timedelta(hours=24 - mk["day_start_ny"])).dt.floor("4h")
    def agg(key):
        g = df.groupby(key, sort=True)
        a = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "v": g.v.sum()})
        a["t"] = a.index
        return a, a.index.get_indexer(key)
    A15, i15 = agg(k15)
    A1, i1 = agg(k1)
    A4, i4 = agg(k4)
    # bias: previous completed HTF close vs EMA of that TF   (Pine: [close[1], ema[1]], lookahead_on)
    def bias(A, idx):
        e = A.c.ewm(span=P["emaLen"], adjust=False).mean().values
        c = A.c.values
        b = np.sign(c - e)
        b[:P["emaLen"]] = 0
        out = np.zeros(n)
        ok = idx - 1 >= 0
        out[ok] = b[idx[ok] - 1]
        return out
    b4, b1 = bias(A4, i4), bias(A1, i1)
    atr15 = M.atr(A15.h.values, A15.l.values, A15.c.values)
    vsma = pd.Series(A15.v.values).rolling(20).mean().values
    s15 = M.struct15(A15, P["pivL15"], P["pivR15"], P["dispMult"])
    t15 = M.ms(A15.t.values)  # UTC ms (candle open); unit-safe (pandas may store us)
    def hhmm(ms_arr, tz):
        lt = pd.to_datetime(ms_arr, unit="ms", utc=True).tz_convert(tz)
        return (lt.hour * 100 + lt.minute).values
    hm = {tz: hhmm(t15, tz) for tz in {"Asia/Tokyo", "Europe/London", "America/New_York"}}
    last = np.r_[i15[1:] != i15[:-1], True]  # 5M bar whose close is the 15M close
    ph5, pl5 = M.pivots(df.h.values, 3, 2, True), M.pivots(df.l.values, 3, 2, False)
    sw5H, sw5L = pd.Series(ph5).ffill().values, pd.Series(pl5).ffill().values  # last CONFIRMED 5M swing
    win = np.zeros(n, bool)
    for tz, a, b in mk["windows"]:
        lt = utc.dt.tz_convert(tz)
        hm5 = (lt.dt.hour * 100 + lt.dt.minute).values
        win |= (hm5 >= a) & (hm5 < b)
    return dict(sw5H=sw5H, sw5L=sw5L, win=win, n=n, i15=i15, A15=A15, b4=b4, b1=b1, atr15=atr15, vsma=vsma, s15=s15, t15=t15, hm=hm, last=last,
                o=df.o.values, h=df.h.values, l=df.l.values, c=df.c.values, utc=utc)


def in_s(hm, a, b):
    return (hm >= a and hm < b) if a < b else (hm >= a or hm < b)


def run(D, mk, P, t_from=None, t_to=None):
    o, h, l, c, i15, A15 = D["o"], D["h"], D["l"], D["c"], D["i15"], D["A15"]
    H15, L15, O15, C15, V15 = A15.h.values, A15.l.values, A15.o.values, A15.c.values, A15.v.values
    tick = mk["tick"]
    q15 = 15 * 60_000
    CR = dict(state=0)
    TC = None
    lastPairT2 = None
    armed, armT = False, None
    prevJ = None
    trades, ends = [], Counter()
    prevStruct = (None, None)
    w1 = P["tp1Pct"] / 100.0

    def end(st, why):
        CR.update(state=st, why=why)
        if CR.get("inRange", True):
            ends[st] += 1

    for i in range(D["n"]):
        # trade lifecycle
        if TC is not None:
            if TC["state"] == 5 and i > TC["sig"]:
                TC.update(state=6, entry=o[i], fill=i)
            if TC["state"] == 6:
                d = TC["dir"]
                if (l[i] <= TC["stop"]) if d == 1 else (h[i] >= TC["stop"]):
                    xp = min(o[i], TC["stop"]) if d == 1 else max(o[i], TC["stop"])
                    rl = d * (xp - TC["entry"]) / TC["risk"]
                    TC["R"] = TC["R"] + (1 - w1) * rl if TC["tp1"] else rl
                    TC["state"] = 8
                else:
                    if not TC["tp1"] and ((h[i] >= TC["t1"]) if d == 1 else (l[i] <= TC["t1"])):
                        TC["tp1"] = True
                        TC["R"] = w1 * d * (TC["t1"] - TC["entry"]) / TC["risk"]
                    if TC["tp1"] and ((h[i] >= TC["t2"]) if d == 1 else (l[i] <= TC["t2"])):
                        TC["R"] += (1 - w1) * d * (TC["t2"] - TC["entry"]) / TC["risk"]
                        TC["state"] = 8
                if TC["state"] == 8:
                    TC["Rnet"] = TC["R"] - mk["cost_pts"] / TC["risk"]
                    if TC["inRange"]:
                        trades.append(TC)
        j = i15[i] - 1  # last completed 15M candle known on this bar ([1] + lookahead_on)
        st = D["s15"][j] if j >= 0 else None
        if P["refMode"] == "structure" and st is not None:
            cur = (st["bullT"], st["bearT"])
            if cur != prevStruct and prevStruct != (None, None) and any(x is not None for x in cur):
                armed, armT = True, max(x for x in cur if x is not None)
            prevStruct = cur
        if not D["last"][i]:
            continue
        k = i15[i]  # this bar closes candle k → process it (lookahead_off at the 15M close)
        kT, kO, kH, kL, kC, kV = int(D["t15"][k]), O15[k], H15[k], L15[k], C15[k], V15[k]
        kA, kVA = D["atr15"][k], D["vsma"][k]
        inRange = (t_from is None or kT >= t_from) and (t_to is None or kT < t_to)
        openNm = ""
        if P["refMode"] == "session":
            for nm, tz, hh in OPENS:
                if D["hm"][tz][k] == hh:
                    openNm = nm
                    break
        if CR["state"] == 2 and openNm:
            end(10, "superseded")
        if CR["state"] == 2 and kT > CR["t2"]:
            CR["n"] += 1
            inWin = P["sweepWin"] == 0 or CR["n"] <= P["sweepWin"]
            if inWin and P["sweepRule"] != "off":
                if kH > CR["up"]:
                    CR["upHit"] = True
                    if P["sweepRule"] == "strict":
                        CR["bearDQ"] = True
                if kL < CR["lo"]:
                    CR["dnHit"] = True
                    if P["sweepRule"] == "strict":
                        CR["bullDQ"] = True
                if P["sweepRule"] == "sweep" and CR["upHit"] and kC <= CR["up"]:
                    CR["bearDQ"] = True
                if P["sweepRule"] == "sweep" and CR["dnHit"] and kC >= CR["lo"]:
                    CR["bullDQ"] = True
            buf = P["bufTk"] * tick
            bearC, bullC = kC < CR["lo"] - buf, kC > CR["up"] + buf
            if bearC or bullC:
                d = 1 if bullC else -1
                if CR["bullDQ"] if d == 1 else CR["bearDQ"]:
                    end(9, "disqualified side")
                else:
                    why = ""
                    tzs = [mk["sessions"][s] for s in P["sessions"]]
                    inS = P["anyTime"] or any(in_s(D["hm"][tz][k], a, b) for tz, a, b in tzs)
                    b4, b1 = D["b4"][i], D["b1"][i]
                    conflict = b4 != b1
                    eff = b4 if P["bias"] == "4H" else b1 if P["bias"] == "1H" else (b4 if not conflict else (b4 if P["conflict"] == "4H" else b1 if P["conflict"] == "1H" else 0))
                    if not inS:
                        why = "session"
                    elif P["bias"] == "4H+1H" and conflict and P["conflict"] == "block":
                        why = "bias conflict"
                    elif P["bias"] != "off" and eff != d:
                        why = "against bias"
                    elif P["structF"] and (st is None or st["trend"] != d):
                        why = "15M structure"
                    elif P["dispMin"] > 0 and not math.isnan(kA) and abs(kC - kO) < P["dispMin"] * kA:
                        why = "displacement"
                    elif P["volMult"] > 0 and not math.isnan(kVA) and kVA > 0 and kV < P["volMult"] * kVA:
                        why = "volume"
                    if why:
                        end(9, "filtered: " + why)
                    elif TC is not None and TC["state"] in (5, 6):
                        end(11, "trade open")
                    elif P["needWin"] and not D["win"][i]:
                        end(11, "not actionable: entries off")
                    else:
                        e = c[i]
                        sb = P["stopTk"] * tick
                        stp = NaN
                        cap = min(P["maxRiskATR"] * kA if not math.isnan(kA) else 1e12, P["maxStopPts"] or 1e12)
                        mnR = P["minStopATR"] * kA if not math.isnan(kA) else 0.0
                        if P["stopMode"] == "smart":
                            cands = [kL - sb if d == 1 else kH + sb]
                            if st is not None:
                                cands.append((st["swL"] - sb) if d == 1 else (st["swH"] + sb))
                            cands.append((D["sw5L"][i] - sb) if d == 1 else (D["sw5H"][i] + sb))
                            best = None
                            for cv in cands:
                                if not math.isnan(cv):
                                    rr = d * (e - cv)
                                    if mnR <= rr <= cap and (best is None or rr < best):
                                        best, stp = rr, cv
                            if math.isnan(stp) and not math.isnan(kA):
                                ra = max(P["stopATR"] * kA, mnR)
                                if ra <= cap:
                                    stp = e - d * ra
                            if math.isnan(stp):
                                end(11, "no stop within limits")
                                stp = None
                        elif P["stopMode"] == "swing" and st is not None:
                            sw = st["swL"] if d == 1 else st["swH"]
                            if not math.isnan(sw) and d * (e - sw) > 0:
                                stp = sw - d * sb
                        elif P["stopMode"] == "atr" and not math.isnan(kA):
                            stp = e - d * P["stopATR"] * kA
                        if stp is not None and math.isnan(stp):
                            stp = CR["lo"] - sb if d == 1 else CR["up"] + sb
                        risk = d * (e - stp) if stp is not None else 0
                        if stp is None:
                            pass
                        elif risk <= 0:
                            end(11, "beyond stop")
                        elif risk > cap:
                            end(11, "stop too wide")
                        elif P["tp2R"] < P["minRR"]:
                            end(11, "rr")
                        else:
                            t1, t2 = e + d * P["tp1R"] * risk, e + d * P["tp2R"] * risk
                            if d * (t2 - t1) <= 0:
                                t1 = e + (t2 - e) * 0.5
                            TC = dict(state=5, dir=d, sig=i, entryRef=e, stop=stp, risk=risk, t1=t1, t2=t2, tp1=False, R=0.0,
                                      kT=kT, src=CR["src"], inRange=inRange, riskATR=risk / kA if kA else NaN)
                            end(7, "confirmed")
            elif CR["bullDQ"] and CR["bearDQ"]:
                end(9, "both sides disqualified")
            elif CR["n"] >= P["expiry"]:
                end(10, "expired")
        if CR["state"] == 1:
            if kT == CR["t1"] + q15:
                CR.update(state=2, h2=kH, l2=kL, t2=kT, up=max(CR["h1"], kH), lo=min(CR["l1"], kL), n=0,
                          upHit=False, dnHit=False, bullDQ=False, bearDQ=False, inRange=inRange)
                lastPairT2 = kT
                if inRange:
                    ends["locked"] += 1
            else:
                CR["state"] = 0
        if CR["state"] not in (1, 2):
            fresh = lastPairT2 is None or kT > lastPairT2
            endT = CR.get("endT")
            nm = ""
            if P["refMode"] == "session" and openNm:
                nm = openNm
            elif P["refMode"] == "structure" and armed and kT >= armT:
                nm, armed = "structure", False
            elif P["refMode"] == "rolling" and prevJ is not None and kT == int(D["t15"][prevJ]) + q15 and int(D["t15"][prevJ]) > (lastPairT2 or -1) and (endT is None or int(D["t15"][prevJ]) > endT):
                nm = "rolling"
            if nm and fresh:
                if nm == "rolling":
                    pT = int(D["t15"][prevJ])
                    CR = dict(state=2, src=nm, h1=H15[prevJ], l1=L15[prevJ], t1=pT, h2=kH, l2=kL, t2=kT,
                              up=max(H15[prevJ], kH), lo=min(L15[prevJ], kL), n=0, upHit=False, dnHit=False,
                              bullDQ=False, bearDQ=False, inRange=inRange)
                    lastPairT2 = kT
                    if inRange:
                        ends["locked"] += 1
                else:
                    CR = dict(state=1, src=nm, h1=kH, l1=kL, t1=kT, inRange=inRange)
        if CR["state"] in (7, 9, 10, 11) and "endT" not in CR:
            CR["endT"] = kT
        prevJ = k
    return trades, ends


def stats(tr, label=""):
    if not tr:
        return dict(label=label, n=0)
    R = np.array([t["Rnet"] for t in tr])
    w, ls = R[R > 0], R[R <= 0]
    eq = np.cumsum(R)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]))
    pf = w.sum() / -ls.sum() if ls.sum() < 0 else float("inf")
    return dict(label=label, n=len(R), win=100 * len(w) / len(R), pf=pf, netR=R.sum(), expR=R.mean(),
                avgW=w.mean() if len(w) else NaN, avgL=ls.mean() if len(ls) else NaN, ddR=dd)


def fmt(s):
    if s["n"] == 0:
        return f"{s['label']:<34} trades    0"
    return (f"{s['label']:<34} trades {s['n']:>4}  win {s['win']:5.1f}%  PF {s['pf']:5.2f}  net {s['netR']:+7.1f}R  "
            f"exp {s['expR']:+.3f}R  avgW {s['avgW']:+.2f}  avgL {s['avgL']:+.2f}  maxDD {s['ddR']:.1f}R")


def session_of(t, mk):
    hm = {tz: int(pd.Timestamp(t, unit="ms", tz="UTC").tz_convert(tz).strftime("%H%M")) for tz in {"Asia/Tokyo", "Europe/London", "America/New_York"}}
    for nm in ("NY", "LDN", "ASIA"):
        tz, a, b = mk["sessions"][nm]
        if in_s(hm[tz], a, b):
            return nm
    return "OTHER"


if __name__ == "__main__":
    kind, path = sys.argv[1], sys.argv[2]
    mk = MARKETS[kind]
    df = load(kind, path)
    periods = {"gold": [("IS 2023-02→2024-02", "2023-02-01", "2024-02-01"), ("OOS 2024-02→2025-02", "2024-02-01", "2025-02-01")],
               "nq": [("NQ 2008-01→2008-05 (all)", "2008-01-01", "2008-06-01")]}[kind]
    lo_t = pd.Timestamp(periods[0][1], tz="UTC") - pd.Timedelta(days=40)
    df = df[(df.utc >= lo_t) & (df.utc < pd.Timestamp(periods[-1][2], tz="UTC"))].reset_index(drop=True)
    print(f"{kind}: {len(df)} 5M bars {df.utc.min()} → {df.utc.max()}  cost/trade {mk['cost_pts']} pts")
    raw = dict(DEF, bias="off", anyTime=True)
    variants = [
        ("RAW (no filters, any time)", raw),
        ("+ sessions only", dict(raw, anyTime=False)),
        ("+ 4H bias only", dict(raw, bias="4H")),
        ("+ 1H bias only", dict(raw, bias="1H")),
        ("+ 4H+1H bias, conflict=block", dict(raw, bias="4H+1H")),
        ("+ 15M structure only", dict(raw, structF=True)),
        ("+ displacement ≥0.5 ATR only", dict(raw, dispMin=0.5)),
        ("+ volume ≥1.0× avg only", dict(raw, volMult=1.0)),
        ("DEFAULT (sessions + 4H+1H block)", dict(DEF)),
        ("raw · sweep rule = sweep+close", dict(raw, sweepRule="sweep")),
        ("raw · sweep rule = off", dict(raw, sweepRule="off")),
        ("raw · ref = after structure", dict(raw, refMode="structure")),
        ("raw · ref = rolling", dict(raw, refMode="rolling")),
    ]
    for pname, a, b in periods:
        print(f"\n######## {pname} ########")
        t_from = int(pd.Timestamp(a, tz="UTC").value // 1_000_000)
        t_to = int(pd.Timestamp(b, tz="UTC").value // 1_000_000)
        cache = {}
        for name, P in variants:
            key = (P["emaLen"], P["pivL15"], P["pivR15"], P["dispMult"])
            if key not in cache:
                cache[key] = prep(df, mk, P)
            tr, ends = run(cache[key], mk, P, t_from, t_to)
            print(fmt(stats(tr, name)) + f"   | locked {ends['locked']} conf {ends[7]} inval {ends[9]} exp {ends[10]} missed {ends[11]}")
            if name.startswith("RAW") or name.startswith("DEFAULT"):
                for dname, dv in (("  long", 1), ("  short", -1)):
                    print("   " + fmt(stats([t for t in tr if t["dir"] == dv], name[:7] + dname)))
                for sn in ("NY", "LDN", "ASIA", "OTHER"):
                    sub = [t for t in tr if session_of(t["kT"], mk) == sn]
                    if sub:
                        print("   " + fmt(stats(sub, name[:7] + "  session " + sn)))
