"""Approximate GICS sector from a US SIC code (SEC EDGAR filings).

SIC predates GICS and doesn't map one to one; this table follows the usual conventions and
is good enough for a concentration limit, not for research. Known mismatches: internet
platforms filed under SIC 7370 (e.g. Alphabet, Meta) land in Information Technology rather
than Communication Services. Put such stocks in config/instruments.yaml, which takes
precedence. Codes outside every range (e.g. 9995 shell companies) return None: unknown.
"""

from __future__ import annotations

# (first, last, sector), checked in order: the narrower ranges come first.
_RANGES: tuple[tuple[int, int, str], ...] = (
    (2830, 2836, "Health Care"),
    (2840, 2844, "Consumer Staples"),
    (3570, 3579, "Information Technology"),
    (3630, 3639, "Consumer Discretionary"),
    (3650, 3652, "Consumer Discretionary"),
    (3660, 3699, "Information Technology"),
    (3710, 3716, "Consumer Discretionary"),
    (3840, 3851, "Health Care"),
    (5120, 5129, "Health Care"),
    (5400, 5499, "Consumer Staples"),
    (5910, 5912, "Consumer Staples"),
    (6798, 6798, "Real Estate"),
    (7370, 7379, "Information Technology"),
    (100, 999, "Consumer Staples"),
    (1000, 1099, "Materials"),
    (1200, 1399, "Energy"),
    (1400, 1499, "Materials"),
    (1500, 1799, "Industrials"),
    (2000, 2199, "Consumer Staples"),
    (2200, 2399, "Consumer Discretionary"),
    (2400, 2499, "Materials"),
    (2500, 2599, "Consumer Discretionary"),
    (2600, 2699, "Materials"),
    (2700, 2799, "Communication Services"),
    (2800, 2899, "Materials"),
    (2900, 2999, "Energy"),
    (3100, 3199, "Consumer Discretionary"),
    (3000, 3399, "Materials"),
    (3400, 3599, "Industrials"),
    (3600, 3629, "Industrials"),
    (3640, 3649, "Industrials"),
    (3700, 3799, "Industrials"),
    (3800, 3899, "Information Technology"),
    (3900, 3999, "Consumer Discretionary"),
    (4000, 4799, "Industrials"),
    (4800, 4899, "Communication Services"),
    (4900, 4999, "Utilities"),
    (5000, 5199, "Industrials"),
    (5200, 5999, "Consumer Discretionary"),
    (6000, 6499, "Financials"),
    (6500, 6599, "Real Estate"),
    (6700, 6799, "Financials"),
    (7000, 7299, "Consumer Discretionary"),
    (7300, 7399, "Industrials"),
    (7800, 7899, "Communication Services"),
    (7900, 7999, "Consumer Discretionary"),
    (8000, 8099, "Health Care"),
    (8700, 8799, "Industrials"),
)


def sector_for_sic(sic: int | None) -> str | None:
    if sic is None:
        return None
    for lo, hi, sector in _RANGES:
        if lo <= sic <= hi:
            return sector
    return None
