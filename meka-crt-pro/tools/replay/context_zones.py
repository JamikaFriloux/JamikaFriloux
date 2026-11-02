#!/usr/bin/env python3
"""FVG + supply/demand engines — bar-for-bar port of the Pine rules (context overlays).

Reports how many gaps / zones the default rules create, how they end (filled, inverted,
invalidated, retired), how many are visible at once, and runs a no-future-information test
(state on any bar must not change when later data is removed).

  python3 tools/replay/context_zones.py gold XAU_5m.csv
  python3 tools/replay/context_zones.py nq   NQ_1m.csv
"""
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import meka_replay as M  # noqa: E402
import model_c as C      # noqa: E402

P = dict(fvgMinATR=0.15, fvgStrongATR=1.0, fvgMaxAge=288, sdDispATR=1.2, sdLook=3, sdMaxTouch=3, sdMaxAge=576,
         showN=2, fvgMaxDist=8.0, sdMaxDist=10.0)


def run(df, stop_at=None):
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    n = len(df) if stop_at is None else stop_at
    atr = M.atr(h, l, c)
    ph5 = M.pivots(h, 3, 2, True)
    pl5 = M.pivots(l, 3, 2, False)
    swH = swL = np.nan
    swHB = swLB = True
    fvgs, zones = [], []
    ev = Counter()
    vis = []
    snap = []
    for i in range(n):
        bull5 = bear5 = False
        if not np.isnan(ph5[i]):
            swH, swHB = ph5[i], False
        if not np.isnan(pl5[i]):
            swL, swLB = pl5[i], False
        if not swHB and c[i] > swH:
            swHB, bull5 = True, True
        if not swLB and c[i] < swL:
            swLB, bear5 = True, True
        a = atr[i]
        # FVG update
        for g in list(fvgs):
            if g["bar"] < i and g["state"] < 2:
                if g["dir"] == 1:
                    if c[i] < g["bot"]:
                        if g["inv"]:
                            g["state"] = 3; ev["ifvg invalidated"] += 1
                        else:
                            g.update(inv=True, dir=-1, state=0, fill=0.0, bar=i); ev["fvg inverted"] += 1
                    elif l[i] <= g["bot"]:
                        g["state"] = 2; ev["ifvg filled" if g["inv"] else "fvg fully filled"] += 1
                    elif l[i] < g["top"]:
                        g["state"] = 1
                else:
                    if c[i] > g["top"]:
                        if g["inv"]:
                            g["state"] = 3; ev["ifvg invalidated"] += 1
                        else:
                            g.update(inv=True, dir=1, state=0, fill=0.0, bar=i); ev["fvg inverted"] += 1
                    elif h[i] >= g["top"]:
                        g["state"] = 2; ev["ifvg filled" if g["inv"] else "fvg fully filled"] += 1
                    elif h[i] > g["bot"]:
                        g["state"] = 1
            if g["state"] >= 2 or i - g["bar"] > P["fvgMaxAge"]:
                if g["state"] < 2:
                    ev["fvg expired (age)"] += 1
                fvgs.remove(g)
        # FVG detection
        if i >= 2 and not np.isnan(a):
            body1 = abs(c[i - 1] - o[i - 1])
            if l[i] - h[i - 2] > 0 and l[i] - h[i - 2] >= P["fvgMinATR"] * a:
                fvgs.append(dict(dir=1, top=l[i], bot=h[i - 2], bar=i, inv=False, state=0, fill=0.0,
                                 strong=c[i - 1] > o[i - 1] and body1 >= P["fvgStrongATR"] * a)); ev["fvg created"] += 1
                ev["fvg strong"] += fvgs[-1]["strong"]
            if l[i - 2] - h[i] > 0 and l[i - 2] - h[i] >= P["fvgMinATR"] * a:
                fvgs.append(dict(dir=-1, top=l[i - 2], bot=h[i], bar=i, inv=False, state=0, fill=0.0,
                                 strong=c[i - 1] < o[i - 1] and body1 >= P["fvgStrongATR"] * a)); ev["fvg created"] += 1
                ev["fvg strong"] += fvgs[-1]["strong"]
            while len(fvgs) > 40:
                fvgs.pop(0)
        # zones update
        for z in list(zones):
            if z["state"] == 0 and z["bar"] < i:
                thru = c[i] < z["bot"] if z["dir"] == 1 else c[i] > z["top"]
                touch = l[i] <= z["top"] if z["dir"] == 1 else h[i] >= z["bot"]
                if thru:
                    z.update(state=1, end=i); ev["zone invalidated"] += 1
                elif touch:
                    if not z["inside"]:
                        z["touches"] += 1; z["inside"] = True
                        if z["touches"] == 1:
                            ev["zone first retest"] += 1
                        if z["touches"] > P["sdMaxTouch"]:
                            z.update(state=2, end=i); ev["zone retired"] += 1
                else:
                    z["inside"] = False
            if i - z["bar"] > P["sdMaxAge"] or (z["state"] != 0 and i - z["end"] > 48):
                zones.remove(z)
        # zone detection
        if i > P["sdLook"] and not np.isnan(a):
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
                bos = bull5 if d == 1 else bear5
                merged = False
                for z in zones:
                    if z["state"] == 0 and z["dir"] == d and zb <= z["top"] and zt >= z["bot"]:
                        z["bos"] = z["bos"] or bos; merged = True; ev["zone merged"] += 1
                        break
                if not merged:
                    zones.append(dict(dir=d, top=zt, bot=zb, bar=i, bos=bos, touches=0, inside=False, state=0, end=None))
                    ev["zone created"] += 1; ev["zone with BOS"] += bos
                while len(zones) > 30:
                    zones.pop(0)
        # visible-candidate counts (before the N-per-side cap)
        if not np.isnan(a):
            fv = sum(1 for g in fvgs if max(0, (c[i] - g["top"]) if g["dir"] == 1 else (g["bot"] - c[i])) <= P["fvgMaxDist"] * a and ((g["bot"] < c[i]) if g["dir"] == 1 else (g["top"] > c[i])))
            zv = sum(1 for z in zones if z["state"] == 0 and max(0, (c[i] - z["top"]) if z["dir"] == 1 else (z["bot"] - c[i])) <= P["sdMaxDist"] * a and ((z["bot"] < c[i]) if z["dir"] == 1 else (z["top"] > c[i])))
            vis.append((fv, zv))
        snap.append((len(fvgs), len(zones), round(sum(g["top"] for g in fvgs), 6), round(sum(z["top"] for z in zones), 6)))
    return ev, vis, snap


if __name__ == "__main__":
    kind, path = sys.argv[1], sys.argv[2]
    df = C.load(kind, path)
    if kind == "gold":
        df = df[(df.utc >= pd.Timestamp("2024-02-01", tz="UTC")) & (df.utc < pd.Timestamp("2025-02-01", tz="UTC"))].reset_index(drop=True)
    days = df.utc.dt.date.nunique()
    ev, vis, snap = run(df)
    print(f"{kind}: {len(df)} 5M bars, {days} trading days")
    for k in ["fvg created", "fvg strong", "fvg fully filled", "fvg inverted", "ifvg filled", "ifvg invalidated", "fvg expired (age)",
              "zone created", "zone with BOS", "zone merged", "zone first retest", "zone invalidated", "zone retired"]:
        print(f"  {k:<20} {ev[k]:>6}   ({ev[k] / days:.1f}/day)")
    v = np.array(vis)
    print(f"  candidates within range on a bar: FVG median {np.median(v[:, 0]):.0f} (p90 {np.percentile(v[:, 0], 90):.0f}), "
          f"zones median {np.median(v[:, 1]):.0f} (p90 {np.percentile(v[:, 1], 90):.0f}) → drawn ≤ {P['showN']} per side")
    ok = True
    for frac in (0.3, 0.6, 0.9):
        cut = int(len(df) * frac)
        _, _, sp = run(df, stop_at=cut)
        same = sp == snap[:cut]
        ok &= same
        print(f"  no-future test cut {df.utc.iloc[cut - 1]}: {'IDENTICAL' if same else 'MISMATCH'} engine state on all {cut} bars")
    sys.exit(0 if ok else 1)
