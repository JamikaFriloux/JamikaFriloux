import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Stat, plTone } from "@/components/stat";
import { getStatus } from "@/lib/api";
import { fmtTime, fmtUsd } from "@/lib/utils";

export default async function OverviewPage() {
  const s = await getStatus();
  const a = s.account;
  return (
    <>
      <PageHeader title="Overview" subtitle={`Server time ${fmtTime(s.server_time)}`}>
        <TradingStatus allowed={s.trading_allowed} engaged={s.kill_switch.engaged} />
      </PageHeader>

      {a ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Account equity" value={fmtUsd(a.equity)} sub={`as of ${fmtTime(a.as_of)}`} />
          <Stat label="Available cash" value={fmtUsd(a.cash)} sub={`Buying power ${fmtUsd(a.buying_power)}`} />
          <Stat label="Daily P&L" value={fmtUsd(a.day_pl, true)} tone={plTone(a.day_pl)} sub="vs. prior close" />
          <Stat label="Total P&L" value={fmtUsd(a.total_pl, true)} tone={plTone(a.total_pl)} sub={a.total_pl_since ? `since first broker sync ${fmtTime(a.total_pl_since)}` : "unavailable"} />
        </div>
      ) : (
        <EmptyState title="No broker data yet">
          The execution service has not completed a paper-account sync. Configure{" "}
          <code className="num">broker.env</code> with Alpaca paper keys and start the{" "}
          <code className="num">executor</code> service. ATLAS never displays placeholder balances.
        </EmptyState>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Active positions</CardTitle>
            <span className="text-xs text-muted">{s.open_orders} open orders</span>
          </CardHeader>
          <CardContent>
            {s.positions.length === 0 ? (
              <p className="text-sm text-muted">No open positions.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                    <tr>
                      <th className="py-2 font-medium">Symbol</th>
                      <th className="py-2 text-right font-medium">Qty</th>
                      <th className="py-2 text-right font-medium">Avg entry</th>
                      <th className="py-2 text-right font-medium">Market value</th>
                      <th className="py-2 text-right font-medium">Unrealized</th>
                    </tr>
                  </thead>
                  <tbody className="num">
                    {s.positions.map((p) => (
                      <tr key={p.symbol} className="border-t border-line">
                        <td className="py-2 font-sans font-medium">{p.symbol}</td>
                        <td className="py-2 text-right">{Number(p.qty)}</td>
                        <td className="py-2 text-right">{fmtUsd(p.avg_entry_price)}</td>
                        <td className="py-2 text-right">{fmtUsd(p.market_value)}</td>
                        <td className={`py-2 text-right ${plTone(p.unrealized_pl) === "gain" ? "text-gain" : plTone(p.unrealized_pl) === "loss" ? "text-loss" : ""}`}>
                          {fmtUsd(p.unrealized_pl, true)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Market regime</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted">
                {s.market_regime ?? "Not yet classified — the Market Intelligence agent ships in Phase 5."}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>System health</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {s.services.length === 0 ? (
                <p className="text-sm text-muted">No service heartbeats recorded.</p>
              ) : (
                s.services.map((svc) => (
                  <div key={svc.service} className="flex items-center justify-between text-sm">
                    <span className="capitalize">{svc.service}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-xs text-muted">{fmtTime(svc.last_seen)}</span>
                      <Badge tone={svc.status === "ok" ? "gain" : svc.status === "error" ? "loss" : "warn"}>
                        {svc.status}
                      </Badge>
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

function TradingStatus({ allowed, engaged }: { allowed: boolean; engaged: boolean }) {
  if (allowed) return <Badge tone="gain">● Trading enabled (paper)</Badge>;
  return <Badge tone="loss">● {engaged ? "Kill switch engaged — new orders disabled" : "Trading disabled"}</Badge>;
}
