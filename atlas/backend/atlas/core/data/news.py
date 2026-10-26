"""News ingestion: provider-agnostic records and storage.

News text is untrusted external content. It is stored as received (HTML stripped,
entities decoded) and only ever reaches an LLM wrapped by ``wrap_untrusted``.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from atlas.core.models.db import NewsArticle

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
MAX_HEADLINE = 500
MAX_SUMMARY = 2000


def clean_text(text: str | None, limit: int) -> str:
    if not text:
        return ""
    out = _SPACE.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()
    return out[:limit]


@dataclass(frozen=True)
class NewsItem:
    source: str
    provider_id: str
    published_at: datetime
    headline: str
    summary: str = ""
    provider: str | None = None
    url: str | None = None
    updated_at: datetime | None = None
    symbols: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.provider_id}"[:64]


class NewsSource(Protocol):
    def get_news(
        self, symbols: Sequence[str], start: datetime, end: datetime
    ) -> list[NewsItem]: ...


def upsert_news(session: Session, items: Iterable[NewsItem], *, now: datetime | None = None) -> int:
    """Insert new articles and refresh updated ones. Returns how many rows changed."""
    now = now or datetime.now(UTC)
    changed = 0
    for it in items:
        headline = clean_text(it.headline, MAX_HEADLINE)
        if not headline:
            continue
        row = session.get(NewsArticle, it.key)
        if row is None:
            row = NewsArticle(id=it.key)
            session.add(row)
        elif row.updated_at is not None and it.updated_at is not None:
            prev = row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=UTC)
            if it.updated_at <= prev:
                continue
        elif row.updated_at is not None or it.updated_at is None:
            continue
        row.source, row.provider = it.source, it.provider
        row.published_at, row.updated_at, row.fetched_at = it.published_at, it.updated_at, now
        row.headline, row.summary = headline, clean_text(it.summary, MAX_SUMMARY)
        row.url = it.url
        row.symbols = sorted({s.upper() for s in it.symbols})
        changed += 1
    session.flush()
    return changed
