from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from atlas.core.configuration.policy import LoadedPolicy, load_policy
from atlas.core.configuration.settings import AtlasSettings
from atlas.core.models.db import Base, KillSwitch

TEST_SECRET = "test-secret-" + "x" * 40


@pytest.fixture
def settings() -> AtlasSettings:
    return AtlasSettings(
        environment="test",
        jwt_secret=SecretStr(TEST_SECRET),
        database_url="sqlite://",
        log_json=False,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def policy(settings: AtlasSettings) -> LoadedPolicy:
    return load_policy(settings.policy_path)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        # Mirrors the migration: deployments start with the kill switch engaged.
        s.add(KillSwitch(id=1, engaged=True, reason="initial", engaged_by="system"))
        s.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s
