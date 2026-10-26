import pytest

from atlas.core.indicators import atr, ema, rolling_max, rolling_min, rsi, sma, true_range


def approx(series):
    return [None if v is None else pytest.approx(v) for v in series]


def test_sma():
    assert sma([1, 2, 3, 4, 5], 3) == approx([None, None, 2.0, 3.0, 4.0])
    assert sma([1, 2], 3) == [None, None]


def test_ema_seeded_with_sma():
    # alpha = 0.5; seed = mean(1,2,3) = 2; then 2 + 0.5*(4-2) = 3; 3 + 0.5*(8-3) = 5.5
    assert ema([1, 2, 3, 4, 8], 3) == approx([None, None, 2.0, 3.0, 5.5])


def test_true_range_and_wilder_atr():
    high, low, close = [10, 11, 12, 11], [9, 10, 10, 9], [9.5, 10.5, 11, 10]
    assert true_range(high, low, close) == approx([None, 1.5, 2.0, 2.0])
    # seed = (1.5 + 2) / 2 = 1.75; next = 1.75 + (2 - 1.75) / 2 = 1.875
    assert atr(high, low, close, 2) == approx([None, None, 1.75, 1.875])
    with pytest.raises(ValueError):
        atr([1], [1, 2], [1], 2)


def test_wilder_rsi():
    # gains [1,1,0,1], losses [0,0,1,0]; avg gain 1 -> 0.5 -> 0.75; avg loss 0 -> 0.5 -> 0.25
    assert rsi([1, 2, 3, 2, 3], 2) == approx([None, None, 100.0, 50.0, 75.0])
    assert rsi([5, 5, 5], 2) == approx([None, None, 50.0])  # flat: neither gains nor losses
    assert all(0 <= v <= 100 for v in rsi([3, 1, 4, 1, 5, 9, 2, 6], 3) if v is not None)


def test_rolling_extremes():
    v = [3, 1, 4, 1, 5]
    assert rolling_max(v, 2) == [None, 3, 4, 4, 5]
    assert rolling_min(v, 2) == [None, 1, 1, 1, 1]
    # Prior-window highs (breakout levels must not include today's bar).
    assert rolling_max(v, 2, exclude_current=True) == [None, None, 3, 4, 4]


def test_invalid_window():
    with pytest.raises(ValueError):
        sma([1], 0)


def test_rolling_extremes_match_brute_force():
    import random

    rng = random.Random(7)
    v = [rng.uniform(0, 100) for _ in range(300)]
    v[50:60] = [42.0] * 10  # ties
    for n in (1, 2, 5, 55):
        for excl in (False, True):
            shift = 1 if excl else 0
            want_max = [
                max(v[i - shift - n + 1 : i - shift + 1]) if i - shift - n + 1 >= 0 else None
                for i in range(len(v))
            ]
            want_min = [
                min(v[i - shift - n + 1 : i - shift + 1]) if i - shift - n + 1 >= 0 else None
                for i in range(len(v))
            ]
            assert rolling_max(v, n, exclude_current=excl) == want_max
            assert rolling_min(v, n, exclude_current=excl) == want_min
