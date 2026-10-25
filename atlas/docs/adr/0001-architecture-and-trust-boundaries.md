# ADR 0001 — Service architecture and trust boundaries

Status: Accepted (Phase 1)

## Context
ATLAS combines untrusted inputs (news, filings, LLM output) with an account that can place
orders. The spec requires that no LLM can place orders or override risk controls.

## Decision
Five runtime services sharing one codebase but different credentials:

| Service    | Role                                             | Broker creds | LLM key | Internet |
|------------|--------------------------------------------------|--------------|---------|----------|
| `api`      | FastAPI: auth, RBAC, read models, kill switch    | no           | no      | not required |
| `dashboard`| Next.js UI; holds the session token in an httpOnly cookie | no  | no      | no |
| `worker`   | Celery `default` queue: research, data quality, reports | no    | yes     | yes |
| `executor` | Celery `execution` queue: broker sync, orders, kill-switch actions | **yes (paper)** | no | yes |
| `beat`     | Celery scheduler (America/New_York)              | no           | no      | no |

* PostgreSQL is the system of record (orders, order events, positions, snapshots, audit log).
* Redis is the Celery broker and rate-limit store; nothing authoritative lives only in Redis.
* Agents produce **schema-validated proposals**. Only deterministic code (signal engine →
  risk engine → execution) can create an order, and only the executor can submit it.
* The broker is the source of truth for balances/positions/order status; local state is
  reconciled against it every minute.

## Consequences
* Compromise of the LLM key, a prompt injection, or the API process cannot submit orders.
* The executor is the highest-value target: one process, concurrency 1, minimal code.
