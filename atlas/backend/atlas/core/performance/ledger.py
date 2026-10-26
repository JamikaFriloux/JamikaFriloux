"""Paper trade ledger: round trips rebuilt from the strategy's own filled orders.

Per (strategy, symbol), filled buys open lots and filled sells (exits and protective stops)
close them first-in first-out. Each closed slice is a ``Trade`` with the same fields the
backtester produces, so paper and backtest statistics are computed by the same code.

  * fill time is the order's last fill event (else its last update);
  * an order's fills are taken at its average fill price on that date (a simplification for
    orders filled in pieces across days, which DAY orders here cannot be);
  * risk per share is entry price minus the stop the signal set, or the protective stop
    order's price when the signal has none;
  * fees are zero: Alpaca paper charges none. Backtests charge modeled costs, so compare
    with that in mind;
  * a sell with no open lot to close (e.g. a position not opened by ATLAS) is not a trade;
    its quantity is reported as unmatched.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.core.backtesting.metrics import Trade
from atlas.core.data.calendar import NY
from atlas.core.models.db import Order, OrderEvent, OrderState, SignalRecord

FILL_STATES = (OrderState.FILLED.value, OrderState.PARTIALLY_FILLED.value)
EXIT_REASON = {"exit": "signal", "protective_stop": "stop"}


@dataclass
class Lot:
    strategy_id: str
    version: str
    symbol: str
    qty: Decimal
    price: Decimal
    entry_date: date
    risk_per_share: Decimal


@dataclass(frozen=True)
class PaperTrade:
    strategy_id: str
    version: str
    trade: Trade


@dataclass
class Ledger:
    trades: list[PaperTrade] = field(default_factory=list)
    open_lots: list[Lot] = field(default_factory=list)
    unmatched_sell_qty: dict[str, Decimal] = field(default_factory=dict)  # "strategy/symbol"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def build_ledger(session: Session, strategy_id: str | None = None) -> Ledger:
    q = select(Order).where(Order.strategy_id.is_not(None), Order.filled_qty > 0)
    if strategy_id is not None:
        q = q.where(Order.strategy_id == strategy_id)
    orders = session.scalars(q).all()
    if not orders:
        return Ledger()
    ids = [o.id for o in orders]
    fill_ts = dict(
        session.execute(
            select(OrderEvent.order_id, func.max(OrderEvent.ts))
            .where(OrderEvent.order_id.in_(ids), OrderEvent.to_state.in_(FILL_STATES))
            .group_by(OrderEvent.order_id)
        ).all()
    )
    signal_ids = {o.signal_id for o in orders if o.signal_id}
    signal_stop = dict(
        session.execute(
            select(SignalRecord.id, SignalRecord.stop_price).where(SignalRecord.id.in_(signal_ids))
        ).all()
    )
    stop_by_parent = {
        o.parent_order_id: o.stop_price
        for o in session.scalars(
            select(Order).where(Order.parent_order_id.in_(ids), Order.purpose == "protective_stop")
        ).all()
    }

    def when(o: Order) -> datetime:
        return _aware(fill_ts.get(o.id) or o.updated_at or o.created_at)

    ledger = Ledger()
    lots: dict[tuple[str, str], deque[Lot]] = defaultdict(deque)
    for o in sorted(orders, key=lambda o: (when(o), o.side != "buy")):
        key = (o.strategy_id or "", o.symbol)
        day = when(o).astimezone(NY).date()
        price = o.filled_avg_price
        if price is None:
            continue  # a fill without a price can't be valued; never guess one
        if o.side == "buy":
            stop = signal_stop.get(o.signal_id) if o.signal_id else None
            stop = stop if stop is not None else stop_by_parent.get(o.id)
            risk = price - stop if stop is not None else Decimal(0)
            lots[key].append(
                Lot(key[0], o.strategy_version or "", o.symbol, o.filled_qty, price, day, risk)
            )
            continue
        remaining = o.filled_qty
        reason = EXIT_REASON.get(o.purpose or "", o.purpose or "sell")
        while remaining > 0 and lots[key]:
            lot = lots[key][0]
            qty = min(lot.qty, remaining)
            trade = Trade(
                o.symbol,
                lot.entry_date,
                day,
                qty,
                lot.price,
                price,
                Decimal(0),
                reason,
                lot.risk_per_share,
            )
            ledger.trades.append(PaperTrade(lot.strategy_id, lot.version, trade))
            lot.qty -= qty
            remaining -= qty
            if lot.qty == 0:
                lots[key].popleft()
        if remaining > 0:
            name = f"{key[0]}/{key[1]}"
            ledger.unmatched_sell_qty[name] = (
                ledger.unmatched_sell_qty.get(name, Decimal(0)) + remaining
            )
    ledger.open_lots = [lot for q in lots.values() for lot in q]
    return ledger
