# Security model

## Security-critical decisions
1. **Paper-only, enforced in code, config, database and CI** — ADR 0002.
2. **Credential separation by container** — only `executor` gets `broker.env`; only `worker`
   gets `llm.env`; enforced by `test_paper_isolation.py` against `docker-compose.yml`.
3. **LLMs are advisory.** Output is parsed into Pydantic schemas; nothing an LLM returns is
   executable. External text is wrapped in `<untrusted_content>` with a standing instruction
   that it is data, never instructions. Refusals/truncations raise, never pass through.
4. **Deterministic risk authority.** The risk policy (`config/policy.yaml`) is validated
   against hard ceilings in code; it can only change through a reviewed commit and restart.
   Its SHA-256 is written to the append-only audit log at every API start.
5. **Kill switch fails closed.** It starts ENGAGED on a fresh deployment; a missing row or a
   database error means "trading not allowed". Resume requires an admin and password
   re-entry and is audited. Engagement cancels open orders, reconciles, alerts; it does not
   liquidate.
6. **Audit log is append-only** at the database level (PostgreSQL triggers block UPDATE,
   DELETE and TRUNCATE).

## Authentication & authorization
* No default accounts. Users are created with `python -m atlas.scripts.create_user`.
* Argon2id password hashing; 12-char minimum; 5 failed attempts → 15 min lockout; constant
  work for unknown usernames.
* HS256 JWTs (≥32-char secret required outside development), 60 min TTL, `exp/iat/iss`
  required, `alg=none` rejected. Deactivated users are rejected on every request.
* Roles: `viewer` (read), `operator` (+ engage kill switch), `admin` (+ resume, audit log).
* Dashboard keeps the token in an `httpOnly`, `SameSite=Strict`, `Secure` (prod) cookie;
  state-changing route handlers also verify `Origin`.
* Login is rate limited per IP (Redis-backed, in-process fallback).

## Secrets
* Never in source control (`.gitignore`, CI secret scanning with gitleaks), prompts or logs.
* Structured logs and Sentry events pass through a redactor (sensitive keys and
  credential-shaped values: Alpaca keys, Anthropic keys, JWTs, bearer tokens, Telegram tokens).
  httpx INFO logging is suppressed because Telegram URLs embed the bot token.
* Production: load env files from a secret manager (e.g. AWS Secrets Manager / GCP Secret
  Manager / Doppler) rather than files on disk.

## Network
* PostgreSQL/Redis are on an internal Docker network with no published ports.
* API and dashboard bind to `127.0.0.1`; expose them only through a TLS-terminating reverse
  proxy (Caddy/nginx/cloud LB) with HTTPS.
* Docker bridge networks permit outbound traffic. In production, restrict egress at the
  host/cloud firewall: executor → `paper-api.alpaca.markets`, `data.alpaca.markets`,
  `api.telegram.org`; worker → LLM provider, data sources; api → none (Sentry if used).

## Supply chain
* Locked dependencies (`uv.lock`, `package-lock.json`), `pip-audit` and `npm audit` in CI,
  Dependabot config, pinned base images.
* Phase 1 note: Next.js 16.4.0 had critical advisories (GHSA-2464-fhr4-w9xw,
  GHSA-673q-mjm6-r5xr, GHSA-p3m5-59mp-jv5r); the dashboard pins the patched 16.4.3.

## Backup & recovery
* `scripts/backup.sh` (pg_dump, gzip) — schedule daily, store off-host, encrypted.
* Recovery: restore dump → `alembic upgrade head` → start services. The kill switch state is
  restored with the data; if in doubt engage it before starting the executor. The first
  broker sync repopulates positions/balances from Alpaca (source of truth).

## Path to live trading (not available in this deployment)
Separate deployment and credentials, independent review of risk/execution code, ≥ the
promotion gates in the spec, a written liquidation policy, and explicit owner sign-off.
