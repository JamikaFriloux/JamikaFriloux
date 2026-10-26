# Deploying ATLAS (paper trading) to a DigitalOcean Droplet

One Ubuntu 24.04 Droplet with 4 GB RAM / 2 vCPU runs the whole stack with Docker Compose.
The commands below were rehearsed end to end (build, migrations, data bootstrap, validation,
readiness check, daemon restart) before this guide was written.

What the deployment guarantees:

* **Paper only.** The executor refuses to start with a live Alpaca URL, a live-looking key, or
  `ATLAS_TRADING_MODE` other than `paper`; `TradingClient` is built with `paper=True`.
* **Kill switch engaged** on a fresh database. Nothing can be ordered until an admin resumes
  it, and no strategy can order until an admin promotes it.
* **Nothing public but SSH.** PostgreSQL and Redis publish no ports; the API (8000) and the
  dashboard (3000) bind to `127.0.0.1`. Reach the dashboard through an SSH tunnel.
* **Secrets stay on the server**, in `chmod 600` files Git ignores. Only the `executor`
  container receives broker credentials.

## 0. Server preparation (once)

Docker, UFW (deny incoming, allow SSH) and a non-root `atlas` user in the `docker` group.
Docker must **not** listen on TCP: `sudo ss -ltnp | grep -E ':2375|:2376'` prints nothing.

Add 2 GB of swap as a safety net for memory peaks:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 1. Get the code

```bash
cd ~
git clone --branch claude/adoring-brown-n03w63 --single-branch \
  https://github.com/JamikaFriloux/JamikaFriloux.git
cd ~/JamikaFriloux/atlas
```

## 2. Secrets and settings

```bash
cp .env.example .env && cp broker.env.example broker.env && cp llm.env.example llm.env
chmod 600 .env broker.env llm.env
python3 -c "import secrets; print('ATLAS_JWT_SECRET=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
```

`.env` (shared, no broker keys):

| Key | Value |
|---|---|
| `ATLAS_ENVIRONMENT` | `production` |
| `ATLAS_TRADING_MODE` | `paper` (the only accepted value) |
| `POSTGRES_PASSWORD` | the generated password |
| `ATLAS_DATABASE_URL` | `postgresql+psycopg://atlas:<same password>@postgres:5432/atlas` |
| `ATLAS_REDIS_URL` | `redis://redis:6379/0` |
| `ATLAS_JWT_SECRET` | the generated secret |
| `ATLAS_TELEGRAM_BOT_TOKEN`, `ATLAS_TELEGRAM_CHAT_ID` | from @BotFather (see `docs/setup.md`) |
| `COMPOSE_FILE` | `docker-compose.yml:docker-compose.prod.yml` (add this line) |

Use a password without `@`, `:`, `/` or `#` (the generator above is safe), because it is
also part of the database URL.

`broker.env` (executor only):

| Key | Value |
|---|---|
| `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` | **paper** keys (IDs start with `PK`) |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` (leave as is) |
| `ALPACA_DATA_FEED` | `iex` |
| `ATLAS_REFDATA_FINNHUB_API_KEY` | Finnhub key |
| `ATLAS_REFDATA_SEC_USER_AGENT` | `ATLAS research you@example.com` (no quotes) |

`llm.env`: leave `ATLAS_LLM_PROVIDER=disabled` unless you add an Anthropic key.

Check without printing values: `grep -c '=$' .env broker.env` counts keys still empty.

## 3. Build and start

```bash
docker compose config --quiet && echo config OK
docker compose build            # ~5-10 min the first time
docker compose up -d
docker compose ps -a            # migrate: Exited (0); postgres/redis/api/dashboard: healthy
```

`migrate` runs `alembic upgrade head` before any service starts and on every
`docker compose up -d`; it is a no-op when the schema is current.

## 4. Verify paper mode, kill switch and the broker

```bash
curl -s localhost:8000/health/ready; echo
docker compose exec postgres psql -U atlas -d atlas -c "select engaged, reason from kill_switch"
docker compose exec executor python -m atlas.scripts.check_alpaca
```

Expected: `"database":"ok"`, `engaged = t`, and `check_alpaca` reports the paper URL, a PAPER
account, `shorting_enabled=False multiplier=1 -> OK` and 5/5 checks.

## 5. Admin user and dashboard access

```bash
docker compose run --rm api python -m atlas.scripts.create_user <name> --role admin
```

From your own computer:

```bash
ssh -N -L 3000:127.0.0.1:3000 atlas@<droplet-ip>
```

Open http://localhost:3000 (Chrome or Firefox). The session cookie is `Secure`, which browsers
accept on `localhost`.

## 6. Data bootstrap (once, ~5 min)

```bash
docker compose exec executor python -c "from atlas.apps.executor.tasks import refresh_universe as r; print(r.run())"
docker compose exec -T executor python - <<'EOF'
from atlas.core.data.watchlists import save_watchlist
from atlas.core.models.session import session_scope
symbols = """AAPL AMAT AMD AMZN AVGO BE CRWV DELL GLD GOOG GOOGL HYG INTC IVV LITE LQD META MRNA
MRVL MSFT MU NBIS NVDA ORCL PLTR SMH SNDK SOXL SOXX SPCX STX TLT TQQQ TSLA TSM VOO WDC""".split()
with session_scope() as s:
    save_watchlist(s, "research", symbols, actor="deploy", create=True)
print(f"watchlist research: {len(symbols)} symbols")
EOF
docker compose exec executor python -m atlas.scripts.backfill_history --years 10.5
docker compose exec executor python -c "from atlas.apps.executor.tasks import refresh_reference_data as r; print(r.run())"
docker compose exec executor python -m atlas.scripts.check_reference
```

Then **Strategy Lab → Run validation** for each strategy (5-7 min each).

## 6b. Telegram alerts

1. In Telegram, message **@BotFather** → `/newbot` → copy the token.
2. Send your new bot any message (bots can't message you first).
3. On **your own computer** (not in chat), open
   `https://api.telegram.org/bot<token>/getUpdates` and copy `"chat":{"id": ...}`.
4. On the server: `nano .env` → set `ATLAS_TELEGRAM_BOT_TOKEN` and `ATLAS_TELEGRAM_CHAT_ID`.
5. Recreate the services so they read it: `docker compose up -d`.
6. Test: `docker compose exec executor python -m atlas.scripts.send_test_alert`.
   `OK` means Telegram accepted it; otherwise the output says whether the token or the chat id
   is wrong. Neither is printed.

## 7. Readiness (before any promotion)

```bash
docker compose exec executor python -m atlas.scripts.check_readiness
```

On a fresh deployment it must fail on exactly: kill switch engaged, no strategy promoted, and
any missing piece (e.g. Telegram). Everything else (broker, account snapshot, worker,
executor, broker heartbeats, universe, daily bars, classification, earnings calendar) must be
OK. Promote a strategy and resume the kill switch only after that, as two separate admin
decisions.

## Operations

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f --tail=100 executor` (rotated: 5 x 10 MB per service) |
| Memory | `docker stats --no-stream` |
| Backup | `scripts/backup.sh ~/backups` (cron daily; copy off the server) |
| Update | `git pull && docker compose build && docker compose up -d` |
| Stop everything | `docker compose down` (data volumes are kept) |

Recovery after reboot: Docker starts at boot and every service has `restart: unless-stopped`,
so the stack comes back on its own. Verify after `sudo reboot` with `docker compose ps`.

Memory limits (`docker-compose.prod.yml`) come from the rehearsal: the idle stack uses
~1 GB; the executor peaked at 843 MiB during the 10.5-year backfill (limit 1.25 GiB); the
worker peaked at 1.57 GiB running both validations at once (limit 2 GiB). Everything at its
peak together is ~3 GB, so a 4 GB droplet fits, with swap as a backstop.

Never run `docker compose down -v`: `-v` deletes the database volume.
