import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE, apiBase } from "./session";

export type KillSwitch = {
  engaged: boolean;
  reason: string | null;
  engaged_at: string | null;
  engaged_by: string | null;
  resumed_at: string | null;
  resumed_by: string | null;
};

export type SystemStatus = {
  trading_mode: "PAPER";
  server_time: string;
  kill_switch: KillSwitch;
  trading_allowed: boolean;
  account: null | {
    as_of: string;
    source: string;
    status: string;
    equity: string;
    cash: string;
    buying_power: string;
    long_market_value: string;
    day_pl: string;
    total_pl: string | null;
    total_pl_since: string | null;
    capital_base: string;
    shorting_enabled: boolean | null;
    trading_blocked: boolean;
  };
  positions: {
    symbol: string;
    qty: string;
    avg_entry_price: string;
    market_value: string;
    unrealized_pl: string;
    synced_at: string;
  }[];
  open_orders: number;
  market_regime: string | null;
  services: { service: string; status: string; last_seen: string }[];
  policy: { sha256: string; version: number; limits: Record<string, number> };
};

export type Me = { username: string; role: "viewer" | "operator" | "admin" };

export type LiveQuote = {
  symbol: string;
  bid: string | null;
  ask: string | null;
  quote_ts: string | null;
  quote_age_seconds: number | null;
  last: string | null;
  trade_ts: string | null;
  fresh: boolean;
};

export type LiveMarket = {
  trading_mode: "PAPER";
  server_time: string;
  market_open: boolean;
  max_quote_age_seconds: number;
  stream: null | {
    status: string;
    state: string;
    updated_at: string;
    market_open: string;
    last_data_at: string;
  };
  quotes: LiveQuote[];
};

export type Watchlists = {
  universe_as_of: string | null;
  benchmarks: string[];
  stream: { symbols: number; capacity: number };
  watchlists: {
    name: string;
    updated_at: string | null;
    symbols: { symbol: string; in_universe: boolean | null }[];
  }[];
};

export type UniverseSummary = {
  snapshot: null | {
    id: number;
    as_of: string;
    created_at: string | null;
    stale: boolean;
    source: string;
    criteria: Record<string, unknown>;
    assets_seen: number;
    member_count: number;
    exclusions: Record<string, number>;
  };
  total: number | null;
  members: {
    symbol: string;
    name: string;
    exchange: string;
    last_close: string;
    adv_usd: string;
    sessions: number;
    fractionable: boolean;
  }[];
};

export type StrategyRow = {
  id: string;
  version: string;
  status: "RESEARCH" | "PAPER" | "LIVE_CANDIDATE" | "RETIRED";
  description: string | null;
  lookback_sessions: number | null;
  params: Record<string, number | string | boolean>;
  updated_at: string | null;
  updated_by: string;
  signals: number;
  can_submit_paper_orders: boolean;
};

export type SignalRow = {
  id: string;
  strategy_id: string;
  strategy_version: string;
  symbol: string;
  kind: "entry" | "exit";
  as_of: string;
  ref_price: string | null;
  stop_price: string | null;
  mode: "shadow" | "paper";
  status: string;
  reason: Record<string, unknown>;
  decision: null | { approved: boolean; failed: string[]; qty: string | null; limit_price: string | null; ts: string | null };
};

export type RiskDecisionRow = {
  id: number;
  ts: string | null;
  signal_id: string | null;
  strategy_id: string;
  symbol: string;
  kind: string;
  mode: string;
  approved: boolean;
  qty: string | null;
  limit_price: string | null;
  capital_base: string | null;
  failed: string[];
  checks: { name: string; passed: boolean; detail: string }[];
};

export type OrderRow = {
  client_order_id: string;
  symbol: string;
  side: string;
  type: string;
  purpose: string | null;
  qty: string | null;
  limit_price: string | null;
  stop_price: string | null;
  time_in_force: string;
  state: string;
  filled_qty: string | null;
  filled_avg_price: string | null;
  strategy_id: string | null;
  created_at: string | null;
  submitted_at: string | null;
  last_error: string | null;
};

export class ApiUnavailable extends Error {}

async function apiGet<T>(path: string): Promise<T> {
  const result = await apiGetOptional<T>(path);
  if (result === null) throw new ApiUnavailable(`ATLAS API ${path} returned 503`);
  return result;
}

/** Like apiGet, but a 503 (e.g. live data not available yet) yields null instead of an error. */
async function apiGetOptional<T>(path: string): Promise<T | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) redirect("/login");
  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    throw new ApiUnavailable(`ATLAS API unreachable at ${path}`);
  }
  if (res.status === 401) redirect("/login?expired=1");
  if (res.status === 503) return null;
  if (!res.ok) throw new ApiUnavailable(`ATLAS API ${path} returned ${res.status}`);
  return (await res.json()) as T;
}

export const getStatus = () => apiGet<SystemStatus>("/api/v1/status");
export const getMe = () => apiGet<Me>("/api/v1/auth/me");
export const getLiveMarket = () => apiGetOptional<LiveMarket>("/api/v1/market/live");
export const getWatchlists = () => apiGet<Watchlists>("/api/v1/watchlists");
export const getUniverseSummary = () => apiGet<UniverseSummary>("/api/v1/universe?limit=1");
export const getStrategies = () => apiGet<StrategyRow[]>("/api/v1/strategies");
export const getSignals = (limit = 25) => apiGet<SignalRow[]>(`/api/v1/signals?limit=${limit}`);
export const getRiskDecisions = (rejectedOnly = false, limit = 25) =>
  apiGet<RiskDecisionRow[]>(`/api/v1/risk-decisions?limit=${limit}&rejected_only=${rejectedOnly}`);
export const getOrders = (limit = 25) => apiGet<OrderRow[]>(`/api/v1/orders?limit=${limit}`);
