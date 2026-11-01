#!/usr/bin/env python3
"""No-future-information test: run the engine on data truncated at several cut points and require that
every setup outcome and signal that completed before the cut is identical to the full-history run."""
import sys
import meka_replay as M

def key_sig(s):
    return (s["t"], s["dir"], round(s["entry"], 5), round(s["sl"], 5), round(s["tp1"], 5), round(s["tp2"], 5))

def main(csv, start, end, version):
    df = M.load(csv, start, end)
    full = M.run(df, dict(M.DEFAULTS), version, start=start)
    n = len(df)
    ok = True
    for frac in (0.35, 0.6, 0.85):
        cut = int(n * frac)
        part = M.run(df, dict(M.DEFAULTS), version, start=start, stop_at=cut)
        tcut = str(df.t.iloc[cut - 1])
        fs = [key_sig(s) for s in full["signals"] if s["t"] <= tcut]
        ps = [key_sig(s) for s in part["signals"]]
        # outcomes recorded strictly before the cut must match (open setups at the cut are excluded)
        fo = [(x["t"], x["cat"], x["reason"]) for x in full["outcomes"] if x["crBar"] + x["bars"] < cut - 1]
        po = [(x["t"], x["cat"], x["reason"]) for x in part["outcomes"] if x["crBar"] + x["bars"] < cut - 1]
        same = fs == ps and fo == po
        ok &= same
        print(f"{version} cut@{tcut}: signals {len(ps)}/{len(fs)}  outcomes {len(po)}/{len(fo)}  -> {'IDENTICAL' if same else 'MISMATCH'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "v2"))
