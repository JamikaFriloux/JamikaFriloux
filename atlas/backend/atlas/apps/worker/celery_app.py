"""Celery application shared by the research worker and the execution service.

Queues:
  * ``default``   - research / data-quality / reporting jobs. Consumed by ``worker``
                    (no broker credentials).
  * ``execution`` - broker sync, order handling, kill-switch follow-up. Consumed ONLY by
                    ``executor``, the single container that receives ALPACA_* credentials.

Celery's broker is Redis (durable enough for scheduling; order state itself lives in
PostgreSQL and is reconciled against the brokerage, so a lost task is recoverable).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from atlas.core.configuration.settings import get_settings

_settings = get_settings()

celery_app = Celery(
    "atlas",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    include=["atlas.apps.worker.tasks", "atlas.apps.executor.tasks"],
)
celery_app.conf.update(
    timezone=_settings.timezone,  # America/New_York: DST handled by the scheduler
    enable_utc=True,
    task_default_queue="default",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=240,
    broker_connection_retry_on_startup=True,
    task_routes={"atlas.execution.*": {"queue": "execution"}},
    beat_schedule={
        "worker-heartbeat": {
            "task": "atlas.worker.heartbeat",
            "schedule": 30.0,
            "options": {"expires": 25},
        },
        "executor-heartbeat": {
            "task": "atlas.execution.heartbeat",
            "schedule": 30.0,
            "options": {"expires": 25},
        },
        "broker-sync": {
            "task": "atlas.execution.broker_sync",
            "schedule": 60.0,
            "options": {"expires": 55},
        },
        # Daily bars: after the close (also catches early closes) and a premarket catch-up.
        "ingest-daily-bars": {
            "task": "atlas.execution.ingest_daily_bars",
            "schedule": crontab(hour="7,16", minute=20, day_of_week="mon-fri"),
            "options": {"expires": 3600},
        },
        # Minute bars: every 5 minutes; the task itself skips outside session + 30 minutes.
        "ingest-minute-bars": {
            "task": "atlas.execution.ingest_minute_bars",
            "schedule": crontab(minute="*/5", hour="9-16", day_of_week="mon-fri"),
            "options": {"expires": 240},
        },
        "premarket-readiness": {
            "task": "atlas.worker.premarket_readiness",
            "schedule": crontab(hour=8, minute=30, day_of_week="mon-fri"),
        },
    },
)
