#!/usr/bin/env python3
"""Model C no-future-information test: trades completed before each cut must be identical when the
data is truncated at that cut (signal time, direction, entry ref, stop, targets, net R)."""
import sys
import pandas as pd
import model_c as C

kind, path = sys.argv[1], sys.argv[2]
mk = C.MARKETS[kind]
df = C.load(kind, path)
if kind == "gold":
    df = df[(df.utc >= pd.Timestamp("2023-12-20", tz="UTC")) & (df.utc < pd.Timestamp("2025-02-01", tz="UTC"))].reset_index(drop=True)
key = lambda t: (t["kT"], t["dir"], round(t["entryRef"], 4), round(t["stop"], 4), round(t["t2"], 4), round(t["Rnet"], 6))
ok = True
for P in (dict(C.DEF), dict(C.DEF, bias="off", anyTime=True, refMode="rolling")):
    full, _ = C.run(C.prep(df, mk, P), mk, P)
    for frac in (0.4, 0.7, 0.9):
        cut = int(len(df) * frac)
        part, _ = C.run(C.prep(df.iloc[:cut].reset_index(drop=True), mk, P), mk, P)
        tcut = int(df.utc.iloc[cut - 1].value // 1_000_000)
        a = [key(t) for t in full if t["kT"] < tcut - 6 * 3600_000 and t["state"] == 8][: len(part)]
        b = [key(t) for t in part]
        same = a == b[: len(a)] and len(b) >= len(a)
        ok &= same
        print(f"{P['refMode']:<8} bias={P['bias']:<6} cut {df.utc.iloc[cut-1]}: {len(b)} trades vs {len(a)} → {'IDENTICAL' if same else 'MISMATCH'}")
sys.exit(0 if ok else 1)
