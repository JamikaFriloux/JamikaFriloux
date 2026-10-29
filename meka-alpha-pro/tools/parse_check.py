#!/usr/bin/env python3
"""Grammar-only check with the open-source pynescript parser (pip install pynescript).
This is NOT TradingView compilation: no type checking, no built-in signature validation."""
import sys
from pynescript.ast import parse
ok = True
for path in sys.argv[1:]:
    try:
        parse(open(path).read())
        print(f"PARSED OK   {path}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"PARSE FAIL  {path}: {type(e).__name__}: {str(e)[:500]}")
sys.exit(0 if ok else 1)
