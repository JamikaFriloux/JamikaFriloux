"""Per-strategy positions, derived from the strategy's own filled orders.

The broker reports one position per symbol; attribution to a strategy comes from our orders:
filled entry buys minus filled sells (exits and protective stops). Callers that act on a
position also cap it at what the broker actually holds.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.models.db import Order
from atlas.core.strategies.base import OpenPosition


@dataclass(frozen=True)
class StrategyHolding:
    strategy_id: str
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    entry_date: date


def strategy_holdings(session: Session, strategy_id: str | None = None) -> list[StrategyHolding]:
    q = select(Order).where(Order.strategy_id.is_not(None), Order.filled_qty > 0)
    if strategy_id is not None:
        q = q.where(Order.strategy_id == strategy_id)
    bought: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    cost: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    sold: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    first: dict[tuple[str, str], date] = {}
    for o in session.scalars(q.order_by(Order.created_at)).all():
        key = (o.strategy_id or "", o.symbol)
        if o.side == "buy":
            bought[key] += o.filled_qty
            cost[key] += o.filled_qty * (o.filled_avg_price or Decimal(0))
            ts = o.submitted_at or o.created_at
            ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts
            first.setdefault(key, ts.astimezone(NY).date())
        else:
            sold[key] += o.filled_qty
    out = []
    for key, qty in bought.items():
        net = qty - sold.get(key, Decimal(0))
        if net > 0:
            out.append(StrategyHolding(key[0], key[1], net, cost[key] / qty, first[key]))
    return out


def open_positions_for(
    session: Session, strategy_id: str, as_of: date, calendar: MarketCalendar
) -> dict[str, OpenPosition]:
    """Positions in the shape strategies consume, with sessions held up to ``as_of``."""
    out = {}
    for h in strategy_holdings(session, strategy_id):
        held = max(len(calendar.sessions_between(h.entry_date, as_of)) - 1, 0)
        out[h.symbol] = OpenPosition(h.qty, h.avg_entry_price, h.entry_date, held)
    return out
