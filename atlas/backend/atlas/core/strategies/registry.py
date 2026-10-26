"""Strategy registry and lifecycle.

Statuses: RESEARCH -> PAPER -> LIVE_CANDIDATE, plus RETIRED. Rules (CLAUDE.md rule 8):
  * strategies never change their own status; only an admin can, and every change is audited;
  * RESEARCH -> PAPER requires a passing validation report (Phase 4) for the exact version;
    PAPER -> LIVE_CANDIDATE requires a passing paper track record (Phase 6,
    ``core/performance/track_record.py``) for the exact version;
  * a code change to a strategy's version or parameters puts it back in RESEARCH, because the
    evidence was for different code;
  * LIVE_CANDIDATE keeps paper trading and still cannot submit live orders in this deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.core.backtesting.validation import params_hash
from atlas.core.configuration.policy import get_policy
from atlas.core.models.db import StrategyRecord, StrategyStatus, ValidationReport
from atlas.core.security import audit
from atlas.core.strategies.base import Strategy
from atlas.core.strategies.baselines import RsiPullback, TrendBreakout

St = StrategyStatus

STRATEGIES: dict[str, Strategy] = {s.id: s for s in (TrendBreakout(), RsiPullback())}

ALLOWED: dict[StrategyStatus, frozenset[StrategyStatus]] = {
    St.RESEARCH: frozenset({St.PAPER, St.RETIRED}),
    St.PAPER: frozenset({St.RESEARCH, St.LIVE_CANDIDATE, St.RETIRED}),
    St.LIVE_CANDIDATE: frozenset({St.PAPER, St.RESEARCH, St.RETIRED}),
    St.RETIRED: frozenset({St.RESEARCH}),
}
GATED = frozenset({(St.RESEARCH, St.PAPER), (St.PAPER, St.LIVE_CANDIDATE)})


class StatusChangeRefused(ValueError):
    pass


def passing_validation_report(
    session: Session, strategy_id: str, version: str, target: StrategyStatus
) -> str | None:
    """Id of a passing validation report that justifies ``target``, else None.

    Accepted for PAPER only when it passed, matches the exact version and parameters now
    registered, was produced under the current policy (a policy change can change the
    simulation), and is no older than ``report_max_age_days``. LIVE_CANDIDATE is judged on the
    paper track record instead (``passing_track_record``).
    """
    if target != St.PAPER:
        return None
    row = session.get(StrategyRecord, strategy_id)
    if row is None:
        return None
    policy = get_policy()
    cutoff = datetime.now(UTC) - timedelta(days=policy.policy.promotion_gates.report_max_age_days)
    report = session.scalars(
        select(ValidationReport)
        .where(
            ValidationReport.strategy_id == strategy_id,
            ValidationReport.version == version,
            ValidationReport.params_hash == params_hash(row.params),
            ValidationReport.policy_sha256 == policy.sha256,
            ValidationReport.passed.is_(True),
            ValidationReport.target_status == St.PAPER.value,
            ValidationReport.created_at >= cutoff,
        )
        .order_by(ValidationReport.id.desc())
        .limit(1)
    ).first()
    return str(report.id) if report is not None else None


def sync_registry(session: Session) -> list[StrategyRecord]:
    """Make the strategies table match the code (insert new; demote changed or removed)."""
    rows = {r.id: r for r in session.scalars(select(StrategyRecord)).all()}
    for sid, strat in STRATEGIES.items():
        params = strat.params.model_dump()
        row = rows.get(sid)
        if row is None:
            row = StrategyRecord(
                id=sid,
                version=strat.version,
                status=St.RESEARCH,
                params=params,
                updated_by="system",
            )
            session.add(row)
            rows[sid] = row
            audit.record(
                session,
                actor="system",
                action="strategy.registered",
                target=sid,
                details={"version": strat.version, "params": params},
            )
        elif row.version != strat.version or row.params != params:
            before = {"version": row.version, "params": row.params, "status": row.status.value}
            row.version, row.params, row.updated_by = strat.version, params, "system"
            if row.status != St.RETIRED:
                row.status = St.RESEARCH
            audit.record(
                session,
                actor="system",
                action="strategy.code_changed",
                target=sid,
                details={"before": before, "version": strat.version, "status": row.status.value},
            )
    for sid, row in rows.items():
        if sid not in STRATEGIES and row.status != St.RETIRED:
            row.status, row.updated_by = St.RETIRED, "system"
            audit.record(session, actor="system", action="strategy.removed_from_code", target=sid)
    session.flush()
    return sorted(rows.values(), key=lambda r: r.id)


def set_status(
    session: Session,
    strategy_id: str,
    new: StrategyStatus,
    *,
    actor: str,
    reason: str,
    ip_address: str | None = None,
) -> StrategyRecord:
    row = session.get(StrategyRecord, strategy_id)
    if row is None:
        raise LookupError(strategy_id)
    if not reason.strip():
        raise StatusChangeRefused("a reason is required")
    if new not in ALLOWED[row.status]:
        raise StatusChangeRefused(f"{row.status.value} -> {new.value} is not allowed")
    report_id = record_id = None
    if (row.status, new) == (St.RESEARCH, St.PAPER):
        report_id = passing_validation_report(session, strategy_id, row.version, new)
        if report_id is None:
            raise StatusChangeRefused(
                f"{row.status.value} -> {new.value} requires a passing validation report for "
                f"{strategy_id} v{row.version} under the current policy (run a validation)"
            )
    elif (row.status, new) == (St.PAPER, St.LIVE_CANDIDATE):
        from atlas.core.performance.track_record import passing_track_record

        record_id = passing_track_record(session, strategy_id, get_policy())
        if record_id is None:
            raise StatusChangeRefused(
                f"{row.status.value} -> {new.value} requires a passing paper track record for "
                f"{strategy_id} v{row.version} under the current policy (see Performance)"
            )
    before = row.status
    row.status, row.updated_by = new, actor
    audit.record(
        session,
        actor=actor,
        action="strategy.status_changed",
        target=strategy_id,
        details={
            "from": before.value,
            "to": new.value,
            "reason": reason,
            "version": row.version,
            "validation_report": report_id,
            "track_record": record_id,
        },
        ip_address=ip_address,
    )
    session.flush()
    return row
