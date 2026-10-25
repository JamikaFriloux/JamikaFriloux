# ADR 0004 — Job scheduling

Status: Accepted (Phase 1)

Celery 5 with Redis (AOF persistence enabled) and Celery beat, timezone `America/New_York`.

* `task_acks_late` + `reject_on_worker_lost`: a task killed mid-run is redelivered.
* Periodic execution tasks carry `expires` so a backlog does not burst after an outage.
* Tasks must be idempotent; order state is in PostgreSQL and reconciled with the broker, so a
  lost or duplicated task cannot create a duplicate order (client-order-id idempotency).
* Market-hours logic never relies on cron alone: every job checks the XNYS calendar
  (`atlas.core.data.calendar`), which handles holidays, early closes and DST.
