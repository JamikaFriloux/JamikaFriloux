#!/usr/bin/env python3
"""Deterministic scenario + randomized property tests for the MEKA ALPHA PRO 4.0 rules.

Run: python3 -I tools/test_reference.py   (stdlib only; Python 3.9+ for zoneinfo)
These exercise tools/reference_model.py (a Python port) plus a port of the Pine session /
trading-day formulas, and run static checks on the generated Pine text. They do NOT execute
Pine or TradingView's broker emulator.
"""
import pathlib
import random
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from reference_model import Bar, Cfg, Sim, parts, run, targets, floor_tick, ceil_tick  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOEXIT = dict(exit_on_choch=False)


def icc_bars():
    raw = [
        (101, 102, 100.5, 101.5), (101.5, 103, 101, 102.5), (102.5, 105, 102, 104),  # 2: swing high 105
        (104, 104.5, 100.8, 101.5), (101.5, 103.5, 101.2, 103),   # 4: swing high 105 confirmed
        (103, 104, 101.5, 103.6),     # 5: swing low 100.8 (bar 3) confirmed -> impulse origin
        (103.6, 106.2, 103.4, 106),   # 6: indication - close breaks 105 by > 1 tick, body 2.4 ATR
        (105.8, 106, 105, 105.5),     # 7: correction - retest band 104.75-105.25, trigger 106
        (105.6, 107, 105.3, 106.8),   # 8: continuation - bullish close above 106.25
        (106.9, 107.2, 106.5, 107),   # 9: fill bar
    ]
    return [Bar(*r) for r in raw]


def stages(eng):
    return [(e[0], e[1]) for e in eng.log if e[1] in ("INDICATION", "CORRECTION", "CONTINUATION")]


class Structure(unittest.TestCase):
    def test_choch_then_bos_and_swing_broken_once(self):
        eng, _, _ = run(icc_bars(), Cfg(**NOEXIT))
        kinds = [(e[0], e[1]) for e in eng.log if e[1] in ("BOS_UP", "CHOCH_UP", "BOS_DN", "CHOCH_DN")]
        self.assertEqual(kinds, [(6, "CHOCH_UP")])  # first break with no prior trend = CHoCH
        bars = icc_bars() + [Bar(107, 107.1, 105.6, 106), Bar(106, 106.5, 105.7, 106.2), Bar(106.2, 108.5, 106.1, 108.4)]
        eng, _, _ = run(bars, Cfg(**NOEXIT))
        ups = [e[1] for e in eng.log if e[1] in ("BOS_UP", "CHOCH_UP")]
        self.assertEqual(ups[0], "CHOCH_UP")
        self.assertTrue(all(k == "BOS_UP" for k in ups[1:]))
        self.assertEqual(len(ups), len({e[2] for e in eng.log if e[1] in ("BOS_UP", "CHOCH_UP")}))

    def test_choch_can_be_disallowed(self):
        eng, _, out = run(icc_bars(), Cfg(allow_choch=False, **NOEXIT))
        self.assertEqual(stages(eng), [])

    def test_sweep_detection(self):
        bars = icc_bars()[:6] + [Bar(103.5, 103.7, 100.6, 101.2)]  # wick below swing low 100.8, close back above
        _, _, out = run(bars, Cfg(**NOEXIT))
        self.assertTrue(out[6]["events"]["sweep_low"])


class ICCStages(unittest.TestCase):
    def test_three_distinct_bars(self):
        eng, sim, out = run(icc_bars(), Cfg(**NOEXIT))
        self.assertEqual(stages(eng), [(6, "INDICATION"), (7, "CORRECTION"), (8, "CONTINUATION")])
        self.assertEqual(out[8]["signal"], 1)
        self.assertAlmostEqual(out[8]["stop"], 104.75)    # min(105, 105.3) - 0.15 -> tick floor
        self.assertEqual(out[8]["qty"], 24.0)              # floor(50 / 2.05)

    def test_stages_never_collapse_on_one_bar(self):
        bars = icc_bars()[:6] + [Bar(103.6, 107, 104.8, 106.9)]
        eng, _, out = run(bars, Cfg(**NOEXIT))
        self.assertEqual(stages(eng), [(6, "INDICATION")])
        self.assertEqual(out[6]["signal"], 0)

    def test_no_indication_without_known_swing(self):
        eng, _, _ = run(icc_bars(), Cfg(**NOEXIT))
        first_low = min(e[0] for e in eng.log if e[1] == "PIVOT_LOW_AVAILABLE")
        self.assertEqual(first_low, 5)
        self.assertTrue(all(e[0] > first_low for e in eng.log if e[1] == "INDICATION"))

    def test_deeper_pullback_moves_trigger_to_that_bar(self):
        bars = icc_bars()[:8] + [Bar(105.4, 105.6, 104.6, 105.0), Bar(105.1, 106.0, 105.0, 105.9)]
        eng, _, out = run(bars, Cfg(**NOEXIT))
        self.assertEqual(out[8]["signal"], 0)
        # Bar 6's 106.2 high becomes a confirmed swing on bar 8: only 0.3 of room above 105.9.
        self.assertEqual(out[9]["cand"], 1)
        self.assertFalse(out[9]["room_ok"])
        self.assertEqual(out[9]["signal"], 0)
        eng, _, out = run(bars, Cfg(room_gate=False, **NOEXIT))
        self.assertEqual(out[9]["signal"], 1)                # 105.9 > 105.6 + 1 tick
        self.assertAlmostEqual(out[9]["stop"], 104.25)       # min(104.6, 105.0) - 0.15 -> 104.25

    def test_retracement_zone_correction(self):
        bars = icc_bars()[:7] + [Bar(106.1, 106.3, 104.0, 104.3)]   # never in the retest band? 104 < 104.75
        eng, _, _ = run(bars, Cfg(corr_type="Retracement 38-79%", **NOEXIT))
        self.assertIn((7, "CORRECTION"), stages(eng))       # 104.0 <= 106.2 - 0.382 * 5.4 = 104.137
        bars = icc_bars()[:7] + [Bar(106.1, 106.3, 104.3, 104.6)]
        eng, _, _ = run(bars, Cfg(corr_type="Retracement 38-79%", **NOEXIT))
        self.assertNotIn((7, "CORRECTION"), stages(eng))

    def test_close_beyond_origin_cancels(self):
        bars = icc_bars()[:8] + [Bar(105, 105.2, 100.0, 100.5)]
        eng, _, _ = run(bars, Cfg(**NOEXIT))
        self.assertIn((8, "END", "ORIGIN"), eng.log)

    def test_bias_loss_and_expiry_cancel(self):
        bars = icc_bars()[:8] + [Bar(105.5, 105.8, 105.2, 105.6, bias=0)]
        eng, _, _ = run(bars, Cfg(**NOEXIT))
        self.assertIn((8, "END", "BIAS"), eng.log)
        bars = icc_bars()[:7] + [Bar(106.5, 107.5, 106.0, 107.2) for _ in range(30)]
        eng, _, _ = run(bars, Cfg(expiry=5, **NOEXIT))
        self.assertTrue(any(e[1] == "END" and e[2] == "EXPIRED" for e in eng.log))

    def test_vwap_volume_and_sweep_requirements_block_continuation(self):
        bars = icc_bars()
        bars[8] = Bar(105.6, 107, 105.3, 106.8, vwap_long=False)
        _, _, out = run(bars, Cfg(**NOEXIT))
        self.assertEqual(out[8]["signal"], 0)
        bars[8] = Bar(105.6, 107, 105.3, 106.8, vol_ok=False)
        _, _, out = run(bars, Cfg(**NOEXIT))
        self.assertEqual(out[8]["signal"], 0)
        _, _, out = run(icc_bars(), Cfg(need_sweep=True, **NOEXIT))
        self.assertEqual(out[8]["signal"], 0)
        bars = icc_bars()
        bars[7] = Bar(105.8, 106, 100.5, 105.5)   # correction wick sweeps the 100.8 origin
        _, _, out = run(bars, Cfg(need_sweep=True, max_stop=10, **NOEXIT))
        self.assertEqual(out[8]["signal"], 1)

    def test_far_structure_rejected_and_stop_methods(self):
        _, _, out = run(icc_bars(), Cfg(max_stop=1.5, **NOEXIT))
        self.assertEqual(out[8]["cand"], 1)
        self.assertEqual(out[8]["signal"], 0)
        self.assertTrue(out[8]["wide"])
        _, _, out = run(icc_bars(), Cfg(stop_method="ATR", **NOEXIT))
        self.assertAlmostEqual(out[8]["stop"], 105.25)       # 106.8 - 1.5 -> floor tick
        _, _, out = run(icc_bars(), Cfg(stop_method="Wider of both", **NOEXIT))
        self.assertAlmostEqual(out[8]["stop"], 104.75)

    def test_limit_entry_reference_is_trigger(self):
        _, _, out = run(icc_bars(), Cfg(limit=True, **NOEXIT))
        self.assertAlmostEqual(out[8]["ref"], 106.0)         # rests at the broken trigger, below close
        self.assertAlmostEqual(out[8]["risk"], 1.25)


def sig(i, s, ref, stop, q):
    return {i: (s, ref, stop, q)}


class Execution(unittest.TestCase):
    def test_signal_bar_target_touch_not_credited(self):
        bars = [Bar(99, 103, 98.5, 100), Bar(100, 100.5, 99.5, 100.2), Bar(100.2, 100.4, 99.8, 100)]
        _, sim, _ = run(bars, Cfg(**NOEXIT), signals=sig(0, 1, 100.0, 98.0, 2.0))
        kinds = [(e[0], e[1]) for e in sim.events]
        self.assertEqual(kinds[:2], [(0, "ENTER"), (1, "FILL")])
        self.assertNotIn("TP1", [k for _, k in kinds])

    def test_gap_fill_risk_and_gap_policy(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(103, 103.2, 102.6, 103), Bar(103, 103.5, 102.5, 103.1)]
        _, sim, _ = run(bars, Cfg(**NOEXIT), signals=sig(0, 1, 100.0, 98.0, 2.0))
        self.assertIn((1, "FILL", 2.0, 103), sim.events)
        self.assertAlmostEqual(sim.ratio, 2.5)
        self.assertIn((1, "TP1", 1.0, 103), sim.events)       # limit below market fills at the open
        self.assertIn((1, "EXIT_REQUEST", "GAP_RISK", None), sim.events)
        self.assertIn((2, "EXIT_GAP_RISK", 1.0, 103), sim.events)

    def test_adverse_gaps_through_stop(self):
        _, sim, _ = run([Bar(99, 100.5, 99, 100), Bar(97, 97.5, 96, 97.2)], Cfg(**NOEXIT), signals=sig(0, 1, 100.0, 98.0, 2.0))
        self.assertIn((1, "STOP", 2.0, 97), sim.events)
        _, sim, _ = run([Bar(101, 101, 99.5, 100), Bar(103, 103.5, 102.5, 103)], Cfg(**NOEXIT), signals=sig(0, -1, 100.0, 102.0, 2.0))
        self.assertIn((1, "STOP", 2.0, 103), sim.events)

    def test_stop_and_target_same_bar_is_stop_first(self):
        _, sim, _ = run([Bar(99, 100.5, 99, 100), Bar(100, 102.5, 97.5, 101)], Cfg(**NOEXIT), signals=sig(0, 1, 100.0, 98.0, 2.0))
        self.assertEqual(sim.ambiguous, 1)
        self.assertNotIn("TP1", [e[1] for e in sim.events])
        self.assertTrue(sim.touched[0])                       # touched, but not credited

    def test_tp1_then_breakeven_not_retroactive(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 102.5, 99.0, 101.5), Bar(101.5, 101.8, 99.5, 100)]
        _, sim, _ = run(bars, Cfg(be_on=True, **NOEXIT), signals=sig(0, 1, 100.0, 98.0, 2.0))
        self.assertIn((1, "TP1", 1.0, 102.0), sim.events)
        self.assertNotIn(1, [e[0] for e in sim.events if e[1] == "STOP"])
        self.assertIn((2, "STOP", 1.0, 100.0), sim.events)

    def test_single_unit_goes_to_tp2(self):
        self.assertEqual(parts(1.0, Cfg()), (0.0, 1.0, 0.0))
        self.assertEqual(parts(2.0, Cfg(use3=True)), (1.0, 1.0, 0.0))
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 102.2, 99.5, 102), Bar(102, 104.5, 101.8, 104)]
        _, sim, _ = run(bars, Cfg(**NOEXIT), signals=sig(0, 1, 100.0, 98.0, 1.0))
        self.assertNotIn("TP1", [e[1] for e in sim.events])
        self.assertTrue(sim.touched[0])
        self.assertIn((2, "TP2", 1.0, 104.0), sim.events)

    def test_configurable_allocations_conserve_quantity(self):
        self.assertEqual(parts(10.0, Cfg(use3=True, alloc3a=50, alloc3b=30)), (5.0, 3.0, 2.0))
        self.assertEqual(parts(10.0, Cfg(alloc2=70)), (7.0, 3.0, 0.0))
        for use3 in (False, True):
            for a in (1, 33, 50, 70, 98):
                for step in (1.0, 0.01):
                    cfg = Cfg(use3=use3, qty_step=step, alloc2=a, alloc3a=min(a, 60), alloc3b=30)
                    for units in range(1, 2001):
                        q = units * step
                        p = parts(q, cfg)
                        self.assertTrue(min(p) >= 0)
                        self.assertAlmostEqual(sum(p), q, delta=step * 1e-6)
                        self.assertGreater(p[1], 0)               # TP2 always carries units
                        if units >= 2:
                            self.assertGreater(p[0], 0)
                        if use3 and units >= 3:
                            self.assertGreater(p[2], 0)

    def test_limit_needs_trade_through_and_expires(self):
        bars = [Bar(101, 101.5, 100.5, 101), Bar(101, 101.2, 100.0, 100.8), Bar(100.8, 101, 100.6, 100.9), Bar(101, 101.3, 100.7, 101), Bar(101, 101.1, 100.8, 101)]
        cfg = Cfg(limit=True, limit_bars=3, **NOEXIT)
        _, sim, _ = run(bars, cfg, signals=sig(0, 1, 100.0, 98.0, 2.0))
        self.assertNotIn("FILL", [e[1] for e in sim.events])  # low touched 100.0 but not 99.75
        self.assertIn((3, "CANCEL", 0, None), sim.events)

    def test_limit_intrabar_fill_defers_targets_and_gap_fill(self):
        bars = [Bar(101, 101.5, 100.5, 101), Bar(101, 102.5, 99.7, 102.2), Bar(102.2, 102.4, 101.5, 102)]
        _, sim, _ = run(bars, Cfg(limit=True, **NOEXIT), signals=sig(0, 1, 100.0, 98.0, 2.0))
        self.assertIn((1, "FILL", 2.0, 100.0), sim.events)
        self.assertNotIn(1, [e[0] for e in sim.events if e[1].startswith("TP")])  # TP1 102 not credited
        self.assertIn((2, "TP1", 1.0, 102.2), sim.events)      # next bar opens above TP1 -> open fill
        bars = [Bar(101, 101.5, 100.5, 101), Bar(99.5, 99.8, 98.9, 99.6)]
        _, sim, _ = run(bars, Cfg(limit=True, **NOEXIT), signals=sig(0, 1, 100.0, 98.0, 2.0))
        self.assertIn((1, "FILL", 2.0, 99.5), sim.events)      # gap through the limit fills at the open

    def test_costs_reduce_result_exactly(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 104.5, 99.5, 104)]
        cfg = Cfg(comm=1.0, spread=0.5, slip_ticks=1, **NOEXIT)
        _, sim, _ = run(bars, cfg, signals=sig(0, 1, 100.0, 98.0, 2.0))
        res = sim.results[0]
        self.assertAlmostEqual(res["gross"], 2.0 + 4.0)        # TP1 +2 on 1 unit, TP2 +4 on 1 unit
        entry_cost = 1.0 * 2 + (0.25 + 0.25) * 2               # commission + half spread + 1 tick slip
        exit_cost = (1.0 * 1 + 0.25 * 1) * 2                   # two limit fills: commission + half spread
        self.assertAlmostEqual(res["cost"], entry_cost + exit_cost)
        self.assertAlmostEqual(res["r"], (6.0 - entry_cost - exit_cost) / 4.0)

    def test_early_exit_on_structure_break_next_open(self):
        cfg = Cfg()
        sim = Sim(cfg)
        none = dict(break_up=False, break_dn=False)
        sim.step(0, Bar(99, 100.5, 99, 100), dict(signal=1, ref=100.0, stop=98.0, risk=2.0, qty=2.0), none)
        sim.step(1, Bar(100, 100.8, 99.6, 99.8), dict(signal=0), dict(break_up=False, break_dn=True))
        self.assertIn((1, "EXIT_REQUEST", "STRUCTURE", None), sim.events)
        sim.step(2, Bar(99.7, 100, 99.2, 99.5), dict(signal=0), none)
        self.assertIn((2, "EXIT_STRUCTURE", 2.0, 99.7), sim.events)

    def test_cooldown_zero_blocks_same_bar_reentry(self):
        bars = [Bar(99, 100.5, 99, 100), Bar(100, 100.2, 97, 97.5), Bar(97.5, 98, 97, 97.8)]
        signals = {0: (1, 100.0, 98.0, 2.0), 1: (-1, 97.5, 99.5, 2.0), 2: (-1, 97.8, 99.5, 2.0)}
        _, sim, _ = run(bars, Cfg(cooldown=0, **NOEXIT), signals=signals)
        self.assertEqual([e[0] for e in sim.events if e[1] == "ENTER"], [0, 2])

    def test_targets_ordered_after_rounding(self):
        cfg = Cfg(tick=0.25, r1=1.0, r2=1.01, r3=1.02)
        self.assertTrue(100 < targets(1, 100.0, 0.3, cfg)[0] < targets(1, 100.0, 0.3, cfg)[1] < targets(1, 100.0, 0.3, cfg)[2])
        t = targets(-1, 100.0, 0.3, cfg)
        self.assertTrue(100 > t[0] > t[1] > t[2])
        self.assertAlmostEqual(ceil_tick(1.1, 0.1), 1.1)
        self.assertAlmostEqual(floor_tick(0.3, 0.1), 0.3)


def random_bars(rng, n):
    bars, c = [], 100.0
    for i in range(n):
        o = round((c + rng.gauss(0, 0.15)) * 4) / 4
        c = round((o + rng.gauss(0, 0.9)) * 4) / 4
        h = max(o, c) + round(abs(rng.gauss(0, 0.5)) * 4) / 4
        lo = min(o, c) - round(abs(rng.gauss(0, 0.5)) * 4) / 4
        up = (i // 150) % 2 == 0
        bars.append(Bar(o, h, lo, c, bias=1 if up else -1, vwap_long=rng.random() < 0.8, vwap_short=rng.random() < 0.8,
                        pull_long=up and rng.random() < 0.03, pull_short=(not up) and rng.random() < 0.03, ema=c))
    return bars


class Properties(unittest.TestCase):
    def test_random_series(self):
        rng = random.Random(20261029)
        n_trades = n_icc = n_limit_fills = 0
        for _ in range(150):
            cfg = Cfg(framework=rng.choice(["ICC hybrid", "ICC hybrid", "Trend pullback (baseline)"]), use3=rng.random() < 0.5,
                      be_on=rng.random() < 0.5, trail_atr=rng.choice([0.0, 0.0, 2.0]), cooldown=rng.choice([0, 1, 3]),
                      hold_bars=rng.choice([5, 20, 60]), risk_cash=rng.choice([3.0, 50.0, 400.0]), limit=rng.random() < 0.4,
                      corr_type=rng.choice(["Retracement or retest", "Retracement 38-79%", "Broken-level retest"]),
                      stop_method=rng.choice(["Structure", "ATR", "Wider of both"]), exit_on_choch=rng.random() < 0.5,
                      comm=rng.choice([0.0, 1.0]), spread=rng.choice([0.0, 0.25]), slip_ticks=rng.choice([0, 1]))
            bars = random_bars(rng, 600)
            eng, sim, out = run(bars, cfg)
            stage, broken = {}, {"BOS_UP": set(), "CHOCH_UP": set(), "BOS_DN": set(), "CHOCH_DN": set()}
            for e in eng.log:
                i, kind = e[0], e[1]
                if kind == "INDICATION":
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
            levels_up = [e[2] for e in eng.log if e[1] in ("BOS_UP", "CHOCH_UP")]
            cur = None
            for ev in sim.events:
                i, kind = ev[0], ev[1]
                if kind == "ENTER":
                    self.assertIsNone(cur)
                    cur = {"enter": i, "qty": out[i]["qty"], "closed": 0.0, "fill": None}
                elif kind == "CANCEL":
                    self.assertTrue(cfg.limit)
                    self.assertEqual(i - cur["enter"], cfg.limit_bars)
                    cur = None
                elif kind == "FILL":
                    if cfg.limit:
                        self.assertTrue(1 <= i - cur["enter"] <= cfg.limit_bars)
                        n_limit_fills += 1
                    else:
                        self.assertEqual(i, cur["enter"] + 1)
                    cur["fill"] = i
                elif kind == "CLOSED_R":
                    self.assertAlmostEqual(cur["closed"], cur["qty"], delta=1e-6)
                    n_trades += 1
                    cur = None
                elif kind == "EXIT_REQUEST":
                    self.assertIsNotNone(cur["fill"])
                else:
                    self.assertIsNotNone(cur["fill"], f"{kind} before fill")
                    cur["closed"] += ev[2]
            for r in out:
                if r["signal"] != 0:
                    s, stop, risk, ref = r["signal"], r["stop"], r["risk"], r["ref"]
                    t1, t2, t3 = targets(s, ref, risk, cfg)
                    seq = [stop, ref, t1, t2, t3] if s == 1 else [t3, t2, t1, ref, stop]
                    self.assertEqual(seq, sorted(seq))
                    self.assertEqual(len(set(seq)), 5)
                    self.assertGreaterEqual(risk, cfg.min_stop - 1e-9)
                    self.assertLessEqual(risk, cfg.max_stop + 1e-9)
                    if cfg.limit:
                        self.assertTrue(ref <= bars[r["i"]].c if s == 1 else ref >= bars[r["i"]].c)
            for res in sim.results:
                self.assertGreaterEqual(res["cost"], 0)
                self.assertLessEqual(res["net"] if "net" in res else res["r"], res["gross"] + 1e-9)
        self.assertGreater(n_trades, 100)
        self.assertGreater(n_icc, 20)
        self.assertGreater(n_limit_fills, 10)


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
            # "Win rate" appears only as a measured-statistics column header, never as a claim.
            for bad in ("probability", "accuracy", "institutional", "varip", "guarantee", "confidence"):
                self.assertNotIn(bad, low)
            for lit in re.findall(r'"(?:[^"\\]|\\.)*"', low):
                self.assertNotRegex(lit, r"\d\s*%\s*(win|accura|success|probab|hit rate)", lit)  # no % claims

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
            declared = set(re.findall(r"^\s*(?:var\s+)?(?:(?:int|float|bool|string|color|table|box|line|label|SessTrack|array<\w+>)\s+)?([A-Za-z_]\w*)\s*=(?!=)", text, re.M))
            declared |= {n for tup in re.findall(r"\[([^\]]+)\]\s*=(?!=)", text) for n in re.split(r"\s*,\s*", tup)}
            for name in re.findall(r"^\s*([A-Za-z_]\w*)\s*(?::=|\+=|-=)", text, re.M):
                self.assertIn(name, declared, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
