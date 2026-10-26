import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { EquityChart } from "@/components/trading/equity-chart";
import { checkLabel } from "@/components/trading/labels";
import { getValidationReport, type Metrics } from "@/lib/api";
import { fmtTime, fmtUsd } from "@/lib/utils";

const METRIC_ROWS: [string, string, (v: unknown) => string][] = [
  ["Period", "start", (v) => String(v ?? "—")],
  ["Years", "years", (v) => String(v ?? "—")],
  ["Total return", "total_return_pct", (v) => pct(v)],
  ["CAGR", "cagr_pct", (v) => pct(v)],
  ["Sharpe", "sharpe", (v) => num(v)],
  ["Sortino", "sortino", (v) => num(v)],
  ["Max drawdown", "max_drawdown_pct", (v) => pct(v)],
  ["Trades", "trades", (v) => String(v ?? "—")],
  ["Win rate", "win_rate_pct", (v) => pct(v)],
  ["Profit factor", "profit_factor", (v) => num(v)],
  ["Avg R per trade", "avg_r", (v) => num(v)],
  ["Net P&L", "net_pnl", (v) => (v == null ? "—" : fmtUsd(Number(v), true))],
  ["Fees", "fees", (v) => (v == null ? "—" : fmtUsd(Number(v)))],
  ["Time in market", "exposure_pct", (v) => pct(v)],
];

function pct(v: unknown) {
  return v == null ? "—" : `${Number(v).toFixed(2)}%`;
}
function num(v: unknown) {
  if (v == null) return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(3) : String(v);
}

function MetricsTable({ title, m }: { title: string; m: Metrics }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        <dl className="text-sm">
          {METRIC_ROWS.map(([label, key, f]) => (
            <div key={key} className="flex justify-between border-t border-line py-1.5 first:border-t-0">
              <dt className="text-muted">{label}</dt>
              <dd className="num">{key === "start" ? `${m.start ?? "—"} → ${m.end ?? "—"}` : f(m[key])}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = Number.isInteger(Number(id)) ? await getValidationReport(Number(id)) : null;
  if (!r) notFound();
  const m = r.metrics;
  const start = Number(m.full.start_equity ?? 0);
  return (
    <>
      <PageHeader title={`Validation · ${r.strategy_id} v${r.version}`} subtitle={`Report #${r.id} · ${fmtTime(r.created_at)} · requested by ${r.requested_by}`}>
        <div className="flex flex-wrap items-center gap-2">
          {r.passed ? <Badge tone="gain">All gates passed</Badge> : <Badge tone="loss">{r.failed_gates.length} of {r.gates.length} gates failed</Badge>}
          {r.currently_valid_for_promotion ? <Badge tone="accent">Valid for promotion to PAPER</Badge> : null}
        </div>
      </PageHeader>
      <p className="mb-4 text-sm text-muted">
        <Link href="/strategy-lab" className="underline underline-offset-2 hover:text-fg">Strategy Lab</Link> · Simulated with
        the production strategy, sizing and risk-engine code, net of costs, on {r.symbols} symbols ({r.data_start} → {r.data_end}).
        Simulated results are not a prediction of future returns.
      </p>

      <Card className="mb-4">
        <CardHeader><CardTitle>Promotion gates</CardTitle><span className="text-[11px] text-muted">thresholds from policy.yaml</span></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
              <tr><th className="py-2 font-medium">Gate</th><th className="py-2 text-right font-medium">Value</th><th className="py-2 pl-6 font-medium">Required</th><th className="py-2 font-medium">Result</th></tr>
            </thead>
            <tbody>
              {r.gates.map((g) => (
                <tr key={g.name} className="border-t border-line">
                  <td className="py-2">{g.name.replace("_", " ")}{g.detail ? <span className="ml-2 text-xs text-muted">{g.detail}</span> : null}</td>
                  <td className="num py-2 text-right">{g.value == null ? "—" : String(g.value)}</td>
                  <td className="py-2 pl-6 text-muted">{g.threshold}</td>
                  <td className="py-2">{g.passed ? <Badge tone="gain">pass</Badge> : <Badge tone="loss">fail</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader><CardTitle>Simulated equity</CardTitle><span className="text-[11px] text-muted">starting capital {fmtUsd(start)} (policy budget)</span></CardHeader>
        <CardContent>
          <EquityChart points={r.equity_curve} start={start} />
          <details className="mt-3 text-xs text-muted">
            <summary className="cursor-pointer">Equity data table</summary>
            <div className="mt-2 max-h-64 overflow-auto">
              <table className="num w-full">
                <tbody>
                  {r.equity_curve.map(([d, v]) => (
                    <tr key={d} className="border-t border-line"><td className="py-1">{d}</td><td className="py-1 text-right">{fmtUsd(v)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </CardContent>
      </Card>

      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <MetricsTable title="Full period" m={m.full} />
        <MetricsTable title="Holdout (most recent years)" m={m.holdout} />
      </div>

      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Walk-forward windows</CardTitle></CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="num w-full min-w-[420px] text-sm">
              <thead className="text-left font-sans text-[11px] uppercase tracking-wider text-muted">
                <tr><th className="py-2 font-medium">Window</th><th className="py-2 text-right font-medium">Return</th><th className="py-2 text-right font-medium">Trades</th><th className="py-2 text-right font-medium">Max DD</th></tr>
              </thead>
              <tbody>
                {m.windows.map((w) => (
                  <tr key={String(w.start)} className="border-t border-line">
                    <td className="py-1.5">{String(w.start)} → {String(w.end)}</td>
                    <td className={`py-1.5 text-right ${Number(w.total_return_pct) > 0 ? "text-gain" : "text-loss"}`}>{pct(w.total_return_pct)}</td>
                    <td className="py-1.5 text-right">{String(w.trades)}</td>
                    <td className="py-1.5 text-right">{pct(w.max_drawdown_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Parameter stability</CardTitle><span className="text-[11px] text-muted">one parameter changed ±10%</span></CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="num w-full min-w-[360px] text-sm">
              <thead className="text-left font-sans text-[11px] uppercase tracking-wider text-muted">
                <tr><th className="py-2 font-medium">Change</th><th className="py-2 text-right font-medium">Net P&amp;L</th><th className="py-2 text-right font-medium">Sharpe</th><th className="py-2 text-right font-medium">Trades</th></tr>
              </thead>
              <tbody>
                {m.neighbors.map((n) => (
                  <tr key={n.change} className="border-t border-line">
                    <td className="py-1.5">{n.change}</td>
                    <td className={`py-1.5 text-right ${n.net_pnl > 0 ? "text-gain" : "text-loss"}`}>{fmtUsd(n.net_pnl, true)}</td>
                    <td className="py-1.5 text-right">{num(n.sharpe)}</td>
                    <td className="py-1.5 text-right">{n.trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Risk engine in the simulation</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-muted">{m.signals} signals · {m.unfilled} unfilled · {m.partial_fills} partial fills. Exits: {Object.entries(m.exit_reasons).map(([k, v]) => `${k.replace("_", " ")} ${v}`).join(", ") || "none"}.</p>
            {Object.keys(m.rejections).length === 0 ? <p className="text-muted">No entries were rejected.</p> : (
              <ul className="space-y-1">
                {Object.entries(m.rejections).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                  <li key={k} className="flex justify-between border-t border-line pt-1"><span>{checkLabel(k)}</span><span className="num text-muted">{v} · first {m.first_halt[k]}</span></li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Caveats</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-4 text-sm text-muted">
              {r.caveats.map((c) => <li key={c}><span className="text-fg">{c.split(":")[0].replaceAll("_", " ")}</span>{c.includes(":") ? `: ${c.split(":").slice(1).join(":")}` : ""}</li>)}
            </ul>
            <p className="mt-3 text-xs text-muted">Costs per fill: half-spread {Number(m.cost_model.half_spread) * 1e4} bps, slippage {Number(m.cost_model.slippage) * 1e4} bps, stop slippage {Number(m.cost_model.stop_slippage) * 1e4} bps, plus SEC/FINRA fees on sells.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
