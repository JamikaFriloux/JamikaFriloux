import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { SignalsTable } from "@/components/trading/signals-table";
import { STATUS_TONE } from "@/components/trading/labels";
import { StrategyStatusControl } from "@/components/trading/strategy-status-control";
import { getMe, getSignals, getStrategies } from "@/lib/api";
import { fmtTime } from "@/lib/utils";

export default async function StrategyLabPage() {
  const [strategies, signals, me] = await Promise.all([getStrategies(), getSignals(30), getMe()]);
  return (
    <>
      <PageHeader title="Strategy Lab" subtitle="Deterministic strategies, their lifecycle status and the signals they produce" />
      <p className="mb-4 max-w-3xl text-sm text-muted">
        Every strategy is a hypothesis under test. In <span className="text-fg">RESEARCH</span> its signals are risk-checked in
        shadow and never ordered. Promotion to <span className="text-fg">PAPER</span> requires a passing validation report for the
        exact version (walk-forward, out-of-sample, cost-aware backtests, built in Phase 4), so it is refused until then. A code
        change puts a strategy back in RESEARCH.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
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
