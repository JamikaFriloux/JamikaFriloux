# Setup, operation, maintenance and troubleshooting

## Prerequisites
* Docker 24+ with Compose v2 (production-like run), **or** for local development:
  Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16, Redis 7.
* An Alpaca account with **paper trading** API keys (Phase 2 broker sync).
* Optional: a Telegram bot token and chat id; an Anthropic API key (Phase 5).

Never paste keys into chat, issues or commits. Put them only in the env files below.

## 1. Configure
```bash
cd atlas
cp .env.example .env              # shared config
cp broker.env.example broker.env  # Alpaca PAPER keys — executor only
cp llm.env.example llm.env        # LLM key — research worker only
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into ATLAS_JWT_SECRET
```
Edit `POSTGRES_PASSWORD` and make `ATLAS_DATABASE_URL` use the same password.

### Getting Alpaca paper keys
1. Sign in at https://app.alpaca.markets, switch the account selector to **Paper**.
2. Generate API keys on the paper dashboard (key IDs start with `PK`).
3. Put them in `broker.env`. Live keys (`AK…`) and live URLs are rejected at startup.

### Telegram (optional)
1. Message @BotFather → `/newbot` → copy the token into `ATLAS_TELEGRAM_BOT_TOKEN`.
2. Send any message to your bot, then open
   `https://api.telegram.org/bot<token>/getUpdates` and copy `chat.id` into
   `ATLAS_TELEGRAM_CHAT_ID`.

## 2a. Run with Docker Compose
```bash
docker compose up -d --build
docker compose run --rm api python -m atlas.scripts.create_user admin --role admin
docker compose exec executor python -m atlas.scripts.check_alpaca   # verifies paper auth
```
Open http://localhost:3000 and sign in. The API is at http://localhost:8000 (docs at /docs
outside production).

## 2b. Run locally without Docker
```bash
cd atlas && make setup
export ATLAS_DATABASE_URL=postgresql+psycopg://atlas:<pw>@localhost:5432/atlas
export ATLAS_JWT_SECRET=<48+ random chars>
make migrate
cd backend && uv run python -m atlas.scripts.create_user admin --role admin && cd ..
make api          # terminal 1
make worker       # terminal 2
make beat         # terminal 3
set -a; . ./broker.env; set +a; make executor   # terminal 4 (only this one gets broker creds)
ATLAS_API_URL=http://localhost:8000 make dashboard  # terminal 5
```

## 3. First start: arming the system
A fresh database starts with the **kill switch engaged** (fail-closed). After verifying
configuration and a clean `check_alpaca` run, an admin resumes it in **Risk Center**
(requires re-entering the password). Until Phase 3, there are no strategies, so resuming only
enables the gate; no orders are generated.

## Operation
* **Overview**: equity/cash/P&L come from the last broker sync (every 60 s). If no sync has
  happened the page says so — it never shows placeholder numbers.
* **Kill switch**: operators can engage; admins resume. Engaging cancels open paper orders,
  reconciles and alerts. Positions are not liquidated.
* **Audit**: `GET /api/v1/audit` (admin) lists logins, kill-switch actions, service starts.

## Maintenance
* Migrations: `make migrate` (or `docker compose run --rm migrate`).
* Backups: `scripts/backup.sh` daily; test restores monthly.
* Dependencies: Dependabot PRs; CI runs `pip-audit` and `npm audit`.
* Risk policy changes: edit `config/policy.yaml` in a PR, review, deploy, restart. Values
  above the hard limits in `core/configuration/policy.py` are refused at startup.

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| API fails with `ATLAS_JWT_SECRET must be at least 32 characters` | Set a strong secret in `.env`. |
| Login always 401 | No user created, wrong password, or account locked for 15 min after 5 failures. |
| Login 429 | Rate limit (10/min/IP). Wait a minute. |
| `/health/ready` 503 | PostgreSQL or Redis unreachable; check `docker compose ps` / logs. |
| Executor: `ALPACA_BASE_URL must be https://paper-api.alpaca.markets` | Remove any live URL from `broker.env`. |
| Executor: `LiveEnvironmentDetected` | Keys belong to a live account. Generate paper keys. |
| Overview says "No broker data yet" | Executor not running, or `broker.env` missing; check `docker compose logs executor`. |
| Broker status `error` in Settings | Alpaca unreachable or keys revoked; a Telegram alert is sent if configured. |
| Calendar discrepancies in `check_alpaca` | Update `exchange-calendars` (new holiday rules) and re-run. |
