"""Strategy interface.

A strategy is deterministic: given daily bars up to and including the close of ``as_of`` and
its own open position (if any), it returns at most one signal per symbol. It never sees data
after ``as_of``, never sizes positions and never talks to the broker; sizing and approval
belong to the risk engine, which has final authority. The same code runs in the signal
engine (paper) and, in Phase 4, the backtester.

Every strategy is a hypothesis under test. Nothing here implies it is profitable.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from atlas.core.data.bars import BarRecord, validate_bars
from atlas.core.data.calendar import NY

CENT = Decimal("0.01")


def to_cents(v: float | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Signal:
    strategy_id: str
    strategy_version: str
    symbol: str
    kind: Literal["entry", "exit"]
    as_of: date
    ref_price: Decimal  # the close that produced the signal
    stop_price: Decimal | None = None  # required for entries (defines risk per share)
    reason: Mapping[str, Any] = field(default_factory=dict)

    @property
    def side(self) -> Literal["buy", "sell"]:
        return "buy" if self.kind == "entry" else "sell"  # long-only

    @property
    def id(self) -> str:
        key = f"{self.strategy_id}|{self.strategy_version}|{self.symbol}|{self.kind}|{self.as_of}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class OpenPosition:
    """What the strategy holds in a symbol (from its own filled orders)."""

    qty: Decimal
    avg_entry_price: Decimal
    entry_date: date  # session of the entry fill
    sessions_held: int


class StrategyParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Strategy(ABC):
    id: ClassVar[str]
    version: ClassVar[str]
    description: ClassVar[str]
    params: StrategyParams

    @property
    @abstractmethod
    def lookback(self) -> int:
        """Bars needed before the first decision."""

    @abstractmethod
    def decide(
        self, symbol: str, bars: Sequence[BarRecord], position: OpenPosition | None
    ) -> Signal | None:
        """One decision for ``symbol``; ``bars`` end at the decision session's close."""

    def generate(
        self,
        as_of: date,
        bars: Mapping[str, Sequence[BarRecord]],
        positions: Mapping[str, OpenPosition],
        *,
        trusted: bool = False,
    ) -> tuple[list[Signal], dict[str, str]]:
        """Run ``decide`` for every symbol with usable data.

        Returns (signals, skipped) where ``skipped`` maps symbol -> reason. A symbol is skipped,
        never guessed, when its data is short, stale or fails validation.

        ``trusted`` is for callers (the backtester) that validated each full series up front
        and pass windows ending at ``as_of``; it skips re-filtering and re-validating them.
        """
        signals: list[Signal] = []
        skipped: dict[str, str] = {}
        for symbol in sorted(bars):
            if trusted:
                series = list(bars[symbol])
            else:
                series = [b for b in bars[symbol] if b.ts.astimezone(NY).date() <= as_of]
            if len(series) < self.lookback:
                skipped[symbol] = "insufficient_history"
                continue
            if series[-1].ts.astimezone(NY).date() != as_of:
                skipped[symbol] = "no_bar_for_session"
                continue
            window = series[-self.lookback :]
            if not trusted:
                report = validate_bars(window, now=window[-1].ts)
                if not report.ok:
                    skipped[symbol] = "bad_data:" + report.issues[0].code
                    continue
            sig = self.decide(symbol, window, positions.get(symbol))
            if sig is not None:
                if sig.kind == "entry" and (
                    sig.stop_price is None or sig.stop_price >= sig.ref_price
                ):
                    raise ValueError(f"{self.id}: entry for {symbol} without a valid stop")
                signals.append(sig)
        return signals, skipped

    def signal(
        self,
        symbol: str,
        kind: Literal["entry", "exit"],
        bars: Sequence[BarRecord],
        stop: float | None = None,
        **reason: Any,
    ) -> Signal:
        last = bars[-1]
        return Signal(
            strategy_id=self.id,
            strategy_version=self.version,
            symbol=symbol,
            kind=kind,
            as_of=last.ts.astimezone(NY).date(),
            ref_price=last.close,
            stop_price=to_cents(stop) if stop is not None else None,
            reason={k: (round(v, 6) if isinstance(v, float) else v) for k, v in reason.items()},
        )


def closes(bars: Sequence[BarRecord]) -> list[float]:
    return [float(b.close) for b in bars]


def highs(bars: Sequence[BarRecord]) -> list[float]:
    return [float(b.high) for b in bars]


def lows(bars: Sequence[BarRecord]) -> list[float]:
    return [float(b.low) for b in bars]
