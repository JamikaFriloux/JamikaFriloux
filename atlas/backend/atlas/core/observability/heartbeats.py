"""Which heartbeats can go stale. Shared by the health endpoint and the operations agent."""

from __future__ import annotations

from datetime import timedelta

HEARTBEAT_STALE_AFTER = timedelta(minutes=3)
# Services that heartbeat continuously (every 15-60 s). Scheduled jobs (ingestion, universe,
# news, agents) heartbeat only when they run, so an old heartbeat is normal for them.
CONTINUOUS_SERVICES = frozenset({"worker", "executor", "broker", "stream"})
