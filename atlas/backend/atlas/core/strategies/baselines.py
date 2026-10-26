"""Two baseline daily-bar strategies, long-only.

These are well-known textbook rules, included as *hypotheses to test* and as references for
the pipeline. They start in RESEARCH and cannot place paper orders until they pass the
Phase 4 validation gates.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field

from atlas.core.data.bars import BarRecord
from atlas.core.indicators import atr, rolling_max, rolling_min, rsi, sma
from atlas.core.strategies.base import (
    OpenPosition,
    Signal,
    Strategy,
    StrategyParams,
    closes,
    highs,
    lows,
)


class TrendBreakoutParams(StrategyParams):
    breakout_n: int = Field(default=55, ge=10, le=250)
    exit_n: int = Field(default=20, ge=5, le=250)
    trend_n: int = Field(default=200, ge=20, le=400)
    atr_n: int = Field(default=20, ge=5, le=100)
    stop_atr: float = Field(default=2.0, gt=0, le=10)


class TrendBreakout(Strategy):
    """Donchian breakout in an uptrend.

    Entry: close above the highest high of the prior ``breakout_n`` sessions, and above its
    ``trend_n``-day SMA. Stop: entry close - ``stop_atr`` x ATR(``atr_n``).
    Exit: close below the lowest low of the prior ``exit_n`` sessions (the stop protects
    in between).
    """

    id = "trend_breakout"
    version = "1.0.0"
    description = "55-day breakout above the 200-day SMA, 2xATR stop, 20-day low exit"

    def __init__(self, params: TrendBreakoutParams | None = None):
        self.params: TrendBreakoutParams = params or TrendBreakoutParams()

    @property
    def lookback(self) -> int:
        p = self.params
        return max(p.trend_n, p.breakout_n + 1, p.exit_n + 1, p.atr_n + 1) + 1

    def decide(
        self, symbol: str, bars: Sequence[BarRecord], position: OpenPosition | None
    ) -> Signal | None:
        p = self.params
        c, h, lo = closes(bars), highs(bars), lows(bars)
        close = c[-1]
        if position is not None:
            # Only the last value is used, so compute over just the tail (identical result).
            exit_level = rolling_min(lo[-(p.exit_n + 1) :], p.exit_n, exclude_current=True)[-1]
            if exit_level is not None and close < exit_level:
                return self.signal(symbol, "exit", bars, close=close, exit_level=exit_level)
            return None
        breakout = rolling_max(h[-(p.breakout_n + 1) :], p.breakout_n, exclude_current=True)[-1]
        trend = sma(c[-p.trend_n :], p.trend_n)[-1]
        a = atr(h, lo, c, p.atr_n)[-1]
        if breakout is None or trend is None or a is None:
            return None
        if close > breakout and close > trend:
            return self.signal(
                symbol,
                "entry",
                bars,
                stop=close - p.stop_atr * a,
                close=close,
                breakout_level=breakout,
                sma_trend=trend,
                atr=a,
            )
        return None


class RsiPullbackParams(StrategyParams):
    rsi_n: int = Field(default=2, ge=2, le=14)
    entry_below: float = Field(default=10.0, gt=0, lt=50)
    trend_n: int = Field(default=200, ge=20, le=400)
    exit_sma_n: int = Field(default=5, ge=2, le=50)
    atr_n: int = Field(default=20, ge=5, le=100)
    stop_atr: float = Field(default=2.5, gt=0, le=10)
    max_hold_sessions: int = Field(default=10, ge=1, le=60)


class RsiPullback(Strategy):
    """Short-term pullback in an uptrend (RSI(2) mean reversion).

    Entry: close above its ``trend_n``-day SMA and RSI(``rsi_n``) below ``entry_below``.
    Stop: entry close - ``stop_atr`` x ATR. Exit: close above the ``exit_sma_n``-day SMA, or
    after ``max_hold_sessions``.
    """

    id = "rsi_pullback"
    version = "1.0.0"
    description = "RSI(2) < 10 above the 200-day SMA, exit above the 5-day SMA or after 10 sessions"

    def __init__(self, params: RsiPullbackParams | None = None):
        self.params: RsiPullbackParams = params or RsiPullbackParams()

    @property
    def lookback(self) -> int:
        p = self.params
        return max(p.trend_n, p.rsi_n + 1, p.exit_sma_n, p.atr_n + 1) + 1

    def decide(
        self, symbol: str, bars: Sequence[BarRecord], position: OpenPosition | None
    ) -> Signal | None:
        p = self.params
        c, h, lo = closes(bars), highs(bars), lows(bars)
        close = c[-1]
        if position is not None:
            exit_sma = sma(c, p.exit_sma_n)[-1]
            if exit_sma is not None and close > exit_sma:
                return self.signal(
                    symbol, "exit", bars, close=close, exit_sma=exit_sma, rule="above_exit_sma"
                )
            if position.sessions_held >= p.max_hold_sessions:
                return self.signal(
                    symbol,
                    "exit",
                    bars,
                    close=close,
                    sessions_held=position.sessions_held,
                    rule="max_hold",
                )
            return None
        r = rsi(c, p.rsi_n)[-1]
        trend = sma(c, p.trend_n)[-1]
        a = atr(h, lo, c, p.atr_n)[-1]
        if r is None or trend is None or a is None:
            return None
        if close > trend and r < p.entry_below:
            return self.signal(
                symbol,
                "entry",
                bars,
                stop=close - p.stop_atr * a,
                close=close,
                rsi=r,
                sma_trend=trend,
                atr=a,
            )
        return None
