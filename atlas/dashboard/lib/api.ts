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
    total_pl: string;
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
