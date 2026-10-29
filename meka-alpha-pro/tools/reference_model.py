#!/usr/bin/env python3
"""Line-by-line Python port of the 4.0-r2 decision logic, for deterministic scenario tests.

What it ports: ICC state machine, trend-pullback candidate, pivot availability, candidate
validation (tick rounding, stop limits, room, quantity), tranche allocation, target building,
and the INDICATOR simulation (next-open fill, stop-first, gaps, BE/trail timing, close-based
exits, cooldown). Trend/quality/window gates and ATR are injected per bar instead of computed.

What it is NOT: Pine execution, TradingView's session functions, or the broker emulator.
A passing test shows the intended rules are internally consistent; it does not prove that the
Pine text compiles or behaves identically inside TradingView.
"""
from dataclasses import dataclass, field
import math

EPS = 1e-9


@dataclass
class Bar:
    o: float
    h: float
    l: float
    c: float
    atr: float = 1.0
    trend_long: bool = True
    trend_short: bool = False
    quality: bool = True
    entry_gate: bool = True
    in_window: bool = True
    pull_long: bool = False
    pull_short: bool = False


@dataclass
class Cfg:
    tick: float = 0.25
    strength: int = 2
    expiry: int = 24
    displace: float = 0.6
    retest_pad: float = 0.25
    bos_ticks: int = 1
    stop_pad: float = 0.15
    min_stop: float = 0.6
    max_stop: float = 3.0
    r1: float = 1.0
    r2: float = 2.0
    r3: float = 3.0
    use_tp3: bool = False
    room_gate: bool = True
    engine: str = "ICC"
    risk_cash: float = 50.0
    unit_usd: float = 1.0
    qty_step: float = 1.0
    max_qty: float = 100000.0
    cooldown: int = 3
    hold_bars: int = 48
    be_on: bool = False
    trail_on: bool = False
    trail_atr: float = 2.0
    gap_max_risk: float = 1.5


def floor_tick(x, t):
    return math.floor(x / t + EPS) * t


def ceil_tick(x, t):
    return math.ceil(x / t - EPS) * t


def qty_for(distance, cfg):
    raw = cfg.risk_cash / (distance * cfg.unit_usd) if distance > 0 else 0.0
    return math.floor(min(raw, cfg.max_qty) / cfg.qty_step + EPS) * cfg.qty_step


def parts(q, cfg):
    units = int(round(q / cfg.qty_step))
    need = 3 if cfg.use_tp3 else 2
    u1 = int(math.floor(units * (0.4 if cfg.use_tp3 else 0.5))) if units >= need else 0
    u2 = max(1, int(math.floor(units * 0.3))) if cfg.use_tp3 and units >= need else 0
    return u1 * cfg.qty_step, u2 * cfg.qty_step, (units - u1 - u2) * cfg.qty_step


def targets(s, ref, risk, cfg):
    t = cfg.tick
    if s == 1:
        t1 = ceil_tick(ref + risk * cfg.r1, t)
        t2 = max(ceil_tick(ref + risk * cfg.r2, t), t1 + t)
        t3 = max(ceil_tick(ref + risk * cfg.r3, t), t2 + t)
    else:
        t1 = floor_tick(ref - risk * cfg.r1, t)
        t2 = min(floor_tick(ref - risk * cfg.r2, t), t1 - t)
        t3 = min(floor_tick(ref - risk * cfg.r3, t), t2 - t)
    return t1, t2, t3


def pivot(values, i, s, high=True):
    """ta.pivothigh/low(src, s, s) evaluated on bar i -> value of bar i-s, or None."""
    j = i - s
    if j - s < 0:
        return None
    v = values[j]
    others = values[j - s:j] + values[j + 1:i + 1]
    if high:
        return v if all(v > x for x in others) else None
    return v if all(v < x for x in others) else None


@dataclass
class Engine:
    cfg: Cfg
    swing_high: float = None
    swing_low: float = None
    high_id: int = None
    low_id: int = None
    consumed_high: int = None
    consumed_low: int = None
    state: int = 0
    side: int = 0
    ind_bar: int = None
    cor_bar: int = None
    broken: float = None
    ind_atr: float = None
    invalidation: float = None
    cor_low: float = None
    cor_high: float = None
    trigger: float = None
    log: list = field(default_factory=list)

    def step(self, i, bars):
        cfg, b = self.cfg, bars[i]
        prev = bars[i - 1] if i > 0 else b
        prev_atr = prev.atr
        buf = cfg.bos_ticks * cfg.tick
        bos_long = self.swing_high is not None and b.c > self.swing_high + buf and prev.c <= self.swing_high + buf
        bos_short = self.swing_low is not None and b.c < self.swing_low - buf and prev.c >= self.swing_low - buf
        cand, cstop, name = 0, None, ""
        if self.state != 0:
            invalid = (b.l <= self.invalidation or not b.trend_long) if self.side == 1 else (b.h >= self.invalidation or not b.trend_short)
            expired = i - self.ind_bar > cfg.expiry
            if invalid or expired or not b.in_window:
                self.log.append((i, "END", "INVALID" if invalid else "EXPIRED" if expired else "BLOCKED"))
                self.state = 0
            elif self.state == 1 and i > self.ind_bar:
                lo, hi = self.broken - cfg.retest_pad * self.ind_atr, self.broken + cfg.retest_pad * self.ind_atr
                revisit = b.l <= hi and b.h >= lo
                hold = b.c >= lo if self.side == 1 else b.c <= hi
                if revisit and hold:
                    self.cor_low, self.cor_high = b.l, b.h
                    self.trigger = b.h if self.side == 1 else b.l
                    self.cor_bar, self.state = i, 2
                    self.log.append((i, "CORRECTION", self.side))
            elif self.state == 2 and i > self.cor_bar:
                cont = (b.c > self.trigger + buf and b.c > b.o) if self.side == 1 else (b.c < self.trigger - buf and b.c < b.o)
                if cont:
                    cand = self.side
                    cstop = (min(self.cor_low, b.l) - cfg.stop_pad * self.ind_atr) if self.side == 1 else (max(self.cor_high, b.h) + cfg.stop_pad * self.ind_atr)
                    name, self.state = "ICC", 0
                    self.log.append((i, "CONTINUATION", self.side))
                else:
                    self.cor_low, self.cor_high = min(self.cor_low, b.l), max(self.cor_high, b.h)
        elif cfg.engine != "Trend pullback" and b.entry_gate and b.quality:
            fresh_l = self.consumed_high is None or self.high_id != self.consumed_high
            fresh_s = self.consumed_low is None or self.low_id != self.consumed_low
            if bos_long and b.trend_long and fresh_l and b.c - b.o >= cfg.displace * prev_atr:
                self.side, self.broken, self.invalidation = 1, self.swing_high, b.l - cfg.stop_pad * prev_atr
                self.ind_atr, self.ind_bar, self.consumed_high, self.state = prev_atr, i, self.high_id, 1
                self.log.append((i, "INDICATION", 1, self.high_id))
            elif bos_short and b.trend_short and fresh_s and b.o - b.c >= cfg.displace * prev_atr:
                self.side, self.broken, self.invalidation = -1, self.swing_low, b.h + cfg.stop_pad * prev_atr
                self.ind_atr, self.ind_bar, self.consumed_low, self.state = prev_atr, i, self.low_id, 1
                self.log.append((i, "INDICATION", -1, self.low_id))
        if cand == 0 and self.state == 0 and cfg.engine != "ICC":
            if b.pull_long:
                cand, cstop, name = 1, min(b.l, prev.l) - cfg.stop_pad * prev_atr, "Trend pullback"
            elif b.pull_short:
                cand, cstop, name = -1, max(b.h, prev.h) + cfg.stop_pad * prev_atr, "Trend pullback"
        ph = pivot([x.h for x in bars], i, cfg.strength, True)
        pl = pivot([x.l for x in bars], i, cfg.strength, False)
        if ph is not None:
            self.swing_high, self.high_id = ph, i - cfg.strength
            self.log.append((i, "PIVOT_HIGH_AVAILABLE", ph, i - cfg.strength))
        if pl is not None:
            self.swing_low, self.low_id = pl, i - cfg.strength
            self.log.append((i, "PIVOT_LOW_AVAILABLE", pl, i - cfg.strength))
        # validation
        if cand == 0:
            return 0, None, None, 0.0, name, 0
        t = cfg.tick
        pstop = floor_tick(cstop, t) if cand == 1 else ceil_tick(cstop, t)
        prisk = b.c - pstop if cand == 1 else pstop - b.c
        stop_ok = prisk >= max(cfg.min_stop * b.atr, t) and prisk <= cfg.max_stop * b.atr
        pq = qty_for(prisk, cfg) if stop_ok else 0.0
        opp = self.swing_high if cand == 1 else self.swing_low
        room = None if opp is None else (opp - b.c if cand == 1 else b.c - opp)
        room_ok = (not cfg.room_gate) or room is None or room <= 0 or room >= prisk * cfg.r1 + t
        ok = b.entry_gate and b.quality and stop_ok and room_ok and pq >= cfg.qty_step
        return (cand if ok else 0), pstop, prisk, pq, name, cand


@dataclass
class Sim:
    """Port of src/indicator_exec.pine (without alerts/day gates)."""
    cfg: Cfg
    side: int = 0
    pending: bool = False
    ref: float = None
    fill: float = None
    stop: float = None
    init_stop: float = None
    risk: float = None
    t1: float = None
    t2: float = None
    t3: float = None
    qty: float = 0.0
    p1: float = 0.0
    p2: float = 0.0
    pf: float = 0.0
    remaining: float = 0.0
    done1: bool = False
    done2: bool = False
    done_f: bool = False
    trig: bool = False
    sub_bar: int = None
    fill_bar: int = None
    last_closed: int = None
    closing: str = ""
    ratio: float = None
    trade_r: float = 0.0
    ambiguous: int = 0
    events: list = field(default_factory=list)

    def _r(self, px, q):
        return (px - self.fill) * self.side * q / (self.qty * self.risk)

    def step(self, i, b, signal, pstop, prisk, pq, force_exit_reason=""):
        cfg = self.cfg
        ev = []
        exited = filled_now = False
        if self.pending and i > self.sub_bar:
            self.fill, self.fill_bar, self.pending = b.o, i, False
            self.remaining, self.trade_r = self.qty, 0.0
            self.ratio = ((self.fill - self.init_stop) if self.side == 1 else (self.init_stop - self.fill)) / self.risk
            filled_now = True
            ev.append(("FILL", self.qty, b.o))
        if self.side != 0 and not self.pending:
            s = self.side
            final_t = self.t3 if cfg.use_tp3 else self.t2
            stop_hit = b.l <= self.stop if s == 1 else b.h >= self.stop
            hit1 = self.p1 > 0 and not self.done1 and (b.h >= self.t1 if s == 1 else b.l <= self.t1)
            hit2 = self.p2 > 0 and not self.done2 and (b.h >= self.t2 if s == 1 else b.l <= self.t2)
            hitf = not self.done_f and (b.h >= final_t if s == 1 else b.l <= final_t)
            if self.closing:
                self.trade_r += self._r(b.o, self.remaining)
                ev.append(("EXIT_" + self.closing, self.remaining, b.o))
                self.remaining, exited = 0.0, True
            elif stop_hit:
                px = min(b.o, self.stop) if s == 1 else max(b.o, self.stop)
                if hit1 or hit2 or hitf:
                    self.ambiguous += 1
                self.trade_r += self._r(px, self.remaining)
                ev.append(("STOP", self.remaining, px))
                self.remaining, exited = 0.0, True
            else:
                fav = (lambda t: max(b.o, t)) if s == 1 else (lambda t: min(b.o, t))
                if hit1:
                    self.trade_r += self._r(fav(self.t1), self.p1)
                    self.remaining -= self.p1
                    self.done1 = True
                    ev.append(("TP1", self.p1, fav(self.t1)))
                if hit2:
                    self.trade_r += self._r(fav(self.t2), self.p2)
                    self.remaining -= self.p2
                    self.done2 = True
                    ev.append(("TP2", self.p2, fav(self.t2)))
                if hitf:
                    self.trade_r += self._r(fav(final_t), self.remaining)
                    ev.append(("FINAL", self.remaining, fav(final_t)))
                    self.remaining, self.done_f, exited = 0.0, True, True
                if self.remaining > 0:
                    self.trig = self.trig or (b.h >= self.t1 if s == 1 else b.l <= self.t1)
                    if cfg.be_on and self.trig:
                        self.stop = max(self.stop, floor_tick(self.fill, cfg.tick)) if s == 1 else min(self.stop, ceil_tick(self.fill, cfg.tick))
                    if cfg.trail_on and self.trig:
                        self.stop = max(self.stop, floor_tick(b.c - cfg.trail_atr * b.atr, cfg.tick)) if s == 1 else min(self.stop, ceil_tick(b.c + cfg.trail_atr * b.atr, cfg.tick))
                    why = ("GAP_RISK" if filled_now and cfg.gap_max_risk > 0 and self.ratio > cfg.gap_max_risk
                           else force_exit_reason if force_exit_reason
                           else "MAX_HOLD" if i - self.fill_bar >= cfg.hold_bars else "")
                    if why:
                        self.closing = why
            if exited:
                self.last_closed, self.side, self.closing = i, 0, ""
                ev.append(("CLOSED_R", round(self.trade_r, 6), None))
        entered = False
        rested = self.last_closed is None or i - self.last_closed > cfg.cooldown
        if signal != 0 and self.side == 0 and rested:
            self.side, self.ref, self.fill = signal, b.c, None
            self.stop = self.init_stop = pstop
            self.risk = prisk
            self.t1, self.t2, self.t3 = targets(signal, b.c, prisk, cfg)
            self.qty = pq
            self.p1, self.p2, self.pf = parts(pq, cfg)
            self.remaining, self.done1, self.done2, self.done_f, self.trig = 0.0, False, False, False, False
            self.pending, self.closing, self.ratio, self.trade_r, self.sub_bar = True, "", None, 0.0, i
            entered = True
            ev.append(("ENTER", signal, b.c))
        self.events.extend((i,) + e for e in ev)
        return ev, entered, exited


def run(bars, cfg, signals=None):
    """Run engine + simulation. `signals` optionally overrides engine output per bar index with
    (signal, stop, risk, qty) tuples, to test execution rules in isolation."""
    eng, sim = Engine(cfg), Sim(cfg)
    out = []
    for i, b in enumerate(bars):
        sig, pstop, prisk, pq, name, cand = eng.step(i, bars)
        if signals is not None:
            sig, pstop, prisk, pq = signals.get(i, (0, None, None, 0.0))
        ev, entered, exited = sim.step(i, b, sig, pstop, prisk, pq)
        out.append(dict(i=i, signal=sig, cand=cand, stop=pstop, risk=prisk, qty=pq, events=ev))
    return eng, sim, out
