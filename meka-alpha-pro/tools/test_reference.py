#!/usr/bin/env python3
"""Deterministic scenario + randomized property tests for the 4.0-r2 rules.

Run: python3 -I tools/test_reference.py   (stdlib only; Python 3.9+ for zoneinfo)
These exercise tools/reference_model.py (a Python port) plus a port of the Pine session /
trading-day formulas. They do NOT execute Pine or TradingView's broker emulator.
"""
import pathlib
import random
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from reference_model import Bar, Cfg, Engine, Sim, parts, run, targets, floor_tick, ceil_tick  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def icc_bars():
    raw = [
        (100, 101, 99, 100), (100, 102, 99.5, 101), (101, 105, 100.5, 104), (104, 104.5, 102, 103),
        (103, 103.5, 101, 102), (102, 104, 101.5, 103.5),
        (103.6, 106.2, 103.4, 106),   # 6 indication: close breaks pivot 105 (+1 tick), body 2.4 >= 0.6 ATR
        (105.8, 106, 105, 105.5),     # 7 correction: retest band 104.75-105.25, trigger = 106
        (105.6, 107, 105.3, 106.8),   # 8 continuation: close > 106.25, bullish
        (106.9, 107.2, 106.5, 107),   # 9 fill bar
    ]
    return [Bar(*r) for r in raw]


class ICCStages(unittest.TestCase):
    def test_three_distinct_bars(self):
        eng, sim, out = run(icc_bars(), Cfg())
        stages = [(e[0], e[1]) for e in eng.log if e[1] in ("INDICATION", "CORRECTION", "CONTINUATION")]
        self.assertEqual(stages, [(6, "INDICATION"), (7, "CORRECTION"), (8, "CONTINUATION")])
        self.assertEqual(out[8]["signal"], 1)
        # Stop beyond correction extremes incl. the continuation bar: min(105, 105.3) - 0.15 -> 104.75
        self.assertAlmostEqual(out[8]["stop"], 104.75)
        self.assertEqual(out[8]["qty"], 24.0)  # floor(50 / 2.05)

    def test_stages_never_collapse_on_one_bar(self):
        bars = icc_bars()[:6]
        # One huge bar satisfying indication, retest band and a close above its own high-ish trigger.
        bars.append(Bar(103.6, 107, 104.8, 106.9))
        eng, sim, out = run(bars, Cfg())
        self.assertEqual([e[1] for e in eng.log if e[0] == 6 and e[1] in ("INDICATION", "CORRECTION", "CONTINUATION")], ["INDICATION"])
        self.assertEqual(out[6]["signal"], 0)

    def test_no_indication_before_pivot_available(self):
        eng, _, _ = run(icc_bars(), Cfg())
        first_pivot = min(e[0] for e in eng.log if e[1] == "PIVOT_HIGH_AVAILABLE")
        self.assertEqual(first_pivot, 4)  # origin bar 2 + strength 2
        self.assertTrue(all(e[0] > first_pivot for e in eng.log if e[1] == "INDICATION"))

    def test_trigger_frozen_and_correction_strictly_later(self):
        bars = icc_bars()
        bars[8] = Bar(105.6, 106.2, 105.1, 106.1)   # closes above 106 but not above 106 + 1 tick
        bars[9] = Bar(106.1, 106.6, 105.9, 106.5)   # breaks the frozen 106 trigger by > 1 tick
        eng, _, out = run(bars, Cfg())
        self.assertEqual(out[8]["signal"], 0)
        self.assertEqual(out[9]["signal"], 1)
        self.assertAlmostEqual(out[9]["stop"], 104.75)  # min(105, 105.1, 105.9) - 0.15 -> tick floor

    def test_invalidation_and_expiry(self):
        bars = icc_bars()[:8]
        bars.append(Bar(105.5, 105.6, 103.0, 103.5))   # breaks invalidation 103.25
        eng, _, out = run(bars, Cfg())
        self.assertIn((8, "END", "INVALID"), eng.log)
        bars = icc_bars()[:7] + [Bar(106.5, 107.5, 106.0, 107.2) for _ in range(30)]
        eng, _, _ = run(bars, Cfg(expiry=5))
        self.assertTrue(any(e[1] == "END" and e[2] == "EXPIRED" for e in eng.log))

    def test_far_structure_is_rejected_not_clipped(self):
        eng, _, out = run(icc_bars(), Cfg(max_stop=1.5))  # risk 2.05 ATR > 1.5
        self.assertEqual(out[8]["cand"], 1)
        self.assertEqual(out[8]["signal"], 0)


def sig(i, s, stop, risk, q):
    return {i: (s, stop, risk, q)}


class Execution(unittest.TestCase):
    def test_signal_bar_target_touch_not_credited(self):
        bars = [Bar(99, 103, 98.5, 100), Bar(100, 100.5, 99.5, 100.2), Bar(100.2, 100.4, 99.8, 100)]
        _, sim, out = run(bars, Cfg(), signals=sig(0, 1, 98.0, 2.0, 2.0))
        kinds = [e[1] for e in sim.events]
        self.assertEqual(kinds[:2], ["ENTER", "FILL"])
        self.assertNotIn("TP1", kinds)
        self.assertEqual([e[0] for e in sim.events if e[1] == "FILL"], [1])

    def test_favorable_gap_records_fill_and_gap_policy(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(103, 103.2, 102.6, 103), Bar(103, 103.5, 102.5, 103.1)]
        _, sim, _ = run(bars, Cfg(), signals=sig(0, 1, 98.0, 2.0, 2.0))
        fill = [e for e in sim.events if e[1] == "FILL"][0]
        self.assertEqual(fill[3], 103)            # actual modeled open, not the 100 reference
        self.assertAlmostEqual(sim.ratio, 2.5)    # (103 - 98) / 2
        tp1 = [e for e in sim.events if e[1] == "TP1"][0]
        self.assertEqual((tp1[0], tp1[3]), (1, 103))  # limit below market fills at the open
        self.assertIn((2, "EXIT_GAP_RISK", 1.0, 103), sim.events)

    def test_adverse_gap_through_stop(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(97, 97.5, 96, 97.2)]
        _, sim, _ = run(bars, Cfg(), signals=sig(0, 1, 98.0, 2.0, 2.0))
        stop = [e for e in sim.events if e[1] == "STOP"][0]
        self.assertEqual((stop[0], stop[3]), (1, 97))  # worse open, not the 98 stop price

    def test_short_gap_through_stop(self):
        bars = [Bar(101, 101, 99.5, 100), Bar(103, 103.5, 102.5, 103)]
        _, sim, _ = run(bars, Cfg(), signals=sig(0, -1, 102.0, 2.0, 2.0))
        stop = [e for e in sim.events if e[1] == "STOP"][0]
        self.assertEqual((stop[0], stop[3]), (1, 103))

    def test_stop_and_target_same_bar_is_stop_first_and_flagged(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 102.5, 97.5, 101)]
        _, sim, _ = run(bars, Cfg(), signals=sig(0, 1, 98.0, 2.0, 2.0))
        self.assertEqual(sim.ambiguous, 1)
        self.assertNotIn("TP1", [e[1] for e in sim.events])
        self.assertIn("STOP", [e[1] for e in sim.events])

    def test_tp1_then_breakeven_not_retroactive(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 102.5, 99.0, 101.5), Bar(101.5, 101.8, 99.5, 100)]
        _, sim, _ = run(bars, Cfg(be_on=True), signals=sig(0, 1, 98.0, 2.0, 2.0))
        kinds = [(e[0], e[1]) for e in sim.events]
        self.assertIn((1, "TP1"), kinds)
        self.assertNotIn((1, "STOP"), kinds)          # dip to 99 on the TP1 bar does not hit BE
        stop = [e for e in sim.events if e[1] == "STOP"][0]
        self.assertEqual((stop[0], stop[2], stop[3]), (2, 1.0, 100))  # 1 remaining unit at BE

    def test_one_contract_single_final_tranche(self):
        self.assertEqual(parts(1.0, Cfg()), (0.0, 0.0, 1.0))
        self.assertEqual(parts(2.0, Cfg(use_tp3=True)), (0.0, 0.0, 2.0))
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 102.2, 99.5, 102), Bar(102, 104.5, 101.8, 104)]
        _, sim, _ = run(bars, Cfg(), signals=sig(0, 1, 98.0, 2.0, 1.0))
        kinds = [e[1] for e in sim.events]
        self.assertNotIn("TP1", kinds)
        self.assertEqual([e for e in sim.events if e[1] == "FINAL"][0][2:], (1.0, 104))

    def test_allocations_conserve_quantity(self):
        for tp3 in (False, True):
            for step in (1.0, 0.01, 1000.0):
                cfg = Cfg(use_tp3=tp3, qty_step=step)
                for units in range(1, 10001):
                    q = units * step
                    a, b, c = parts(q, cfg)
                    self.assertTrue(min(a, b, c) >= 0)
                    self.assertAlmostEqual(a + b + c, q, delta=step * 1e-6)
                    for x in (a, b, c):
                        self.assertAlmostEqual(round(x / step), x / step, delta=1e-6)
                    if units >= (3 if tp3 else 2):
                        self.assertTrue(a > 0 and c > 0 and (b > 0) == tp3)

    def test_cooldown_zero_blocks_same_bar_reentry(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 100.2, 97, 97.5), Bar(97.5, 98, 97, 97.8)]
        signals = {0: (1, 98.0, 2.0, 2.0), 1: (-1, 99.5, 2.0, 2.0), 2: (-1, 99.5, 1.7, 2.0)}
        _, sim, _ = run(bars, Cfg(cooldown=0), signals=signals)
        enters = [e[0] for e in sim.events if e[1] == "ENTER"]
        self.assertEqual(enters, [0, 2])

    def test_targets_ordered_after_rounding(self):
        cfg = Cfg(tick=0.25, r1=1.0, r2=1.01, r3=1.02)
        t1, t2, t3 = targets(1, 100.0, 0.3, cfg)
        self.assertTrue(100 < t1 < t2 < t3)
        t1, t2, t3 = targets(-1, 100.0, 0.3, cfg)
        self.assertTrue(100 > t1 > t2 > t3)
        self.assertEqual(floor_tick(0.3, 0.1), 0.30000000000000004 or 0.3)
        self.assertAlmostEqual(ceil_tick(1.1, 0.1), 1.1)


def random_bars(rng, n):
    bars, c = [], 100.0
    for i in range(n):
        o = round((c + rng.gauss(0, 0.15)) * 4) / 4
        c = round((o + rng.gauss(0, 0.9)) * 4) / 4
        h = max(o, c) + round(abs(rng.gauss(0, 0.5)) * 4) / 4
        l = min(o, c) - round(abs(rng.gauss(0, 0.5)) * 4) / 4
        up = (i // 150) % 2 == 0
        bars.append(Bar(o, h, l, c, atr=1.0, trend_long=up, trend_short=not up, pull_long=up and rng.random() < 0.03, pull_short=(not up) and rng.random() < 0.03))
    return bars


class Properties(unittest.TestCase):
    def test_random_series(self):
        rng = random.Random(20261029)
        n_trades = n_icc = 0
        for trial in range(150):
            cfg = Cfg(engine=rng.choice(["ICC", "Either", "Trend pullback"]), use_tp3=rng.random() < 0.5,
                      be_on=rng.random() < 0.5, trail_on=rng.random() < 0.3, cooldown=rng.choice([0, 1, 3]),
                      hold_bars=rng.choice([5, 20, 48]), risk_cash=rng.choice([3.0, 50.0, 400.0]))
            bars = random_bars(rng, 600)
            eng, sim, out = run(bars, cfg)
            # Stage ordering, freshness and pivot availability.
            stage = {}
            avail = {}
            used = {1: set(), -1: set()}
            for e in eng.log:
                i, kind = e[0], e[1]
                if kind.startswith("PIVOT"):
                    avail[(kind, e[3])] = i
                    self.assertEqual(i - e[3], cfg.strength)
                elif kind == "INDICATION":
                    side, pid = e[2], e[3]
                    self.assertNotIn(pid, used[side], "pivot reused for a second indication")
                    used[side].add(pid)
                    key = ("PIVOT_HIGH_AVAILABLE" if side == 1 else "PIVOT_LOW_AVAILABLE", pid)
                    self.assertLess(avail[key], i)
                    stage = {"ind": i}
                elif kind == "CORRECTION":
                    self.assertGreater(i, stage["ind"])
                    stage["cor"] = i
                elif kind == "CONTINUATION":
                    self.assertGreater(i, stage["cor"])
                    n_icc += 1
                    stage = {}
                elif kind == "END":
                    stage = {}
            # Execution ledger checks per trade.
            trades, cur = [], None
            for ev in sim.events:
                i, kind = ev[0], ev[1]
                if kind == "ENTER":
                    self.assertIsNone(cur)
                    cur = {"enter": i, "qty": out[i]["qty"], "closed": 0.0, "fill": None}
                elif kind == "FILL":
                    self.assertEqual(i, cur["enter"] + 1)
                    cur["fill"] = i
                elif kind == "CLOSED_R":
                    self.assertAlmostEqual(cur["closed"], cur["qty"], delta=1e-6)
                    trades.append(cur)
                    cur = None
                else:
                    self.assertIsNotNone(cur["fill"], f"{kind} before fill")
                    self.assertGreaterEqual(i, cur["fill"])
                    cur["closed"] += ev[2]
            for r in out:
                if r["signal"] != 0:
                    s, stop, risk = r["signal"], r["stop"], r["risk"]
                    ref = bars[r["i"]].c
                    t1, t2, t3 = targets(s, ref, risk, cfg)
                    seq = [stop, ref, t1, t2, t3] if s == 1 else [t3, t2, t1, ref, stop]
                    self.assertEqual(seq, sorted(seq))
                    self.assertTrue(len(set(seq)) == 5)
                    self.assertGreaterEqual(risk, cfg.min_stop * bars[r["i"]].atr - 1e-9)
                    self.assertLessEqual(risk, cfg.max_stop * bars[r["i"]].atr + 1e-9)
            n_trades += len(trades)
        self.assertGreater(n_trades, 100)
        self.assertGreater(n_icc, 20)


# ---- Port of the Pine local-time formulas (f_inside / f_left / f_dayKey) ---------------------
def local_mins(t, zone):
    d = t.astimezone(ZoneInfo(zone))
    return d.hour * 60 + d.minute, d.date(), d.isoweekday() % 7 + 1  # Pine: 1=Sun ... 7=Sat


def inside(open_utc, minutes, sess, zone, weekdays="23456"):
    close = open_utc + timedelta(minutes=minutes)
    o, od, dow = local_mins(open_utc, zone)
    c, cd, _ = local_mins(close - timedelta(milliseconds=1), zone)
    a = int(sess[:2]) * 60 + int(sess[2:4])
    b = int(sess[5:7]) * 60 + int(sess[7:9])
    return str(dow) in weekdays and od == cd and o >= a and c < b, b - (c + 1)


def day_key(t, zone="America/New_York", reset=1700):
    m, d, _ = local_mins(t, zone)
    if m >= (reset // 100) * 60 + reset % 100:
        d = (t + timedelta(days=1)).astimezone(ZoneInfo(zone)).date()
    return d


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


class Sessions(unittest.TestCase):
    def test_us_uk_dst_mismatch_weeks(self):
        # 2026: US DST starts Mar 8, UK Mar 29; UK ends Oct 25, US Nov 1.
        ny, ldn, tky = ("0830-1200", "America/New_York"), ("0800-1200", "Europe/London"), ("0900-1500", "Asia/Tokyo")
        self.assertTrue(inside(utc(2026, 3, 2, 13, 30), 5, *ny)[0])    # EST: 08:30 = 13:30Z
        self.assertFalse(inside(utc(2026, 3, 2, 12, 30), 5, *ny)[0])
        self.assertTrue(inside(utc(2026, 3, 10, 12, 30), 5, *ny)[0])   # EDT: 08:30 = 12:30Z
        self.assertTrue(inside(utc(2026, 3, 10, 8, 0), 5, *ldn)[0])    # GMT still: 08:00 = 08:00Z
        self.assertTrue(inside(utc(2026, 4, 1, 7, 0), 5, *ldn)[0])     # BST: 08:00 = 07:00Z
        self.assertFalse(inside(utc(2026, 4, 1, 11, 0), 5, *ldn)[0])   # 12:00 BST = end, excluded
        self.assertTrue(inside(utc(2026, 10, 27, 8, 0), 5, *ldn)[0])   # GMT again after Oct 25
        self.assertTrue(inside(utc(2026, 10, 27, 12, 30), 5, *ny)[0])  # US still EDT until Nov 1
        self.assertTrue(inside(utc(2026, 11, 3, 13, 30), 5, *ny)[0])
        for d in (2, 10, 30):
            self.assertTrue(inside(utc(2026, 3, d, 0, 0), 5, *tky)[0])  # Tokyo has no DST

    def test_boundary_bars_cutoff_and_weekdays(self):
        ldn = ("0800-1200", "Europe/London")
        self.assertFalse(inside(utc(2026, 1, 6, 11, 30), 60, *ldn)[0])  # 11:30-12:30 crosses the end
        ok, left = inside(utc(2026, 1, 6, 11, 45), 15, *ldn)
        self.assertTrue(ok)
        self.assertEqual(left, 0)                                       # cutoff 5 min would block it
        self.assertEqual(inside(utc(2026, 1, 6, 11, 0), 15, *ldn)[1], 45)
        self.assertFalse(inside(utc(2026, 1, 10, 9, 0), 5, *ldn)[0])    # Saturday
        self.assertFalse(inside(utc(2026, 1, 6, 7, 55), 15, *ldn)[0])   # starts before 08:00

    def test_trading_day_boundary(self):
        self.assertEqual(str(day_key(utc(2026, 3, 9, 20, 55))), "2026-03-09")  # 16:55 EDT Monday
        self.assertEqual(str(day_key(utc(2026, 3, 9, 21, 0))), "2026-03-10")   # 17:00 EDT -> Tuesday
        self.assertEqual(str(day_key(utc(2026, 3, 2, 22, 0))), "2026-03-03")   # 17:00 EST
        self.assertEqual(str(day_key(utc(2026, 3, 3, 4, 59))), "2026-03-03")   # past midnight, same day
        self.assertEqual(str(day_key(utc(2026, 3, 7, 22, 30))), "2026-03-08")  # Sat 17:30 EST -> DST day


def code_only(text):
    """Drop // comments that are not inside string literals."""
    out = []
    for line in text.splitlines():
        in_str, i, cut = False, 0, len(line)
        while i < len(line):
            ch = line[i]
            if ch == "\\" and in_str:
                i += 2
                continue
            if ch == '"':
                in_str = not in_str
            elif not in_str and line.startswith("//", i):
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return "\n".join(out)


# ---- Static checks on the built Pine text --------------------------------------------------
class StaticPine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ind = (ROOT / "MEKA_ALPHA_PRO_4_INDICATOR.pine").read_text()
        cls.strat = (ROOT / "MEKA_ALPHA_PRO_4_STRATEGY.pine").read_text()

    def block(self, text, name):
        return text[text.index(f"// {name} BEGIN"):text.index(f"// {name} END")]

    def test_shared_blocks_identical(self):
        for name in ("COMMON SIGNAL ENGINE", "SHARED EXECUTION HELPERS", "SHARED DISPLAY"):
            self.assertEqual(self.block(self.ind, name), self.block(self.strat, name))

    def test_declarations(self):
        self.assertTrue(self.ind.startswith("//@version=6\nindicator("))
        self.assertTrue(self.strat.startswith("//@version=6\nstrategy("))
        for flag in ("calc_on_every_tick=false", "calc_on_order_fills=false", "process_orders_on_close=false", "pyramiding=0"):
            self.assertIn(flag, self.strat)
        self.assertNotIn("strategy.", code_only(self.ind))
        self.assertNotIn("alertcondition", self.strat)

    def test_htf_is_offset_with_lookahead(self):
        for m in re.finditer(r"request\.security\((.*)\)", self.ind):
            args = m.group(1)
            self.assertIn("lookahead=barmerge.lookahead_on", args)
            self.assertNotRegex(args, r"\[close,|ta\.ema\(close, 50\),")
            self.assertIn("close[1]", args)

    def test_no_forbidden_claims_or_constructs(self):
        # Code and user-visible strings only (comments carry the disclaimers that name these words).
        for text in (self.ind, self.strat):
            low = code_only(text).lower()
            for bad in ("win rate", "winrate", "probability", "accuracy", "institutional", "varip"):
                self.assertNotIn(bad, low)
            for lit in re.findall(r'"(?:[^"\\]|\\.)*"', low):
                self.assertNotRegex(lit, r"\d\s*%", lit)  # no percentage claims in visible text

    def test_balanced_and_tabs(self):
        for text in (self.ind, self.strat):
            self.assertNotIn("\t", text)
            for line in text.splitlines():
                code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line.split("//")[0] if '"' not in line.split("//")[0] else line)
                self.assertEqual(code.count("(") - code.count(")"), 0, line)
                self.assertEqual(code.count("[") - code.count("]"), 0, line)
                indent = len(line) - len(line.lstrip(" "))
                self.assertEqual(indent % 4, 0, line)

    def test_assignments_target_declared_names(self):
        for text in (self.ind, self.strat):
            declared = set(re.findall(r"^\s*(?:var\s+)?(?:(?:int|float|bool|string|color|table|array<string>)\s+)?([A-Za-z_]\w*)\s*=(?!=)", text, re.M))
            declared |= {n for tup in re.findall(r"\[([^\]]+)\]\s*=(?!=)", text) for n in re.split(r"\s*,\s*", tup)}
            for name in re.findall(r"^\s*([A-Za-z_]\w*)\s*(?::=|\+=|-=)", text, re.M):
                self.assertIn(name, declared, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
