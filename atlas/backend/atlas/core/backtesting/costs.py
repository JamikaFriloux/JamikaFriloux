"""Trading cost model for validation backtests (values from ``policy.yaml`` ``backtest``)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from atlas.core.configuration.policy import RiskPolicy

BPS = Decimal(10_000)
CENT = Decimal("0.01")


@dataclass(frozen=True)
class CostModel:
    half_spread: Decimal  # fraction of price
    slippage: Decimal
    stop_slippage: Decimal  # extra slippage when a stop triggers (policy execution section)
    limit_offset: Decimal  # how far through the quote limit orders are priced
    sec_fee_per_dollar: Decimal
    taf_per_share: Decimal
    taf_max: Decimal
    max_participation: Decimal  # fraction of session volume

    @classmethod
    def from_policy(cls, policy: RiskPolicy) -> CostModel:
        b, e = policy.backtest, policy.execution
        d = lambda v: Decimal(str(v))  # noqa: E731
        return cls(
            half_spread=d(b.half_spread_bps) / BPS,
            slippage=d(b.slippage_bps) / BPS,
            stop_slippage=d(e.stop_slippage_assumption_bps) / BPS,
            limit_offset=d(e.limit_offset_bps) / BPS,
            sec_fee_per_dollar=d(b.sec_fee_per_million_usd) / Decimal(1_000_000),
            taf_per_share=d(b.finra_taf_per_share),
            taf_max=d(b.finra_taf_max_per_trade_usd),
            max_participation=d(b.max_participation_pct) / 100,
        )

    def quote(self, mid: Decimal) -> tuple[Decimal, Decimal]:
        """Synthetic (bid, ask) around a reference price."""
        return mid * (1 - self.half_spread), mid * (1 + self.half_spread)

    def sell_fees(self, qty: Decimal, price: Decimal) -> Decimal:
        sec = qty * price * self.sec_fee_per_dollar
        taf = min(qty * self.taf_per_share, self.taf_max)
        return (sec + taf).quantize(CENT, rounding=ROUND_HALF_UP)

    def participation_cap(self, session_volume: Decimal) -> Decimal:
        return (session_volume * self.max_participation).to_integral_value(rounding="ROUND_FLOOR")
