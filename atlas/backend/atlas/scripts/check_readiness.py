"""Go/no-go preflight for unattended paper forward testing (Phase 8). Places no orders.

Usage (executor environment, with the services running):
    python -m atlas.scripts.check_readiness

Reads the broker (account, open orders, positions) and the state the running services
write: kill switch, strategy statuses and their validation reports, the account snapshot
broker sync writes, service heartbeats, the universe snapshot, daily-bar quality reports,
and reference data. Every FAIL is something that stops ATLAS from trading paper on its own
or from being watched while it does; WARN is worth knowing but doesn't block.

Exit 0 when nothing fails, 2 otherwise. Prints no secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.configuration.policy import get_policy
from atlas.core.configuration.settings import AtlasSettings, RefDataSettings, get_settings
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import ingestion_symbols, last_completed_session
from atlas.core.data.universe import current_universe
from atlas.core.execution.broker import AccountInfo, BrokerOrder, PositionInfo
from atlas.core.models.db import (
    AccountSnapshot,
    DataQualityReport,
    InstrumentReference,
    ServiceHeartbeat,
    StrategyRecord,
    StrategyStatus,
)
from atlas.core.models.session import session_scope
from atlas.core.observability.heartbeats import HEARTBEAT_STALE_AFTER
from atlas.core.reference.earnings import blackout_span, fresh_coverage
from atlas.core.risk.engine import ACCOUNT_MAX_AGE
from atlas.core.risk.kill_switch import get_state
from atlas.core.strategies.registry import passing_validation_report

# Continuous services the order path needs. The stream is optional: the order path falls
# back to Alpaca's REST latest quote when the stream cache is stale.
REQUIRED_SERVICES = ("worker", "executor", "broker")
ORDERABLE = (StrategyStatus.PAPER, StrategyStatus.LIVE_CANDIDATE)


def required_universe_as_of(now: datetime, calendar: MarketCalendar) -> date:
    """The snapshot ``as_of`` the most recently opened session trades on.

    A snapshot ``as_of = D`` is built premarket (06:45 NY) for the session after D, so after a
    close the next snapshot isn't due yet; it is missing only once its session has opened.
    """
    day = now.astimezone(NY).date()
    opened = None
    for offset in range(0, 15):
        s = calendar.session(day - timedelta(days=offset))
        if s is not None and s.open <= now:
            opened = s.day
            break
    if opened is None:  # pragma: no cover - the calendar always has a session within 15 days
        raise RuntimeError("no session opened in the last 15 days")
    for offset in range(1, 15):
        prev = calendar.session(opened - timedelta(days=offset))
        if prev is not None:
            return prev.day
    raise RuntimeError("no session before the last opened one")  # pragma: no cover


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts  # SQLite drops the zone


@dataclass(frozen=True)
class Check:
    name: str
    level: Literal["ok", "warn", "fail"]
    detail: str


@dataclass
class BrokerView:
    account: AccountInfo | None
    open_orders: list[BrokerOrder] = field(default_factory=list)
    positions: list[PositionInfo] = field(default_factory=list)
    error: str | None = None


def assess(
    session: Session,
    *,
    now: datetime,
    broker: BrokerView,
    settings: AtlasSettings,
    ref: RefDataSettings,
    calendar: MarketCalendar,
) -> list[Check]:
    out: list[Check] = []

    def add(name: str, ok: bool, detail: str, *, warn_only: bool = False) -> None:
        out.append(Check(name, "ok" if ok else ("warn" if warn_only else "fail"), detail))

    add("mode", settings.trading_mode == "paper", f"trading_mode={settings.trading_mode}")

    acct = broker.account
    if acct is None:
        add("broker", False, f"account unavailable ({broker.error or 'not read'})")
    else:
        problems = []
        if not acct.is_paper:
            problems.append("not a paper account")
        if acct.status != "ACTIVE":
            problems.append(f"status {acct.status}")
        if acct.trading_blocked:
            problems.append("trading blocked")
        if acct.shorting_enabled is not False:
            problems.append(f"shorting_enabled={acct.shorting_enabled}")
        if acct.margin_multiplier is not None and acct.margin_multiplier > 1:
            problems.append(f"margin multiplier {acct.margin_multiplier}")
        add(
            "broker",
            not problems,
            "; ".join(problems)
            or f"paper ACTIVE, long-only, no margin; equity {acct.equity}, cash {acct.cash}",
        )
        add(
            "broker book",
            True,
            f"{len(broker.positions)} positions, {len(broker.open_orders)} open orders",
        )

    ks = get_state(session)
    add(
        "kill switch",
        not ks.engaged,
        f"engaged ({ks.reason or 'no reason'}): an admin resumes it in Risk Center"
        if ks.engaged
        else "released",
    )

    rows = session.scalars(select(StrategyRecord).order_by(StrategyRecord.id)).all()
    orderable = [r for r in rows if r.status in ORDERABLE]
    add(
        "strategies",
        bool(orderable),
        ", ".join(f"{r.id} {r.version} {r.status.value}" for r in rows) or "none registered",
    )
    for r in orderable:
        report = passing_validation_report(session, r.id, r.version, StrategyStatus.PAPER)
        add(
            f"validation {r.id}",
            report is not None,
            f"passing report #{report}"
            if report
            else "no passing report for this version, parameters and policy within the max age",
        )

    snap = session.scalars(
        select(AccountSnapshot).order_by(AccountSnapshot.ts.desc()).limit(1)
    ).first()
    if snap is None:
        add("account snapshot", False, "none: broker sync has never run")
    else:
        age = now - _utc(snap.ts)
        add(
            "account snapshot",
            age <= ACCOUNT_MAX_AGE,
            f"{int(age.total_seconds())} s old (risk engine needs <= "
            f"{int(ACCOUNT_MAX_AGE.total_seconds())} s)",
        )

    beats = {b.service: b for b in session.scalars(select(ServiceHeartbeat)).all()}
    for svc in (*REQUIRED_SERVICES, "stream"):
        b = beats.get(svc)
        if b is None:
            ok, detail = False, "never reported"
        else:
            age = now - _utc(b.last_seen)
            ok = age <= HEARTBEAT_STALE_AFTER and b.status == "ok"
            detail = f"{b.status}, {int(age.total_seconds())} s ago"
        if svc == "stream" and not ok:
            detail += " (order path falls back to REST quotes)"
        add(f"service {svc}", ok, detail, warn_only=svc == "stream")

    uni = current_universe(session)
    if uni is None:
        add("universe", False, "no snapshot")
    else:
        required = required_universe_as_of(now, calendar)
        latest_close = last_completed_session(calendar, now).day
        if uni.as_of < required:
            add("universe", False, f"as_of {uni.as_of}; the session in progress needs {required}")
        elif uni.as_of < latest_close:
            add(
                "universe",
                False,
                f"as_of {uni.as_of}; the {latest_close} snapshot is built at 06:45 NY before "
                "the next session",
                warn_only=True,
            )
        else:
            add("universe", True, f"as_of {uni.as_of}")

    watched = ingestion_symbols(session, settings.ingest_default_symbols)
    stale, missing = [], []
    for sym in watched:
        q = session.scalars(
            select(DataQualityReport)
            .where(
                DataQualityReport.symbol == sym,
                DataQualityReport.timeframe == "1Day",
                DataQualityReport.adjustment == "all",
            )
            .order_by(DataQualityReport.ts.desc())
            .limit(1)
        ).first()
        if q is None:
            missing.append(sym)
        elif q.stale or not q.ok:
            stale.append(sym)
    add(
        "daily bars",
        not stale and not missing,
        f"{len(watched)} symbols"
        + (f"; stale or failed {stale}" if stale else "")
        + (f"; never ingested {missing}" if missing else ""),
    )

    classified = set(session.scalars(select(InstrumentReference.symbol)).all())
    unclassified = sorted(set(watched) - classified)
    add(
        "classification",
        not unclassified,
        f"unclassified {unclassified}" if unclassified else f"all {len(watched)} classified",
    )
    today = now.astimezone(NY).date()
    span = blackout_span(
        today, get_policy().policy.session.block_entries_before_earnings_days, calendar
    )
    span = span or [today]
    cov = fresh_coverage(
        session,
        start=span[0],
        end=span[-1],
        now=now,
        max_age=timedelta(hours=ref.earnings_max_age_hours),
    )
    add(
        "earnings calendar",
        cov is not None,
        f"fresh, covers {span[0]}..{span[-1]}"
        if cov
        else f"none within {ref.earnings_max_age_hours} h: every stock entry is rejected",
    )

    add(
        "alerts",
        settings.telegram_enabled,
        "Telegram configured"
        if settings.telegram_enabled
        else "Telegram not configured: failures, halts and orders would go unnoticed",
    )
    return out


def read_broker() -> BrokerView:
    from atlas.apps.executor.tasks import get_gateway

    try:
        gw = get_gateway()
        return BrokerView(gw.get_account(), gw.list_open_orders(), gw.list_positions())
    except Exception as exc:
        return BrokerView(None, error=type(exc).__name__)


def main() -> int:
    now = datetime.now(UTC)
    broker = read_broker()
    with session_scope() as s:
        checks = assess(
            s,
            now=now,
            broker=broker,
            settings=get_settings(),
            ref=RefDataSettings(),
            calendar=MarketCalendar(),
        )
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"{c.level.upper():4}  {c.name:<{width}}  {c.detail}")
    fails = [c for c in checks if c.level == "fail"]
    print("RESULT", "READY" if not fails else f"NOT READY: {len(fails)} failing check(s)")
    return 0 if not fails else 2


if __name__ == "__main__":
    raise SystemExit(main())
