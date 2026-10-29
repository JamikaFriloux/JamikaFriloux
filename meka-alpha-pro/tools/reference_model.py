#!/usr/bin/env python3
"""Python port of the MEKA ALPHA PRO 4.0 decision rules, for deterministic tests.

Ported: swing structure (BOS / CHoCH, each swing broken once, commit-after-logic), liquidity
sweeps of the latest swing, the ICC state machine (indication -> correction -> continuation with
retracement / retest zone, impulse-origin invalidation, deepening-correction trigger), the trend
pullback baseline, candidate validation (entry reference for market / limit, structure / ATR /
wider stops, tick rounding, min / max stop, room, size), whole-unit target allocation, target
building, and the INDICATOR simulation (next-open and limit fills, conservative intrabar rules,
stop-first, gaps, break-even / ATR trail timing, close-based early exits, modeled costs).

Injected per bar instead of computed: ATR, higher-timeframe bias, quality / entry gates, window,
VWAP side and volume confirmation. Session tracking and the opening-range baseline are not ported.

This is NOT Pine and NOT TradingView's broker emulator. Passing tests means the intended rules are
internally consistent; it does not prove the Pine text behaves identically inside TradingView.
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
    bias: int = 1            # confirmed higher-timeframe bias: 1, -1 or 0
    quality: bool = True
    entry_gate: bool = True
    in_window: bool = True
    vwap_long: bool = True   # close on the long side of VWAP (or filter off)
    vwap_short: bool = True
    vol_ok: bool = True
    pull_long: bool = False
    pull_short: bool = False
    ema: float = None


@dataclass
class Cfg:
    tick: float = 0.25
    strength: int = 2
    expiry: int = 24
    disp: float = 0.6
    retest_pad: float = 0.25
    fib_shallow: float = 0.382
    fib_deep: float = 0.786
    corr_type: str = "Retracement or retest"
    allow_choch: bool = True
    need_sweep: bool = False
    bos_ticks: int = 1
    stop_pad: float = 0.15
    stop_method: str = "Structure"
    atr_stop: float = 1.5
    min_stop: float = 0.6
    max_stop: float = 3.0
    r1: float = 1.0
    r2: float = 2.0
    r3: float = 3.0
    use3: bool = False
    alloc2: int = 50
    alloc3a: int = 50
    alloc3b: int = 30
    room_gate: bool = True
    framework: str = "ICC hybrid"
    risk_cash: float = 50.0
    unit_usd: float = 1.0
    qty_step: float = 1.0
    max_qty: float = 100000.0
    cooldown: int = 3
    hold_bars: int = 60
    be_on: bool = False
    trail_atr: float = 0.0       # 0 = off; otherwise ATR trail after TP1 is touched
    gap_max_risk: float = 1.5
    exit_on_choch: bool = True
    exit_on_bias: bool = False
    limit: bool = False
    limit_bars: int = 3
    fill_ticks: int = 1
    same_bar: str = "conservative"   # or "emulator"
    comm: float = 0.0
    spread: float = 0.0
    slip_ticks: int = 0


def floor_tick(x, t):
    return math.floor(x / t + EPS) * t


def ceil_tick(x, t):
    return math.ceil(x / t - EPS) * t


def qty_for(distance, cfg):
    raw = cfg.risk_cash / (distance * cfg.unit_usd) if distance > 0 else 0.0
    return math.floor(min(raw, cfg.max_qty) / cfg.qty_step + EPS) * cfg.qty_step


def parts(q, cfg):
    units = int(round(q / cfg.qty_step))
    u1 = u2 = u3 = 0
    if cfg.use3 and units >= 3:
        u1 = max(1, min(units - 2, int(math.floor(units * cfg.alloc3a / 100.0))))
        u2 = max(1, min(units - u1 - 1, int(math.floor(units * cfg.alloc3b / 100.0))))
        u3 = units - u1 - u2
    elif units >= 2:
        u1 = max(1, min(units - 1, int(math.floor(units * (cfg.alloc3a if cfg.use3 else cfg.alloc2) / 100.0))))
        u2 = units - u1
    else:
        u2 = units
    return u1 * cfg.qty_step, u2 * cfg.qty_step, u3 * cfg.qty_step


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
    broken_high: int = None
    broken_low: int = None
    trend: int = 0
    state: int = 0
    side: int = 0
    ind_bar: int = None
    cor_bar: int = None
    broken: float = None
    origin: float = None
    ext: float = None
    ind_atr: float = None
    cor_ext: float = None
    trigger: float = None
    swept: bool = False
    log: list = field(default_factory=list)

    def step(self, i, bars):
        cfg, b = self.cfg, bars[i]
        prev = bars[i - 1] if i > 0 else b
        buf = cfg.bos_ticks * cfg.tick
        break_up = self.swing_high is not None and b.c > self.swing_high + buf and self.high_id != self.broken_high
        break_dn = self.swing_low is not None and b.c < self.swing_low - buf and self.low_id != self.broken_low
        choch_up = break_up and self.trend != 1
        choch_dn = break_dn and self.trend != -1
        sweep_low = self.swing_low is not None and b.l < self.swing_low < b.c and prev.l >= self.swing_low
        sweep_high = self.swing_high is not None and b.h > self.swing_high > b.c and prev.h <= self.swing_high
        use_fib = cfg.corr_type != "Broken-level retest"
        use_retest = cfg.corr_type != "Retracement 38-79%"
        cand, cstop, clevel, name = 0, None, None, ""
        if self.state != 0:
            s = self.side
            broke_origin = b.c < self.origin if s == 1 else b.c > self.origin
            bias_lost = b.bias != s
            expired = i - self.ind_bar > cfg.expiry
            if broke_origin or bias_lost or expired or not b.in_window:
                self.log.append((i, "END", "ORIGIN" if broke_origin else "BIAS" if bias_lost else "EXPIRED" if expired else "BLOCKED"))
                self.state = 0
            elif self.state == 1 and i > self.ind_bar:
                leg = abs(self.ext - self.origin)
                near = self.ext - cfg.fib_shallow * leg if s == 1 else self.ext + cfg.fib_shallow * leg
                hit_fib = use_fib and (b.l <= near if s == 1 else b.h >= near)
                hit_rt = use_retest and (b.l <= self.broken + cfg.retest_pad * self.ind_atr if s == 1 else b.h >= self.broken - cfg.retest_pad * self.ind_atr)
                if hit_fib or hit_rt:
                    self.state, self.cor_bar = 2, i
                    self.cor_ext = b.l if s == 1 else b.h
                    self.trigger = b.h if s == 1 else b.l
                    self.swept = (sweep_low or b.l < self.origin) if s == 1 else (sweep_high or b.h > self.origin)
                    self.log.append((i, "CORRECTION", s, self.trigger))
                else:
                    self.ext = max(self.ext, b.h) if s == 1 else min(self.ext, b.l)
            elif self.state == 2 and i > self.cor_bar:
                brk = (b.c > self.trigger + buf and b.c > b.o) if s == 1 else (b.c < self.trigger - buf and b.c < b.o)
                side_ok = b.vwap_long if s == 1 else b.vwap_short
                if brk and side_ok and b.vol_ok and (not cfg.need_sweep or self.swept):
                    cand = s
                    cstop = (min(self.cor_ext, b.l) - cfg.stop_pad * self.ind_atr) if s == 1 else (max(self.cor_ext, b.h) + cfg.stop_pad * self.ind_atr)
                    clevel, name, self.state = self.trigger, "ICC continuation", 0
                    self.log.append((i, "CONTINUATION", s, self.trigger))
                else:
                    deeper = b.l < self.cor_ext if s == 1 else b.h > self.cor_ext
                    if deeper:
                        self.cor_ext = b.l if s == 1 else b.h
                        self.trigger = b.h if s == 1 else b.l
                    self.swept = self.swept or ((sweep_low or b.l < self.origin) if s == 1 else (sweep_high or b.h > self.origin))
        elif cfg.framework == "ICC hybrid" and b.entry_gate and b.quality:
            up = break_up and b.bias == 1 and (cfg.allow_choch or not choch_up) and b.c - b.o >= cfg.disp * prev.atr and self.swing_low is not None and self.swing_low < b.c
            dn = break_dn and b.bias == -1 and (cfg.allow_choch or not choch_dn) and b.o - b.c >= cfg.disp * prev.atr and self.swing_high is not None and self.swing_high > b.c
            if up or dn:
                self.side = 1 if up else -1
                self.broken = self.swing_high if up else self.swing_low
                self.origin = self.swing_low if up else self.swing_high
                self.ext = b.h if up else b.l
                self.ind_atr, self.ind_bar, self.swept, self.state = prev.atr, i, False, 1
                self.log.append((i, "INDICATION", self.side, self.high_id if up else self.low_id, "CHoCH" if (choch_up if up else choch_dn) else "BOS"))
        if cand == 0 and cfg.framework == "Trend pullback (baseline)":
            if b.pull_long and b.vwap_long:
                cand, cstop, clevel, name = 1, min(b.l, prev.l) - cfg.stop_pad * prev.atr, b.ema, "Trend pullback"
            elif b.pull_short and b.vwap_short:
                cand, cstop, clevel, name = -1, max(b.h, prev.h) + cfg.stop_pad * prev.atr, b.ema, "Trend pullback"
        # Commit structure after the setup logic.
        if break_up:
            self.broken_high, self.trend = self.high_id, 1
            self.log.append((i, "CHOCH_UP" if choch_up else "BOS_UP", self.swing_high))
        if break_dn:
            self.broken_low, self.trend = self.low_id, -1
            self.log.append((i, "CHOCH_DN" if choch_dn else "BOS_DN", self.swing_low))
        ph = pivot([x.h for x in bars], i, cfg.strength, True)
        pl = pivot([x.l for x in bars], i, cfg.strength, False)
        if ph is not None:
            self.swing_high, self.high_id = ph, i - cfg.strength
            self.log.append((i, "PIVOT_HIGH_AVAILABLE", ph, i - cfg.strength))
        if pl is not None:
            self.swing_low, self.low_id = pl, i - cfg.strength
            self.log.append((i, "PIVOT_LOW_AVAILABLE", pl, i - cfg.strength))
        events = dict(break_up=break_up, break_dn=break_dn, sweep_low=sweep_low, sweep_high=sweep_high)
        if cand == 0:
            return dict(signal=0, cand=0, events=events)
        t = cfg.tick
        ref = (floor_tick(min(clevel, b.c), t) if cand == 1 else ceil_tick(max(clevel, b.c), t)) if cfg.limit else b.c
        atr_stop = ref - cfg.atr_stop * b.atr if cand == 1 else ref + cfg.atr_stop * b.atr
        raw = cstop if cfg.stop_method == "Structure" else atr_stop if cfg.stop_method == "ATR" else (min(cstop, atr_stop) if cand == 1 else max(cstop, atr_stop))
        pstop = floor_tick(raw, t) if cand == 1 else ceil_tick(raw, t)
        prisk = ref - pstop if cand == 1 else pstop - ref
        tight = prisk < max(cfg.min_stop * b.atr, t)
        wide = prisk > cfg.max_stop * b.atr
        pq = qty_for(prisk, cfg) if not tight and not wide else 0.0
        opp = self.swing_high if cand == 1 else self.swing_low
        room = None if opp is None else (opp - ref if cand == 1 else ref - opp)
        room_ok = (not cfg.room_gate) or room is None or room <= 0 or room >= prisk * cfg.r1 + t
        ok = b.entry_gate and b.quality and not tight and not wide and room_ok and pq >= cfg.qty_step
        return dict(signal=cand if ok else 0, cand=cand, ref=ref, stop=pstop, risk=prisk, qty=pq, tight=tight, wide=wide, room_ok=room_ok, name=name, events=events)


@dataclass
class Sim:
    """Port of src/indicator_exec.pine (alerts, day gates and statistics omitted)."""
    cfg: Cfg
    side: int = 0
    pending: bool = False
    is_limit: bool = False
    ref: float = None
    fill: float = None
    stop: float = None
    init_stop: float = None
    risk: float = None
    t: tuple = (None, None, None)
    qty: float = 0.0
    p: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    done: list = field(default_factory=lambda: [False, False, False])
    touched: list = field(default_factory=lambda: [False, False, False])
    remaining: float = 0.0
    trig: bool = False
    sub_bar: int = None
    fill_bar: int = None
    last_closed: int = None
    closing: str = ""
    ratio: float = None
    gross: float = 0.0
    cost: float = 0.0
    planned_cash: float = None
    ambiguous: int = 0
    events: list = field(default_factory=list)
    results: list = field(default_factory=list)

    def _cost(self, q, market):
        cfg = self.cfg
        return cfg.comm * q + (cfg.spread / 2 + (cfg.slip_ticks * cfg.tick if market else 0.0)) * q * cfg.unit_usd

    def _cash(self, px, q):
        return (px - self.fill) * self.side * q * self.cfg.unit_usd

    def step(self, i, b, sig, ev):
        cfg = self.cfg
        out = []
        exited = fill_now = fill_at_open = False
        if self.pending and i > self.sub_bar:
            s, tk = self.side, cfg.tick
            gap = self.is_limit and (b.o <= self.ref if s == 1 else b.o >= self.ref)
            through = self.is_limit and (b.l <= self.ref - cfg.fill_ticks * tk if s == 1 else b.h >= self.ref + cfg.fill_ticks * tk)
            if not self.is_limit or gap or through:
                fill_at_open = (not self.is_limit) or gap
                self.fill = b.o if fill_at_open else self.ref
                self.fill_bar, self.pending, self.remaining = i, False, self.qty
                self.gross, self.cost = 0.0, self._cost(self.qty, not self.is_limit)
                self.ratio = ((self.fill - self.init_stop) if s == 1 else (self.init_stop - self.fill)) / self.risk
                fill_now = True
                out.append(("FILL", self.qty, self.fill))
            elif i - self.sub_bar >= cfg.limit_bars:
                out.append(("CANCEL", 0, None))
                self.pending, self.side, self.last_closed = False, 0, i
        if self.side != 0 and not self.pending:
            s, tk = self.side, cfg.tick
            from_open = not (fill_now and not fill_at_open)
            emu = cfg.same_bar == "emulator"
            up_first = abs(b.h - b.o) < abs(b.o - b.l)
            fav_first = up_first if s == 1 else not up_first
            if from_open:
                reach = b.h if s == 1 else b.l
            elif emu:
                reach = b.c if fav_first else (b.h if s == 1 else b.l)
            else:
                reach = None
            stop_touched = b.l <= self.stop if s == 1 else b.h >= self.stop
            stop_at_open = from_open and (b.o <= self.stop if s == 1 else b.o >= self.stop)
            targets_first = emu and from_open and fav_first

            def reached(t):
                return reach is not None and (reach >= t if s == 1 else reach <= t)

            def tgt_fill(t):
                if reach is None:
                    return None
                if from_open and (b.o >= t if s == 1 else b.o <= t):
                    return b.o
                if (reach >= t + cfg.fill_ticks * tk) if s == 1 else (reach <= t - cfg.fill_ticks * tk):
                    return t
                return None

            live = [self.p[k] > 0 and not self.done[k] for k in range(3)]
            any_target = any(live[k] and reached(self.t[k]) for k in range(3))
            certain = from_open and (not stop_touched or targets_first)
            for k in range(3):
                if certain and (k < 2 or cfg.use3) and reached(self.t[k]):
                    self.touched[k] = True
            if self.closing and not fill_now:
                self.gross += self._cash(b.o, self.remaining)
                self.cost += self._cost(self.remaining, True)
                out.append(("EXIT_" + self.closing, self.remaining, b.o))
                self.remaining, exited = 0.0, True
            elif stop_at_open or (stop_touched and not targets_first):
                px = b.o if stop_at_open else self.stop
                if any_target and not stop_at_open:
                    self.ambiguous += 1
                self.gross += self._cash(px, self.remaining)
                self.cost += self._cost(self.remaining, True)
                out.append(("STOP", self.remaining, px))
                self.remaining, exited = 0.0, True
            else:
                for k in range(3):
                    px = tgt_fill(self.t[k]) if live[k] else None
                    if px is not None:
                        self.gross += self._cash(px, self.p[k])
                        self.cost += self._cost(self.p[k], False)
                        self.remaining -= self.p[k]
                        self.done[k] = True
                        out.append(("TP%d" % (k + 1), self.p[k], px))
                if self.remaining > cfg.qty_step * 1e-6 and stop_touched:
                    self.ambiguous += 1
                    self.gross += self._cash(self.stop, self.remaining)
                    self.cost += self._cost(self.remaining, True)
                    out.append(("STOP", self.remaining, self.stop))
                    self.remaining = 0.0
                if self.remaining <= cfg.qty_step * 1e-6:
                    self.remaining, exited = 0.0, True
            if not exited:
                self.trig = self.trig or self.done[0] or (self.p[0] <= 0 and self.touched[0])
                if cfg.be_on and self.trig:
                    self.stop = max(self.stop, floor_tick(self.fill, cfg.tick)) if s == 1 else min(self.stop, ceil_tick(self.fill, cfg.tick))
                if cfg.trail_atr > 0 and self.trig:
                    self.stop = max(self.stop, floor_tick(b.c - cfg.trail_atr * b.atr, cfg.tick)) if s == 1 else min(self.stop, ceil_tick(b.c + cfg.trail_atr * b.atr, cfg.tick))
                why = ("GAP_RISK" if fill_now and cfg.gap_max_risk > 0 and self.ratio > cfg.gap_max_risk
                       else "STRUCTURE" if cfg.exit_on_choch and (ev["break_dn"] if s == 1 else ev["break_up"])
                       else "BIAS" if cfg.exit_on_bias and b.bias == -s
                       else "MAX_HOLD" if i - self.fill_bar >= cfg.hold_bars else "")
                if why and not self.closing:
                    self.closing = why
                    out.append(("EXIT_REQUEST", why, None))
            if exited:
                net = self.gross - self.cost
                r = net / self.planned_cash
                self.results.append(dict(r=r, net=net, gross=self.gross, cost=self.cost, qty=self.qty))
                out.append(("CLOSED_R", round(r, 6), None))
                self.last_closed, self.side, self.closing = i, 0, ""
        rested = self.last_closed is None or i - self.last_closed > cfg.cooldown
        if sig.get("signal", 0) != 0 and self.side == 0 and rested:
            s = sig["signal"]
            self.side, self.is_limit, self.ref, self.fill = s, cfg.limit, sig["ref"], None
            self.stop = self.init_stop = sig["stop"]
            self.risk = sig["risk"]
            self.t = targets(s, sig["ref"], sig["risk"], cfg)
            self.qty = sig["qty"]
            self.p = list(parts(sig["qty"], cfg))
            self.done, self.touched = [False] * 3, [False] * 3
            self.remaining, self.trig, self.pending, self.closing = 0.0, False, True, ""
            self.ratio, self.gross, self.cost, self.sub_bar = None, 0.0, 0.0, i
            self.planned_cash = sig["qty"] * sig["risk"] * cfg.unit_usd
            out.append(("ENTER", s, sig["ref"]))
        self.events.extend((i,) + e for e in out)
        return out


def run(bars, cfg, signals=None):
    """Run engine + simulation. `signals` maps bar index -> (side, ref, stop, qty) to test the
    execution rules in isolation (engine output on those bars is replaced)."""
    eng, sim = Engine(cfg), Sim(cfg)
    rows = []
    for i, b in enumerate(bars):
        res = eng.step(i, bars)
        if signals is not None:
            if i in signals:
                s, ref, stop, q = signals[i]
                res = dict(signal=s, cand=s, ref=ref, stop=stop, risk=abs(ref - stop), qty=q, events=res["events"])
            else:
                res = dict(signal=0, cand=0, events=res["events"])
        ev = sim.step(i, b, res, res["events"])
        rows.append(dict(i=i, **res, sim=ev))
    return eng, sim, rows
