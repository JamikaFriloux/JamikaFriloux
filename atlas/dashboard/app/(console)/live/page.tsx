import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { QuoteBoard, type QuoteGroup } from "@/components/live/quote-board";
import { WatchlistEditor } from "@/components/live/watchlist-editor";
import { getLiveMarket, getMe, getStatus, getUniverseSummary, getWatchlists } from "@/lib/api";

export default async function LiveTradingPage() {
  const [market, lists, universe, status, me] = await Promise.all([
    getLiveMarket(),
    getWatchlists(),
    getUniverseSummary(),
    getStatus(),
    getMe(),
  ]);
  const snap = universe.snapshot;
  const groups: QuoteGroup[] = [
    { title: "Benchmarks", symbols: lists.benchmarks.map((symbol) => ({ symbol })) },
    ...lists.watchlists.map((wl) => ({ title: `Watchlist · ${wl.name}`, symbols: wl.symbols })),
  ];

  return (
    <>
      <PageHeader title="Live Trading" subtitle="Live quotes for benchmarks and watchlists, from the executor's market-data stream">
        <div className="flex flex-wrap items-center gap-2">
          {status.trading_allowed ? (
            <Badge tone="gain">Trading enabled (paper)</Badge>
          ) : (
            <Badge tone="loss">{status.kill_switch.engaged ? "Kill switch engaged" : "Trading disabled"}</Badge>
          )}
          {snap ? (
            <Badge tone={snap.stale ? "warn" : "neutral"}>
              Universe {snap.as_of} · {snap.member_count.toLocaleString("en-US")} symbols{snap.stale ? " · stale" : ""}
            </Badge>
          ) : (
            <Badge tone="warn">No universe snapshot</Badge>
          )}
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <QuoteBoard initial={market} groups={groups} positions={status.positions} />
        <div className="space-y-4">
          <WatchlistEditor data={lists} canEdit={me.role === "operator" || me.role === "admin"} />
          <div className="rounded-xl border border-dashed border-line bg-panel/50 px-5 py-4 text-xs text-muted">
            <div className="mb-1 text-sm font-medium text-fg">Orders and signals: Phase 3</div>
            There is no manual order entry. Paper orders will come only from the deterministic signal engine, through
            the risk engine and order state machine. Their activity will appear here.
          </div>
        </div>
      </div>
    </>
  );
}
