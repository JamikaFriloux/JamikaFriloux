"""Fixed-window rate limiter. Redis-backed when available (shared across API replicas), with
an in-process fallback so a Redis outage degrades to per-instance limits instead of no limits."""

from __future__ import annotations

import threading
import time
from typing import Any


class RateLimiter:
    def __init__(self, redis_client: Any | None = None, prefix: str = "atlas:rl"):
        self._redis = redis_client
        self._prefix = prefix
        self._local: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        """Record one hit. Returns True if allowed, False if over the limit."""
        window = int(time.time() // window_seconds)
        bucket = f"{self._prefix}:{key}:{window}"
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(bucket)
                pipe.expire(bucket, window_seconds + 1)
                count, _ = pipe.execute()
                return int(count) <= limit
            except Exception:  # noqa: S110 - fall back to local limiting below
                pass
        with self._lock:
            w, count = self._local.get(key, (window, 0))
            if w != window:
                w, count = window, 0
            count += 1
            self._local[key] = (w, count)
            return count <= limit
