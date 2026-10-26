import math
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from atlas.core.backtesting.runner import ValidationUnavailable, run_validation
from atlas.core.backtesting.validation import (
    bootstrap_lower_bound,
    neighbor_params,
    params_hash,
    validate_strategy,
)
from atlas.core.configuration.policy import LoadedPolicy
from atlas.core.data.bars import BarRecord
from atlas.core.data.calendar import NY, MarketCalendar
from atlas.core.data.ingestion import upsert_bars
from atlas.core.models.db import (
    AuditLog,
    StrategyRecord,
    StrategyStatus,
    UniverseMember,
    UniverseSnapshot,
    ValidationReport,
    Watchlist,
)
from atlas.core.strategies import registry
from atlas.core.strategies.baselines import RsiPullback, TrendBreakout

CAL = MarketCalendar()
DAYS = CAL.sessions_between(date(2021, 1, 4), date(2025, 12, 31))
END = DAYS[-1]


def relaxed(policy) -> LoadedPolicy:
    g = policy.policy.promotion_gates.model_copy(
        update={
            "min_history_years": 3,
            "min_trades": 30,
            "holdout_years": 1,
            "holdout_min_trades": 10,
            "bootstrap_samples": 500,
            "min_profitable_windows_pct": 50,
            "min_stable_neighbors_pct": 50,
        }
    )
    return LoadedPolicy(
        policy=policy.policy.model_copy(update={"promotion_gates": g}),
        path=policy.path,
        sha256=policy.sha256,
    )


def series(symbol, seed, drift, vol=0.012, dip_every=0, adjustment="all"):
    rng = random.Random(seed)
    p, out = 60.0, []
    for i, d in enumerate(DAYS):
        p *= 1 + drift + rng.gauss(0, vol)
        if dip_every and i % dip_every in (0, 1):
            p *= 0.975  # sharp two-day pullback...
        if dip_every and i % dip_every in (3, 4):
            p *= 1.03  # ...that recovers
        c = round(p, 2)
        o = round(c * (1 + rng.gauss(0, 0.002)), 2)
        out.append(
            BarRecord(
                symbol=symbol,
                timeframe="1Day",
                ts=datetime(d.year, d.month, d.day, tzinfo=NY),
                open=Decimal(str(o)),
                high=Decimal(str(round(max(o, c) * 1.006, 2))),
                low=Decimal(str(round(min(o, c) * 0.994, 2))),
                close=Decimal(str(c)),
                volume=Decimal(3_000_000),
                source="t",
                adjustment=adjustment,
            )
        )
    return out


def dataset(kind):
    if kind == "edge":  # uptrends with recurring, recovering pullbacks: RSI(2) has an edge
        return {f"E{k}": series(f"E{k}", k, 0.0006, dip_every=11 + k) for k in range(3)}
    return {f"N{k}": series(f"N{k}", 100 + k, -0.0002, vol=0.02) for k in range(3)}  # no edge


def test_neighbor_params():
    labels = [label for label, _ in neighbor_params(RsiPullback())]
    assert "rsi_n=3" in labels and "rsi_n=1" not in labels  # 1 is below the allowed minimum
    assert "trend_n=180" in labels and "trend_n=220" in labels  # ints step by 10%
    assert "stop_atr=2.25" in labels and "stop_atr=2.75" in labels  # floats by 10%
    assert all(isinstance(v, RsiPullback) for _, v in neighbor_params(RsiPullback()))


def test_bootstrap_lower_bound():
    assert bootstrap_lower_bound([1.0, 2.0, 0.5, 1.5], 500, 0.95, "s") > 0
    noisy = [(-1) ** i * 3 + 0.01 for i in range(100)]
    assert bootstrap_lower_bound(noisy, 500, 0.95, "s") < 0
    assert bootstrap_lower_bound([1.0], 500, 0.95, "s") is None
    a = bootstrap_lower_bound(noisy, 500, 0.95, "seed")
    assert a == bootstrap_lower_bound(noisy, 500, 0.95, "seed")  # reproducible


@pytest.fixture(scope="module")
def edge_outcome():
    from atlas.core.configuration.policy import load_policy
    from atlas.core.configuration.settings import AtlasSettings

    pol = relaxed(load_policy(AtlasSettings(_env_file=None).policy_path))  # type: ignore[call-arg]
    bars = dataset("edge")
    return pol, bars, validate_strategy(RsiPullback(), pol, CAL, bars, bars, end=END)


def test_validation_gates_on_data_with_an_edge(edge_outcome):
    _, _, out = edge_outcome
    names = [g.name for g in out.gates]
    assert names == [
        "history",
        "trades",
        "profit_factor",
        "sharpe",
        "drawdown",
        "holdout_trades",
        "holdout_sharpe",
        "walk_forward",
        "stability",
        "bootstrap",
    ]
    assert out.passed == all(g.passed for g in out.gates)
    full = out.metrics["full"]
    assert full["trades"] > 0 and full["sharpe"] > 0 and out.metrics["windows"]
    assert len(out.metrics["neighbors"]) == len(neighbor_params(RsiPullback()))
    assert out.params_hash == params_hash(RsiPullback().params.model_dump())
    assert out.equity_curve[-1][0] == END.isoformat() and any(
        "survivorship" in c for c in out.caveats
    )


def test_simulation_is_deterministic(edge_outcome):
    from atlas.core.backtesting.simulator import Simulator

    pol, bars, out = edge_outcome
    start = date.fromisoformat(out.metrics["full"]["start"])
    a = Simulator(RsiPullback(), pol.policy, CAL).run(bars, bars, start, END)
    assert a.summary() == out.metrics["full"]


def test_validation_fails_without_an_edge(policy):
    bars = dataset("none")
    out = validate_strategy(TrendBreakout(), relaxed(policy), CAL, bars, bars, end=END)
    assert not out.passed
    failed = {g.name for g in out.gates if not g.passed}
    assert failed & {"trades", "profit_factor", "sharpe", "bootstrap"}


def test_real_policy_requires_eight_years(policy):
    bars = {"E0": dataset("edge")["E0"]}
    out = validate_strategy(RsiPullback(), policy, CAL, bars, bars, end=END)
    history = next(g for g in out.gates if g.name == "history")
    assert not history.passed and not out.passed


# ---------- promotion gate wiring ----------
def _report(db, policy, **kw):
    sid = kw.pop("strategy_id", "rsi_pullback")
    params = registry.STRATEGIES[sid].params.model_dump()
    row = ValidationReport(
        strategy_id=sid,
        version="1.0.0",
        params=params,
        params_hash=params_hash(params),
        target_status="PAPER",
        policy_sha256=policy.sha256,
        passed=True,
        data_start=date(2016, 1, 4),
        data_end=date(2026, 10, 23),
        symbols=["SPY"],
        gates=[],
        metrics={},
        equity_curve=[],
        caveats=[],
        runtime_seconds=Decimal(1),
    )
    for k, v in kw.items():
        setattr(row, k, v)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize(
    "override",
    [
        {"passed": False},
        {"params_hash": "deadbeefdeadbeef"},
        {"policy_sha256": "0" * 64},
        {"version": "0.9.0"},
        {"created_at": datetime.now(UTC) - timedelta(days=200)},
    ],
)
def test_only_a_matching_fresh_passing_report_unlocks_promotion(db, policy, override):
    registry.sync_registry(db)
    _report(db, policy, **override)
    assert (
        registry.passing_validation_report(db, "rsi_pullback", "1.0.0", StrategyStatus.PAPER)
        is None
    )
    with pytest.raises(registry.StatusChangeRefused):
        registry.set_status(db, "rsi_pullback", StrategyStatus.PAPER, actor="admin", reason="go")


def test_valid_report_allows_paper_but_not_live_candidate(db, policy):
    registry.sync_registry(db)
    rep = _report(db, policy)
    assert registry.passing_validation_report(
        db, "rsi_pullback", "1.0.0", StrategyStatus.PAPER
    ) == str(rep.id)
    row = registry.set_status(
        db, "rsi_pullback", StrategyStatus.PAPER, actor="admin", reason="validated"
    )
    assert row.status == StrategyStatus.PAPER
    audit_row = db.scalars(
        select(AuditLog).where(AuditLog.action == "strategy.status_changed")
    ).one()
    assert audit_row.details["validation_report"] == str(rep.id)
    with pytest.raises(registry.StatusChangeRefused):
        registry.set_status(
            db, "rsi_pullback", StrategyStatus.LIVE_CANDIDATE, actor="admin", reason="x"
        )


# ---------- runner ----------
def _seed_db(db, with_raw=True):
    bars = {"E0": dataset("edge")["E0"]}
    for s in bars.values():
        upsert_bars(db, s)
        if with_raw:
            upsert_bars(db, [b.model_copy(update={"adjustment": "raw"}) for b in s])
    snap = UniverseSnapshot(
        as_of=END, source="t", criteria={}, assets_seen=1, member_count=1, exclusions={}
    )
    db.add(snap)
    db.flush()
    for sym in bars:
        db.add(
            UniverseMember(
                snapshot_id=snap.id,
                symbol=sym,
                name=sym,
                exchange="NYSE",
                last_close=Decimal(60),
                adv_usd=Decimal("1e8"),
                sessions=20,
                fractionable=True,
                shortable=False,
                easy_to_borrow=False,
            )
        )
    db.add(Watchlist(name="w", symbols=sorted(bars)))
    db.flush()


def test_runner_stores_an_immutable_style_report(db, policy):
    _seed_db(db)
    rep = run_validation(
        db,
        "rsi_pullback",
        policy=relaxed(policy),
        calendar=CAL,
        default_symbols=[],
        requested_by="tester",
    )
    stored = db.get(ValidationReport, rep.id)
    assert stored.data_end == END and stored.symbols == ["E0"]
    assert stored.version == "1.0.0" and stored.requested_by == "tester"
    assert len(stored.gates) == 10 and stored.metrics["full"]["trades"] > 0
    assert all(
        not isinstance(v, float) or math.isfinite(v) for v in stored.metrics["full"].values()
    )


def test_runner_requires_raw_history_and_universe(db, policy):
    with pytest.raises(ValidationUnavailable, match="universe"):
        run_validation(db, "rsi_pullback", policy=policy, calendar=CAL, default_symbols=[])
    _seed_db(db, with_raw=False)
    with pytest.raises(ValidationUnavailable, match="raw daily history"):
        run_validation(db, "rsi_pullback", policy=policy, calendar=CAL, default_symbols=[])
    db.get(StrategyRecord, "rsi_pullback").status = StrategyStatus.RETIRED
    with pytest.raises(ValidationUnavailable, match="retired"):
        run_validation(db, "rsi_pullback", policy=policy, calendar=CAL, default_symbols=[])
