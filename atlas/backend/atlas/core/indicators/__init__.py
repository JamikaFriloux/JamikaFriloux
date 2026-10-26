"""Technical indicators.

Pure, deterministic functions over float series. Every function returns a list aligned with
its input, with ``None`` until enough data exists (no partially warmed-up values), so a
strategy can never act on an indicator that hasn't seen its full window.

Averages that Wilder defined (ATR, RSI) use Wilder's smoothing: seed with the simple mean of
the first ``n`` values, then ``prev + (x - prev) / n``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

Series = list[float | None]


def _check(n: int) -> None:
    if n < 1:
        raise ValueError("window must be >= 1")


def sma(values: Sequence[float], n: int) -> Series:
    _check(n)
    out: Series = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


def ema(values: Sequence[float], n: int) -> Series:
    """Exponential moving average, alpha = 2 / (n + 1), seeded with the SMA of the first n."""
    _check(n)
    out: Series = [None] * len(values)
    if len(values) < n:
        return out
    alpha = 2.0 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = prev + alpha * (values[i] - prev)
        out[i] = prev
    return out


def _wilder(values: Sequence[float], n: int, offset: int = 0) -> Series:
    """Wilder smoothing of ``values``; output index i corresponds to input index i + offset."""
    out: Series = [None] * (len(values) + offset)
    if len(values) < n:
        return out
    prev = sum(values[:n]) / n
    out[n - 1 + offset] = prev
    for i in range(n, len(values)):
        prev = prev + (values[i] - prev) / n
        out[i + offset] = prev
    return out


def true_range(high: Sequence[float], low: Sequence[float], close: Sequence[float]) -> Series:
    out: Series = [None] * len(close)
    for i in range(1, len(close)):
        pc = close[i - 1]
        out[i] = max(high[i] - low[i], abs(high[i] - pc), abs(low[i] - pc))
    return out


def atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], n: int = 14) -> Series:
    """Average true range (Wilder). First value at index n (needs n true ranges)."""
    _check(n)
    if not len(high) == len(low) == len(close):
        raise ValueError("high/low/close lengths differ")
    tr = [t for t in true_range(high, low, close)[1:] if t is not None]
    return _wilder(tr, n, offset=1)


def rsi(close: Sequence[float], n: int = 14) -> Series:
    """Relative strength index (Wilder), 0-100. First value at index n."""
    _check(n)
    gains, losses = [], []
    for i in range(1, len(close)):
        d = close[i] - close[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = _wilder(gains, n, offset=1)
    avg_loss = _wilder(losses, n, offset=1)
    out: Series = [None] * len(close)
    for i, (g, ls) in enumerate(zip(avg_gain, avg_loss, strict=True)):
        if g is None or ls is None:
            continue
        if ls == 0:
            out[i] = 100.0 if g > 0 else 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + g / ls)
    return out


def _rolling_extreme(
    values: Sequence[float], n: int, exclude_current: bool, is_max: bool
) -> Series:
    """O(len) sliding-window extreme with a monotonic deque of indices."""
    _check(n)
    out: Series = [None] * len(values)
    window: deque[int] = deque()
    shift = 1 if exclude_current else 0
    size = len(values)
    for j, v in enumerate(values):
        # Output index i = j + shift covers values[i - shift - n + 1 .. i - shift].
        if is_max:
            while window and values[window[-1]] <= v:
                window.pop()
        else:
            while window and values[window[-1]] >= v:
                window.pop()
        window.append(j)
        if window[0] <= j - n:
            window.popleft()
        i = j + shift
        if j >= n - 1 and i < size:
            out[i] = values[window[0]]
    return out


def rolling_max(values: Sequence[float], n: int, *, exclude_current: bool = False) -> Series:
    """Highest value of the last n (or, with ``exclude_current``, the n before this one)."""
    return _rolling_extreme(values, n, exclude_current, True)


def rolling_min(values: Sequence[float], n: int, *, exclude_current: bool = False) -> Series:
    return _rolling_extreme(values, n, exclude_current, False)
