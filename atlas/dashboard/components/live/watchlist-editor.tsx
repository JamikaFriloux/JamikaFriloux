"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { UniverseSummary, Watchlists } from "@/lib/api";

type Member = UniverseSummary["members"][number];

/** Turn an API error body into one readable line, including per-symbol rejection reasons. */
function errorText(status: number, data: unknown): string {
  const d = (data ?? {}) as { detail?: unknown; error?: unknown };
  if (typeof d.detail === "string") return d.detail;
  if (d.detail && typeof d.detail === "object" && "rejected" in d.detail) {
    const rejected = (d.detail as { rejected: Record<string, string> }).rejected;
    return Object.entries(rejected).map(([s, why]) => `${s}: ${why}`).join("; ");
  }
  if (Array.isArray(d.detail)) return "Invalid input";
  if (typeof d.error === "string") return d.error;
  return `Request failed (${status})`;
}

export function WatchlistEditor({ data, canEdit }: { data: Watchlists; canEdit: boolean }) {
  const router = useRouter();
  const [newName, setNewName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function send(url: string, method: "POST" | "PUT" | "DELETE", body?: unknown): Promise<boolean> {
    setPending(true);
    setMessage(null);
    try {
      const res = await fetch(url, {
        method,
        headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        setMessage(errorText(res.status, await res.json().catch(() => null)));
        return false;
      }
      router.refresh();
      return true;
    } catch {
      setMessage("Dashboard could not reach the API");
      return false;
    } finally {
      setPending(false);
    }
  }

  const setSymbols = (name: string, symbols: string[]) =>
    send(`/api/watchlists/${encodeURIComponent(name)}`, "PUT", { symbols });

  async function create() {
    if (await send("/api/watchlists", "POST", { name: newName.trim(), symbols: [] })) setNewName("");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Watchlists</CardTitle>
        <span className="text-[11px] text-muted">
          Universe {data.universe_as_of ?? "unavailable"} · stream {data.stream.symbols}/{data.stream.capacity} symbols
        </span>
      </CardHeader>
      <CardContent className="space-y-5">
        {data.stream.symbols > data.stream.capacity ? (
          <p className="rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
            More symbols than the live stream carries ({data.stream.capacity}). Benchmarks come first; the rest still get
            minute bars but no live quotes.
          </p>
        ) : null}
        {data.universe_as_of === null ? (
          <p className="text-sm text-muted">
            No universe snapshot yet, so symbols can't be added. It is built premarket by the executor.
          </p>
        ) : null}

        {data.watchlists.length === 0 ? <p className="text-sm text-muted">No watchlists yet.</p> : null}
        {data.watchlists.map((wl) => {
          const symbols = wl.symbols.map((s) => s.symbol);
          return (
            <div key={wl.name} className="space-y-2 border-t border-line pt-4 first:border-t-0 first:pt-0">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{wl.name}</div>
                {canEdit ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={pending}
                    aria-label={`Delete watchlist ${wl.name}`}
                    onClick={() => confirm(`Delete watchlist "${wl.name}"?`) && send(`/api/watchlists/${encodeURIComponent(wl.name)}`, "DELETE")}
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Delete
                  </Button>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {wl.symbols.length === 0 ? <span className="text-xs text-muted">Empty</span> : null}
                {wl.symbols.map((s) => (
                  <span
                    key={s.symbol}
                    className={
                      "num inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs " +
                      (s.in_universe === false ? "border-warn/40 text-warn" : "border-line bg-panel-2")
                    }
                    title={s.in_universe === false ? "No longer in the universe" : undefined}
                  >
                    {s.symbol}
                    {canEdit ? (
                      <button
                        type="button"
                        className="text-muted hover:text-loss disabled:opacity-50"
                        disabled={pending}
                        aria-label={`Remove ${s.symbol} from ${wl.name}`}
                        onClick={() => setSymbols(wl.name, symbols.filter((x) => x !== s.symbol))}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    ) : null}
                  </span>
                ))}
              </div>
              {canEdit && data.universe_as_of ? (
                <UniverseSearch
                  exclude={symbols}
                  disabled={pending}
                  onPick={(sym) => setSymbols(wl.name, [...symbols, sym])}
                />
              ) : null}
            </div>
          );
        })}

        {canEdit ? (
          <div className="flex gap-2 border-t border-line pt-4">
            <Input
              placeholder="new-watchlist-name"
              value={newName}
              maxLength={64}
              onChange={(e) => setNewName(e.target.value.toLowerCase())}
            />
            <Button variant="outline" disabled={pending || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(newName.trim())} onClick={create}>
              <Plus className="h-4 w-4" /> Create
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted">Operator role required to edit watchlists.</p>
        )}
        {message ? <p className="text-xs text-loss" role="alert">{message}</p> : null}
      </CardContent>
    </Card>
  );
}

function UniverseSearch({ exclude, disabled, onPick }: { exclude: string[]; disabled: boolean; onPick: (s: string) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Member[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const t = window.setTimeout(async () => {
      try {
        const res = await fetch(`/api/universe?q=${encodeURIComponent(term)}`, { signal: controller.signal });
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as UniverseSummary;
        setResults(data.members);
        setSearchError(null);
      } catch (e) {
        if (!controller.signal.aborted) setSearchError("Universe search unavailable");
      }
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(t);
    };
  }, [q]);

  const shown = results.filter((m) => !exclude.includes(m.symbol));
  return (
    <div className="relative">
      <Input placeholder="Add from universe: symbol or name" value={q} onChange={(e) => setQ(e.target.value)} disabled={disabled} />
      {q.trim() && (shown.length > 0 || searchError) ? (
        <ul className="absolute z-10 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-line bg-panel-2 py-1 shadow-xl">
          {searchError ? <li className="px-3 py-2 text-xs text-loss">{searchError}</li> : null}
          {shown.map((m) => (
            <li key={m.symbol}>
              <button
                type="button"
                className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-panel"
                onClick={() => {
                  onPick(m.symbol);
                  setQ("");
                }}
              >
                <span className="num w-16 font-medium">{m.symbol}</span>
                <span className="min-w-0 flex-1 truncate text-muted">{m.name}</span>
                <Badge tone="neutral">{m.exchange}</Badge>
                <span className="num w-24 text-right text-xs text-muted">${(Number(m.adv_usd) / 1e6).toFixed(0)}M/day</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
