import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { SignalsTable } from "@/components/trading/signals-table";
import { STATUS_TONE } from "@/components/trading/labels";
import { StrategyStatusControl } from "@/components/trading/strategy-status-control";
import Link from "next/link";
import { ValidateButton } from "@/components/trading/validate-button";
import { getMe, getSignals, getStrategies, getValidationReports, type ValidationSummary } from "@/lib/api";
import { fmtTime } from "@/lib/utils";

export default async function StrategyLabPage() {
  const [strategies, signals, me, reports] = await Promise.all([
    getStrategies(),
    getSignals(30),
    getMe(),
    getValidationReports(undefined, 50),
  ]);
  const latest = new Map<string, ValidationSummary>();
  for (const r of reports) if (!latest.has(r.strategy_id)) latest.set(r.strategy_id, r);
  return (
    <>
      <PageHeader title="Strategy Lab" subtitle="Deterministic strategies, their lifecycle status and the signals they produce" />
      <p className="mb-4 max-w-3xl text-sm text-muted">
        Every strategy is a hypothesis under test. In <span className="text-fg">RESEARCH</span> its signals are risk-checked in
        shadow and never ordered. Promotion to <span className="text-fg">PAPER</span> requires a passing validation report for the
        exact version and parameters, made under the current policy within the last 90 days. A validation backtests the
        strategy with the production risk engine and costs, then checks the promotion gates in policy.yaml. A code change
        puts a strategy back in RESEARCH.
      </p>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {strategies.map((s) => (
          <Card key={s.id}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <CardTitle className="text-sm normal-case tracking-normal text-fg">{s.id}</CardTitle>
                <span className="num text-[11px] text-muted">v{s.version}</span>
              </div>
              <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">{s.description ?? "Not in the current code (retired)."}</p>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                {Object.entries(s.params).map(([k, v]) => (
                  <div key={k} className="flex justify-between border-t border-line py-1">
                    <dt className="text-muted">{k}</dt>
                    <dd className="num">{String(v)}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-xs text-muted">
                Needs {s.lookback_sessions ?? "—"} sessions of history · {s.signals} signals · last change by {s.updated_by}{" "}
                {fmtTime(s.updated_at)}
              </p>
              <ValidationBlock report={latest.get(s.id)} />
              {me.role === "admin" ? <ValidateButton id={s.id} /> : null}
              {me.role === "admin" ? (
                <StrategyStatusControl id={s.id} status={s.status} />
              ) : (
                <p className="text-xs text-muted">Admin role required to change status.</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="mt-4">
        <SignalsTable signals={signals} />
      </div>
    </>
  );
}

function ValidationBlock({ report }: { report: ValidationSummary | undefined }) {
  if (!report) {
    return <p className="border-t border-line pt-3 text-xs text-muted">Not validated yet.</p>;
  }
  const h = report.headline;
  return (
    <div className="space-y-1.5 border-t border-line pt-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted">Latest validation</span>
        {report.passed ? <Badge tone="gain">passed</Badge> : <Badge tone="loss">failed</Badge>}
        {report.currently_valid_for_promotion ? <Badge tone="accent">promotable</Badge> : null}
        <Link href={`/strategy-lab/reports/${report.id}`} className="ml-auto text-accent underline-offset-2 hover:underline">
          Report #{report.id} →
        </Link>
      </div>
      <p className="num text-muted">
        {report.data_start} → {report.data_end} · {String(h.trades ?? "—")} trades · Sharpe {String(h.sharpe ?? "—")} · CAGR{" "}
        {h.cagr_pct == null ? "—" : `${h.cagr_pct}%`} · max DD {String(h.max_drawdown_pct ?? "—")}%
      </p>
      {report.failed_gates.length ? <p className="text-loss">Failed: {report.failed_gates.join(", ")}</p> : null}
    </div>
  );
}
