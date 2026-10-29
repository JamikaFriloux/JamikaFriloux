#!/usr/bin/env python3
"""Assemble the two standalone Pine v6 files from shared sources.

The signal engine, shared execution helpers and display block are pasted verbatim into both
outputs, so raw-signal parity between indicator and strategy is guaranteed by construction.
Usage: python3 tools/build.py [--check]   (--check: fail if outputs on disk are stale)
"""
import hashlib, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SHARED = ["engine.pine", "exec_shared.pine"]
PLAN = {
    "MEKA_ALPHA_PRO_4_INDICATOR.pine": ["header_indicator.pine", *SHARED, "indicator_exec.pine", "display.pine"],
    "MEKA_ALPHA_PRO_4_STRATEGY.pine": ["header_strategy.pine", *SHARED, "strategy_exec.pine", "display.pine"],
}


def block(text, begin, end):
    i, j = text.index(begin), text.index(end)
    return text[i:j + len(end)]


def build():
    out = {}
    for name, parts in PLAN.items():
        body = "\n".join((SRC / p).read_text().rstrip("\n") + "\n" for p in parts)
        out[name] = body
    ind, strat = out.values()
    for b, e in [("// COMMON SIGNAL ENGINE BEGIN", "// COMMON SIGNAL ENGINE END"),
                 ("// SHARED EXECUTION HELPERS BEGIN", "// SHARED EXECUTION HELPERS END"),
                 ("// SHARED DISPLAY BEGIN", "// SHARED DISPLAY END")]:
        assert block(ind, b, e) == block(strat, b, e), f"block differs: {b}"
    return out


def main():
    out = build()
    check = "--check" in sys.argv
    stale = False
    for name, text in out.items():
        path = ROOT / name
        if check:
            if not path.exists() or path.read_text() != text:
                print(f"STALE {name}")
                stale = True
        else:
            path.write_text(text)
        eng = block(text, "// COMMON SIGNAL ENGINE BEGIN", "// COMMON SIGNAL ENGINE END")
        print(f"{name}: {text.count(chr(10))} lines, engine sha256 {hashlib.sha256(eng.encode()).hexdigest()[:16]}")
    sys.exit(1 if stale else 0)


if __name__ == "__main__":
    main()
