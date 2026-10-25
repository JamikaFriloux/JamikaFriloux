# ADR 0002 — Live trading is technically inaccessible

Status: Accepted (Phase 1)

Defense in depth, each layer independently sufficient to block live orders:

1. `AtlasSettings.trading_mode` is `Literal["paper"]`; the policy file's `trading_mode` too.
2. `BrokerSettings.base_url` must equal `https://paper-api.alpaca.markets`.
3. Key IDs beginning with `AK` (Alpaca's live prefix) are rejected.
4. `TradingClient(..., paper=True)` is a literal everywhere; `url_override` is banned.
5. `verify_paper_environment` checks the resolved URL and that the account number starts
   with `PA` before the gateway is used; reconciliation refuses non-paper accounts.
6. The `account_snapshots` table has a `CHECK (is_paper)` constraint.
7. Static tests (`tests/unit/test_paper_isolation.py`) fail CI if any of the above regress
   or if any non-executor container is given broker credentials.

There is no runtime toggle. Live trading would require: a separate repository branch and
deployment, separate credentials and secret store, independent code review of the execution
and risk paths, and explicit written owner authorization. See `docs/security.md`.
