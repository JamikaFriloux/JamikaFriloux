"""Broker-agnostic gateway interface and idempotent submission logic.

Only the execution service constructs a concrete gateway. Everything else depends on this
protocol, which lets tests inject failure scenarios (timeouts, duplicates, rejections).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from atlas.core.observability.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class AccountInfo:
    account_number: str
    status: str
    equity: Decimal
    last_equity: Decimal
    cash: Decimal
    buying_power: Decimal
    long_market_value: Decimal
    trading_blocked: bool
    is_paper: bool


@dataclass(frozen=True)
class PositionInfo:
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    current_price: Decimal | None


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: Decimal
    limit_price: Decimal
    time_in_force: Literal["day"] = "day"


@dataclass(frozen=True)
class BrokerOrder:
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    status: str
    qty: Decimal
    filled_qty: Decimal
    filled_avg_price: Decimal | None


class BrokerError(RuntimeError):
    """Base class for broker failures."""


class BrokerRejected(BrokerError):
    """The broker definitively refused the request (validation, buying power, ...)."""


class BrokerUncertain(BrokerError):
    """The outcome is unknown (timeout, connection reset, 5xx)."""


class DuplicateClientOrderId(BrokerError):
    """The broker already has an order with this client_order_id."""


class SubmissionUncertain(BrokerError):
    """Submission outcome could not be determined; reconciliation must resolve it."""


class BrokerGateway(Protocol):
    def get_account(self) -> AccountInfo: ...
    def list_positions(self) -> list[PositionInfo]: ...
    def list_open_orders(self) -> list[BrokerOrder]: ...
    def get_order_by_client_id(self, client_order_id: str) -> BrokerOrder | None: ...
    def submit_limit_order(self, request: OrderRequest) -> BrokerOrder: ...
    def cancel_all_open_orders(self) -> list[str]: ...


def _lookup_with_backoff(
    gateway: BrokerGateway, client_order_id: str, attempts: int, base_delay: float
) -> tuple[BrokerOrder | None, bool]:
    """Return (order, lookup_succeeded). lookup_succeeded=False means we still don't know."""
    for attempt in range(attempts):
        try:
            return gateway.get_order_by_client_id(client_order_id), True
        except BrokerUncertain:
            time.sleep(base_delay * (2**attempt))
    return None, False


def submit_idempotent(
    gateway: BrokerGateway,
    request: OrderRequest,
    *,
    lookup_attempts: int = 4,
    base_delay: float = 0.5,
) -> BrokerOrder:
    """Submit an order at most once.

    1. If the broker already knows this client_order_id, return that order.
    2. Submit.
    3. On an uncertain outcome, query the broker by client_order_id (with backoff).
       Found -> return it. Confirmed absent -> retry once with the SAME client_order_id
       (the broker deduplicates on it). Still uncertain -> raise SubmissionUncertain; the
       caller must leave the order in SUBMITTED for reconciliation and never resubmit blindly.
    """
    existing, _ = _lookup_with_backoff(gateway, request.client_order_id, 1, base_delay)
    if existing is not None:
        log.info("order_already_at_broker", client_order_id=request.client_order_id)
        return existing

    for attempt in range(2):
        try:
            return gateway.submit_limit_order(request)
        except DuplicateClientOrderId:
            found, _ = _lookup_with_backoff(
                gateway, request.client_order_id, lookup_attempts, base_delay
            )
            if found is not None:
                return found
            raise SubmissionUncertain(
                f"broker reports duplicate {request.client_order_id} but lookup failed"
            ) from None
        except BrokerUncertain:
            log.warning(
                "order_submission_uncertain",
                client_order_id=request.client_order_id,
                attempt=attempt,
            )
            found, known = _lookup_with_backoff(
                gateway, request.client_order_id, lookup_attempts, base_delay
            )
            if found is not None:
                return found
            if not known or attempt == 1:
                raise SubmissionUncertain(
                    f"could not determine outcome for {request.client_order_id}"
                ) from None
            # Confirmed absent: one retry with the same client_order_id.
    raise SubmissionUncertain(request.client_order_id)  # pragma: no cover
