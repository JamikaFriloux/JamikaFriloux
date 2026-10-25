"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LiveMarket, LiveQuote, SystemStatus } from "@/lib/api";
import { cn, fmtTime, fmtUsd } from "@/lib/utils";

const POLL_MS = 2000;
// If we haven't heard from the API for this long we can no longer vouch for any quote.
const POLL_STALE_MS = 6000;

export type QuoteGroup = {
  title: string;
  symbols: { symbol: string; in_universe?: boolean | null }[];
};

export function QuoteBoard({
  initial,
  groups,
  positions,
}: {
  initial: LiveMarket | null;
  groups: QuoteGroup[];
  positions: SystemStatus["positions"];
}) {
  const [market, setMarket] = useState<LiveMarket | null>(initial);
  const [fetchedAt, setFetchedAt] = useState<number>(() => Date.now());
  const [error, setError] = useState<string | null>(initial ? null : "Live data unavailable");
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      if (document.visibilityState === "hidden") return;
      try {
        const res = await fetch("/api/live", { cache: "no-store" });
        if (res.status === 401) {
          window.location.href = "/login?expired=1";
          return;
        }
        if (!res.ok) throw new Error(res.status === 503 ? "Live data unavailable" : `API returned ${res.status}`);
        const data = (await res.json()) as LiveMarket;
        if (cancelled) return;
        setMarket(data);
        setFetchedAt(Date.now());
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Live data unavailable");
      }
    }
    const id = window.setInterval(poll, POLL_MS);
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      window.clearInterval(tick);
    };
  }, []);

  const quotes = useMemo(() => {
    const map = new Map<string, LiveQuote>();
    for (const q of market?.quotes ?? []) map.set(q.symbol, q);
    return map;
  }, [market]);

  const sinceFetch = (now - fetchedAt) / 1000;
  const pollHealthy = !error && now - fetchedAt < POLL_STALE_MS;
  const isFresh = (q: LiveQuote | undefined) => Boolean(q?.fresh && pollHealthy);

  return (
    <div className="space-y-4">
      <StatusStrip market={market} error={error} sinceFetch={sinceFetch} />
      {groups.map((g) => (
        <Card key={g.title}>
          <CardHeader>
            <CardTitle>{g.title}</CardTitle>
            <span className="text-[11px] text-muted">{g.symbols.length} symbols</span>
          </CardHeader>
          <CardContent>
            {g.symbols.length === 0 ? (
              <p className="text-sm text-muted">No symbols yet. Add some from the universe below.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                    <tr>
                      <th className="py-2 font-medium">Symbol</th>
                      <th className="py-2 text-right font-medium">Bid</th>
                      <th className="py-2 text-right font-medium">Ask</th>
                      <th className="py-2 text-right font-medium">Spread</th>
                      <th className="py-2 text-right font-medium">Last</th>
                      <th className="py-2 text-right font-medium">Quote age</th>
                      <th className="py-2 text-right font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="num">
                    {g.symbols.map(({ symbol, in_universe }) => (
                      <QuoteRow
                        key={symbol}
                        symbol={symbol}
                        inUniverse={in_universe}
                        quote={quotes.get(symbol)}
                        fresh={isFresh(quotes.get(symbol))}
                        extraAge={pollHealthy ? sinceFetch : null}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
      <PositionsCard positions={positions} quotes={quotes} isFresh={isFresh} />
    </div>
  );
}

function StatusStrip({ market, error, sinceFetch }: { market: LiveMarket | null; error: string | null; sinceFetch: number }) {
  const stream = market?.stream ?? null;
  const statusAge = stream?.updated_at ? (Date.now() - new Date(stream.updated_at).getTime()) / 1000 : null;
  // The stream service reports every 15 s; much older means the executor isn't running.
  const statusStale = statusAge !== null && statusAge > 60;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-panel px-4 py-3 text-sm">
      {market ? (
        <Badge tone={market.market_open ? "gain" : "neutral"}>{market.market_open ? "Market open" : "Market closed"}</Badge>
      ) : null}
      <StreamBadge state={stream?.state ?? null} stale={statusStale} />
      {stream?.last_data_at ? (
        <span className="text-xs text-muted">Last market data {fmtTime(stream.last_data_at)}</span>
      ) : (
        <span className="text-xs text-muted">No market data received yet</span>
      )}
      <span className="ml-auto text-xs text-muted">
        {error ? (
          <span className="text-loss">{error} — quotes shown as not fresh</span>
        ) : (
          <>Updated {sinceFetch < 1 ? "just now" : `${Math.round(sinceFetch)}s ago`} · fresh = market open and quote ≤{" "}
            {market?.max_quote_age_seconds ?? "—"}s old</>
        )}
      </span>
    </div>
  );
}

function StreamBadge({ state, stale }: { state: string | null; stale: boolean }) {
  if (state === null) return <Badge tone="neutral">Stream status unavailable</Badge>;
  if (stale) return <Badge tone="loss">Stream status stale — executor may be down</Badge>;
  const map: Record<string, ["gain" | "warn" | "loss", string]> = {
    subscribed: ["gain", "Streaming"],
    connecting: ["warn", "Connecting"],
    backoff: ["warn", "Reconnecting"],
    error: ["loss", "Stream error"],
    stopped: ["loss", "Stream stopped"],
  };
  const [tone, label] = map[state] ?? ["warn", state];
  return <Badge tone={tone}>{label}</Badge>;
}

function QuoteRow({
  symbol,
  inUniverse,
  quote,
  fresh,
  extraAge,
}: {
  symbol: string;
  inUniverse?: boolean | null;
  quote: LiveQuote | undefined;
  fresh: boolean;
  extraAge: number | null;
}) {
  const bid = price(quote?.bid);
  const ask = price(quote?.ask);
  const spreadBps = bid !== null && ask !== null && ask >= bid ? ((ask - bid) / ((ask + bid) / 2)) * 10_000 : null;
  const age = quote?.quote_age_seconds != null ? quote.quote_age_seconds + (extraAge ?? 0) : null;
  return (
    <tr className={cn("border-t border-line", !fresh && "text-muted")}>
      <td className="py-2 font-sans font-medium text-fg">
        {symbol}
        {inUniverse === false ? (
          <span className="ml-2 align-middle">
            <Badge tone="warn" title="No longer passes the universe screen; trading will not use it">left universe</Badge>
          </span>
        ) : null}
      </td>
      <td className="py-2 text-right">{bid === null ? "—" : fmtUsd(bid)}</td>
      <td className="py-2 text-right">{ask === null ? "—" : fmtUsd(ask)}</td>
      <td className="py-2 text-right">{spreadBps === null ? "—" : `${spreadBps.toFixed(1)} bps`}</td>
      <td className="py-2 text-right">{price(quote?.last) === null ? "—" : fmtUsd(quote?.last)}</td>
      <td className="py-2 text-right">{age === null ? "—" : fmtAge(age)}</td>
      <td className="py-2 text-right font-sans">
        {!quote ? (
          <Badge tone="neutral">unavailable</Badge>
        ) : fresh ? (
          <Badge tone="gain">fresh</Badge>
        ) : (
          <Badge tone="warn">stale</Badge>
        )}
      </td>
    </tr>
  );
}

function PositionsCard({
  positions,
  quotes,
  isFresh,
}: {
  positions: SystemStatus["positions"];
  quotes: Map<string, LiveQuote>;
  isFresh: (q: LiveQuote | undefined) => boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Open positions</CardTitle>
        <span className="text-[11px] text-muted">Broker sync, with live mark when the quote is fresh</span>
      </CardHeader>
      <CardContent>
        {positions.length === 0 ? (
          <p className="text-sm text-muted">No open positions at the broker.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="py-2 font-medium">Symbol</th>
                  <th className="py-2 text-right font-medium">Qty</th>
                  <th className="py-2 text-right font-medium">Avg entry</th>
                  <th className="py-2 text-right font-medium">Live mid</th>
                  <th className="py-2 text-right font-medium">Live unrealized</th>
                  <th className="py-2 text-right font-medium">Unrealized (sync)</th>
                </tr>
              </thead>
              <tbody className="num">
                {positions.map((p) => {
                  const q = quotes.get(p.symbol);
                  const bid = price(q?.bid);
                  const ask = price(q?.ask);
                  const mid = isFresh(q) && bid !== null && ask !== null ? (bid + ask) / 2 : null;
                  const liveUpl = mid === null ? null : (mid - Number(p.avg_entry_price)) * Number(p.qty);
                  return (
                    <tr key={p.symbol} className="border-t border-line">
                      <td className="py-2 font-sans font-medium">{p.symbol}</td>
                      <td className="py-2 text-right">{p.qty}</td>
                      <td className="py-2 text-right">{fmtUsd(p.avg_entry_price)}</td>
                      <td className="py-2 text-right">{mid === null ? "—" : fmtUsd(mid)}</td>
                      <td className={cn("py-2 text-right", liveUpl !== null && (liveUpl >= 0 ? "text-gain" : "text-loss"))}>
                        {liveUpl === null ? "—" : fmtUsd(liveUpl, true)}
                      </td>
                      <td className="py-2 text-right">{fmtUsd(p.unrealized_pl, true)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** A usable price, or null. Alpaca sends 0 for a missing side of a one-sided quote. */
function price(v: string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function fmtAge(seconds: number): string {
  if (seconds < 0) return "0s";
  if (seconds < 120) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  if (seconds < 7200) return `${Math.round(seconds / 60)}m`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}
