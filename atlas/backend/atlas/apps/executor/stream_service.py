"""Live market-data service: Alpaca stream -> Redis (latest quotes/trades) and ``bars``.

Runs inside the executor container, the only one with broker credentials (started by
``atlas.apps.executor.run`` next to the Celery worker, or alone with
``python -m atlas.apps.executor.stream_service``).

Loops:
  * flush      - writes changed quotes/trades to Redis every 0.5 s (coalesced, so a burst of
                 quotes costs one write per symbol).
  * bars       - stores completed regular-hours minute bars every 2 s. Bars lost to an outage
                 are backfilled by the REST minute ingestion, which tracks its own coverage.
  * symbols    - re-reads benchmarks + watchlists every 60 s and adjusts subscriptions.
  * heartbeat  - writes the ``stream`` service heartbeat and Redis status every 15 s, and
                 alerts when the stream is down during market hours or fails fatally.

A failure in any loop is logged and retried on the next tick; it never stops the stream.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from atlas.apps.worker.heartbeat import beat
from atlas.core.configuration.policy import get_policy
from atlas.core.configuration.settings import AtlasSettings, BrokerSettings, get_settings
from atlas.core.data.bars import BarRecord, validate_bars
from atlas.core.data.calendar import MarketCalendar
from atlas.core.data.ingestion import ingestion_symbols, upsert_bars
from atlas.core.data.live import LiveCache, LiveStore, Quote, Trade
from atlas.core.models.session import get_sessionmaker, session_scope
from atlas.core.observability.logging import configure_logging, get_logger
from atlas.integrations.alpaca.stream import AlpacaStream, StreamState, StreamStats
from atlas.integrations.telegram.notifier import Event, build_notifier

log = get_logger(__name__)

StreamFactory = Callable[..., AlpacaStream]


class LiveDataService:
    def __init__(
        self,
        stream_factory: StreamFactory,
        store: LiveStore,
        session_factory: sessionmaker[Session],
        *,
        default_symbols: list[str],
        max_symbols: int,
        max_quote_age_seconds: float,
        calendar: MarketCalendar | None = None,
        notifier_factory: Callable[[], Any] = build_notifier,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        flush_interval: float = 0.5,
        bar_flush_interval: float = 2.0,
        symbols_interval: float = 60.0,
        heartbeat_interval: float = 15.0,
        disconnect_alert_after: timedelta = timedelta(seconds=60),
    ) -> None:
        self.calendar = calendar or MarketCalendar()
        self.store = store
        self.session_factory = session_factory
        self.default_symbols = [s.upper() for s in default_symbols]
        self.max_symbols = max_symbols
        self.max_quote_age = max_quote_age_seconds
        self.notifier_factory = notifier_factory
        self.clock = clock
        self.intervals = {
            "flush": flush_interval,
            "bars": bar_flush_interval,
            "symbols": symbols_interval,
            "heartbeat": heartbeat_interval,
        }
        self.disconnect_alert_after = disconnect_alert_after
        self.cache = LiveCache()
        self.symbols: list[str] = []
        self.dropped_symbols: list[str] = []
        self.bars_written = 0
        self.bars_rejected = 0
        self._pending_bars: list[BarRecord] = []
        self._down_since: datetime | None = self.clock()
        self._down_alerted = False
        self._fatal_alerted = False
        self._stopped = asyncio.Event()
        self.stream = stream_factory(
            on_quote=self._on_quote,
            on_trade=self._on_trade,
            on_bar=self._on_bar,
            on_state=self._on_state,
            is_market_open=self.calendar.is_open,
        )

    # ----- stream callbacks (run on the event loop; must stay cheap) ----------------------

    def _on_quote(self, quote: Quote) -> None:
        self.cache.apply_quote(quote, self.clock())

    def _on_trade(self, trade: Trade) -> None:
        self.cache.apply_trade(trade, self.clock())

    def _on_bar(self, bar: BarRecord) -> None:
        if not self.calendar.is_open(bar.ts):
            return  # extended hours: policy is regular hours only
        report = validate_bars([bar], now=self.clock())
        if not report.ok:
            self.bars_rejected += 1
            log.warning("stream_bar_rejected", symbol=bar.symbol, issues=report.issues[0].code)
            return
        self._pending_bars.append(bar)

    def _on_state(self, state: StreamState, _stats: StreamStats) -> None:
        if state == StreamState.SUBSCRIBED:
            self._down_since = None
        elif self._down_since is None:
            self._down_since = self.clock()

    # ----- periodic work ------------------------------------------------------------------

    async def refresh_symbols(self) -> None:
        def load() -> list[str]:
            with session_scope(self.session_factory) as s:
                return ingestion_symbols(s, self.default_symbols)

        found = await asyncio.to_thread(load)
        # Benchmarks first so a full watchlist can never crowd them out.
        ordered = [s for s in self.default_symbols if s in found]
        ordered += [s for s in found if s not in ordered]
        self.symbols, self.dropped_symbols = (
            ordered[: self.max_symbols],
            ordered[self.max_symbols :],
        )
        if self.dropped_symbols:
            log.warning("stream_symbols_truncated", dropped=self.dropped_symbols[:20])
        await self.stream.set_symbols(self.symbols)

    async def flush(self) -> None:
        dirty = self.cache.drain_dirty()
        if not dirty:
            return
        try:
            await asyncio.to_thread(self.store.write, dirty)
        except Exception:
            self.cache.mark_dirty(s.symbol for s in dirty)
            raise

    async def flush_bars(self) -> None:
        bars, self._pending_bars = self._pending_bars, []
        if not bars:
            return

        def write() -> int:
            with session_scope(self.session_factory) as s:
                return upsert_bars(s, bars)

        self.bars_written += await asyncio.to_thread(write)

    async def heartbeat(self) -> None:
        now = self.clock()
        stats = self.stream.stats
        market_open = self.calendar.is_open(now)
        stale = (
            self.cache.stale_symbols(self.symbols, now, self.max_quote_age) if market_open else []
        )
        if stats.state != StreamState.SUBSCRIBED:
            status = "error"
        elif stale:
            status = "degraded"
        else:
            status = "ok"
        details = {
            **stats.as_dict(),
            "market_open": market_open,
            "symbols": len(self.symbols),
            "dropped_symbols": self.dropped_symbols[:20],
            "stale": stale[:20],
            "bars_written": self.bars_written,
            "bars_rejected": self.bars_rejected,
        }

        def write() -> None:
            with session_scope(self.session_factory) as s:
                beat(s, "stream", status, **details)

        await asyncio.to_thread(write)
        await asyncio.to_thread(
            self.store.write_status,
            {
                "status": status,
                "state": stats.state.value,
                "updated_at": now.isoformat(),
                "market_open": str(market_open).lower(),
                "last_data_at": stats.last_data_at.isoformat() if stats.last_data_at else "",
            },
        )
        self._alert(now, stats, market_open)

    def _alert(self, now: datetime, stats: StreamStats, market_open: bool) -> None:
        if stats.state == StreamState.ERROR and not self._fatal_alerted:
            self._fatal_alerted = True
            self.notifier_factory().send(
                f"[PAPER TRADING] Market data stream stopped: {stats.last_error}. "
                "Retrying every 5 minutes; check the Alpaca keys/data plan.",
                critical=True,
            )
        elif stats.state == StreamState.SUBSCRIBED:
            self._fatal_alerted = False
        down_for = now - self._down_since if self._down_since else None
        if (
            down_for is not None
            and market_open
            and down_for > self.disconnect_alert_after
            and not self._down_alerted
        ):
            self._down_alerted = True
            self.notifier_factory().notify(
                Event.BROKER_DISCONNECTED,
                f"[PAPER TRADING] Market data stream down for {int(down_for.total_seconds())}s "
                f"(last error: {stats.last_error}). Live quotes are stale; no new entries.",
            )
        elif down_for is None and self._down_alerted:
            self._down_alerted = False
            self.notifier_factory().notify(
                Event.BROKER_DISCONNECTED, "[PAPER TRADING] Market data stream restored."
            )

    # ----- lifecycle ----------------------------------------------------------------------

    async def _every(self, name: str, fn: Callable[[], Awaitable[None]]) -> None:
        while True:
            await asyncio.sleep(self.intervals[name])
            try:
                await fn()
            except Exception as exc:
                log.error("stream_service_loop_failed", loop=name, error=type(exc).__name__)

    def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        try:
            await self.refresh_symbols()
        except Exception as exc:
            # Benchmarks still stream; the symbols loop retries the watchlists.
            log.error("stream_symbols_failed", error=type(exc).__name__)
            self.symbols = self.default_symbols[: self.max_symbols]
            await self.stream.set_symbols(self.symbols)
        stream_task = asyncio.create_task(self.stream.run())
        loops = [
            asyncio.create_task(self._every("flush", self.flush)),
            asyncio.create_task(self._every("bars", self.flush_bars)),
            asyncio.create_task(self._every("symbols", self.refresh_symbols)),
            asyncio.create_task(self._every("heartbeat", self.heartbeat)),
        ]
        stop_task = asyncio.create_task(self._stopped.wait())
        try:
            await asyncio.wait({stream_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if stream_task.done() and not self._stopped.is_set():
                stream_task.result()  # surfaces a bug in the client
                raise RuntimeError("market data stream exited unexpectedly")
        finally:
            self.stream.stop()
            for t in (*loops, stop_task):
                t.cancel()
            await asyncio.gather(*loops, stop_task, return_exceptions=True)
            try:
                await asyncio.wait_for(stream_task, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                stream_task.cancel()
            for name, fn in (("flush", self.flush), ("bars", self.flush_bars),
                             ("heartbeat", self.heartbeat)):  # fmt: skip
                try:
                    await fn()
                except Exception as exc:
                    log.error(
                        "stream_service_final_flush_failed", loop=name, error=type(exc).__name__
                    )


def build_service(
    settings: AtlasSettings | None = None, broker: BrokerSettings | None = None
) -> LiveDataService:
    import redis

    settings = settings or get_settings()
    broker = broker or BrokerSettings()  # type: ignore[call-arg]
    if broker.data_feed == "delayed_sip":
        raise ValueError("live streaming needs ALPACA_DATA_FEED=iex or sip")
    feed = broker.data_feed

    def factory(**callbacks: Any) -> AlpacaStream:
        return AlpacaStream(
            broker.api_key_id.get_secret_value(),
            broker.api_secret_key.get_secret_value(),
            feed,
            data_timeout=settings.stream_data_timeout_seconds,
            **callbacks,
        )

    return LiveDataService(
        factory,
        LiveStore(redis.Redis.from_url(settings.redis_url, socket_timeout=5)),
        get_sessionmaker(),
        default_symbols=settings.ingest_default_symbols,
        max_symbols=settings.stream_max_symbols,
        max_quote_age_seconds=get_policy().policy.data_quality.max_quote_age_seconds,
    )


async def serve(service: LiveDataService) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, service.stop)
    await service.run()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, service="stream")
    asyncio.run(serve(build_service(settings)))


if __name__ == "__main__":
    main()
