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

export class ApiUnavailable extends Error {}

async function apiGet<T>(path: string): Promise<T> {
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
  if (!res.ok) throw new ApiUnavailable(`ATLAS API ${path} returned ${res.status}`);
  return (await res.json()) as T;
}

export const getStatus = () => apiGet<SystemStatus>("/api/v1/status");
export const getMe = () => apiGet<Me>("/api/v1/auth/me");
