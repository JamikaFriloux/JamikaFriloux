from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch

from pydantic import SecretStr
from sqlalchemy import select

from atlas.apps.executor import tasks as executor_tasks
from atlas.apps.worker import tasks as worker_tasks
from atlas.core.configuration.settings import LLMSettings
from atlas.core.data.news import NewsItem
from atlas.core.models.db import AgentReport, NewsArticle, ServiceHeartbeat


def _scope(session_factory):
    @contextmanager
    def scope():
        with session_factory() as s:
            yield s
            s.commit()

    return scope


class FakeNews:
    def __init__(self, items=(), error=None):
        self.items, self.error, self.calls = list(items), error, []

    def get_news(self, symbols, start, end):
        self.calls.append(list(symbols))
        if self.error:
            raise self.error
        return self.items


def test_fetch_news_stores_articles(session_factory):
    item = NewsItem("alpaca", "1", datetime.now(UTC), "H", symbols=("SPY",))
    src = FakeNews([item, item])
    with (
        patch.object(executor_tasks, "session_scope", _scope(session_factory)),
        patch.object(executor_tasks, "get_news_source", lambda: src),
    ):
        out = executor_tasks.fetch_news.run()
    assert out == {"ok": True, "fetched": 2, "stored": 1}
    assert "SPY" in src.calls[0]
    with session_factory() as s:
        assert [a.id for a in s.scalars(select(NewsArticle)).all()] == ["alpaca:1"]
        assert s.get(ServiceHeartbeat, "news").status == "ok"


def test_fetch_news_outage_is_reported(session_factory):
    with (
        patch.object(executor_tasks, "session_scope", _scope(session_factory)),
        patch.object(executor_tasks, "get_news_source", lambda: FakeNews(error=TimeoutError())),
    ):
        out = executor_tasks.fetch_news.run()
    assert out == {"ok": False, "error": "TimeoutError"}
    with session_factory() as s:
        hb = s.get(ServiceHeartbeat, "news")
        assert hb.status == "error" and hb.details["error"] == "TimeoutError"


def test_run_agents_without_key_falls_back_to_features_only(session_factory):
    # provider=anthropic but no key: the worker must not crash; it runs without the LLM.
    settings = LLMSettings(provider="anthropic", anthropic_api_key=None, _env_file=None)
    with (
        patch.object(worker_tasks, "session_scope", _scope(session_factory)),
        patch("atlas.core.configuration.settings.LLMSettings", lambda: settings),
    ):
        out = worker_tasks.run_agents.run()
    statuses = {k: v["status"] for k, v in out["agents"].items()}
    assert out["ok"] is True and statuses["operations"] == "no_llm"
    assert statuses["market_intelligence"] == "no_data"  # no bars stored
    with session_factory() as s:
        assert len(s.scalars(select(AgentReport)).all()) == 5
        hb = s.get(ServiceHeartbeat, "agents")
        assert hb.status == "ok" and hb.details["provider"] == "disabled"


def test_run_agents_uses_configured_provider(session_factory):
    from atlas.integrations.llm.base import StaticProvider

    settings = LLMSettings(provider="anthropic", anthropic_api_key=SecretStr("k"), _env_file=None)
    narrative = '{"summary": "s", "key_points": [], "risks": [], "data_gaps": []}'
    with (
        patch.object(worker_tasks, "session_scope", _scope(session_factory)),
        patch("atlas.core.configuration.settings.LLMSettings", lambda: settings),
        patch(
            "atlas.integrations.llm.anthropic_provider.build_provider",
            lambda _s: StaticProvider([narrative] * 5),
        ),
    ):
        out = worker_tasks.run_agents.run(only=["operations"])
    assert out["agents"] == {"operations": {"id": 1, "status": "ok"}}


def test_update_track_records_task(session_factory):
    from atlas.core.models.db import TrackRecord

    with patch.object(worker_tasks, "session_scope", _scope(session_factory)):
        out = worker_tasks.update_track_records.run()
    assert out["ok"] is True and set(out["strategies"]) == {"rsi_pullback", "trend_breakout"}
    with session_factory() as s:
        recs = s.scalars(select(TrackRecord)).all()
        assert {r.kind for r in recs} == {"forward_sim"}  # nothing is in PAPER
        assert all("no validation report" in (r.note or "") for r in recs)
        assert s.get(ServiceHeartbeat, "track_records").status == "ok"


def test_update_track_records_task_reports_failure(session_factory):
    with (
        patch.object(worker_tasks, "session_scope", _scope(session_factory)),
        patch(
            "atlas.core.performance.track_record.update_track_records",
            side_effect=RuntimeError("x"),
        ),
    ):
        out = worker_tasks.update_track_records.run()
    assert out == {"ok": False, "error": "RuntimeError"}
    with session_factory() as s:
        assert s.get(ServiceHeartbeat, "track_records").status == "error"
