import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/stat";
import { ComparisonChart } from "@/components/performance/comparison-chart";
import { STATUS_TONE } from "@/components/trading/labels";
import { getPerformance, type Performance, type TrackRecordSummary } from "@/lib/api";
import { fmtTime, fmtUsd } from "@/lib/utils";

type Strat = Performance["strategies"][number];

const num = (v: unknown, d = 2) =>
  typeof v === "number" ? v.toFixed(d) : v === "inf" ? "∞" : v == null ? "—" : String(v);
const pct = (v: unknown) => (typeof v === "number" ? `${v > 0 ? "+" : ""}${v.toFixed(2)}%` : "—");
const tone = (v: unknown) => (typeof v === "number" ? (v > 0 ? "gain" : v < 0 ? "loss" : "neutral") : "neutral");

export default async function PerformancePage() {
  const p = await getPerformance();
  return (
    <>
      <PageHeader title="Performance" subtitle="Paper account versus SPY, and each strategy's backtest, forward test and paper record" />
      <p className="mb-4 max-w-3xl text-sm text-muted">
        Paper results are simulated fills on a paper account, not evidence of future returns. The forward test reruns the
        validation simulator only on sessions after the validation data ended, so it is out of sample. The paper record
        counts only the strategy&apos;s own filled orders since its promotion to PAPER and decides promotion to
        LIVE_CANDIDATE. Nothing in this deployment can place a live order.
      </p>
      <AccountSection account={p.account} />
      <div className="mt-6 space-y-4">
        {p.strategies.map((s) => (
          <StrategyCard key={s.id} s={s} />
        ))}
      </div>
      <GatesNote gates={p.track_record_gates} />
    </>
  );
}

function AccountSection({ account }: { account: Performance["account"] }) {
  const m = account.metrics;
  const c = account.comparison;
  if (!m) {
    return (
      <EmptyState title="No account history yet">
        ATLAS records the paper account&apos;s equity at each session close during broker sync; {account.sessions} recorded so
        far. Metrics and the SPY comparison appear after two sessions. Nothing is estimated in the meantime.
      </EmptyState>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Paper account</CardTitle>
        <span className="text-xs text-muted">
          {m.start} → {m.end} · {account.sessions} sessions
        </span>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Return" value={pct(m.total_return_pct)} tone={tone(m.total_return_pct)} sub={`${fmtUsd(String(m.start_equity))} → ${fmtUsd(String(m.end_equity))}`} />
          <Stat label={`vs ${account.benchmark}`} value={c ? pct(c.excess_return_pct) : "—"} tone={c ? tone(c.excess_return_pct) : "neutral"} sub={c ? `${account.benchmark} ${pct(c.benchmark_return_pct)}` : "no benchmark bars for these sessions"} />
          <Stat label="Sharpe / Sortino" value={`${num(m.sharpe)} / ${num(m.sortino)}`} sub="annualised, daily returns" />
          <Stat label="Max drawdown" value={`${num(m.max_drawdown_pct)}%`} sub={c ? `${account.benchmark} ${num(c.benchmark_max_drawdown_pct)}% · β ${num(c.beta)} · ρ ${num(c.correlation)}` : undefined} />
        </div>
        {account.benchmark_curve && account.benchmark_curve.length >= 2 ? (
          <ComparisonChart a={account.curve} b={account.benchmark_curve} labels={["Paper account", account.benchmark]} />
        ) : null}
        <p className="text-[11px] text-muted">
          Whole paper account, including cash ATLAS doesn&apos;t size against. Deposits and resets aren&apos;t tracked and would show as returns.
        </p>
      </CardContent>
    </Card>
  );
}

const ROWS: [string, (r: Col) => string][] = [
  ["Span", (r) => r.span],
  ["Trades", (r) => num(r.m?.trades, 0)],
  ["Win rate", (r) => (typeof r.m?.win_rate_pct === "number" ? `${r.m.win_rate_pct.toFixed(1)}%` : "—")],
  ["Profit factor", (r) => num(r.m?.profit_factor)],
  ["Avg R", (r) => num(r.m?.avg_r)],
  ["Avg return / trade", (r) => pct(r.m?.avg_return_pct)],
  ["Sharpe", (r) => num(r.m?.sharpe)],
  ["Max drawdown", (r) => (typeof r.m?.max_drawdown_pct === "number" ? `${r.m.max_drawdown_pct.toFixed(2)}%` : "—")],
  ["Net P&L", (r) => (typeof r.m?.net_pnl === "number" ? fmtUsd(r.m.net_pnl, true) : "—")],
];

type Col = { title: string; sub: string; span: string; m: Record<string, unknown> | null };

function col(title: string, rec: TrackRecordSummary | null, empty: string): Col {
  if (!rec) return { title, sub: empty, span: "—", m: null };
  const span = rec.sessions ? `${rec.start} → ${rec.as_of} (${rec.sessions} sessions)` : "—";
  return { title, sub: rec.note ?? `updated ${fmtTime(rec.created_at)}`, span, m: rec.sessions || rec.trade_count ? rec.metrics : null };
}

function StrategyCard({ s }: { s: Strat }) {
  const ref = s.backtest;
  const cols: Col[] = [
    {
      title: "Backtest",
      sub: ref ? `validation report #${ref.report_id} (${ref.passed ? "passed" : "failed"}), in-sample and holdout` : "not validated",
      span: ref ? `${ref.data_start} → ${ref.data_end}` : "—",
      m: ref,
    },
    col("Forward test (simulated)", s.forward_sim, "not computed yet"),
    col("Paper record", s.paper, s.status === "PAPER" || s.status === "LIVE_CANDIDATE" ? "not computed yet" : `not in PAPER (${s.status})`),
  ];
  const gates = s.paper?.gates ?? [];
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm normal-case tracking-normal text-fg">{s.id}</CardTitle>
          <span className="num text-[11px] text-muted">v{s.version}</span>
        </div>
        <span className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
          {s.live_candidate_record ? <Badge tone="accent">LIVE_CANDIDATE gates passed</Badge> : null}
        </span>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="py-2 font-medium" />
                {cols.map((c) => (
                  <th key={c.title} className="py-2 text-right font-medium">
                    {c.title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="num">
              {ROWS.map(([label, f]) => (
                <tr key={label} className="border-t border-line">
                  <td className="py-1.5 font-sans text-muted">{label}</td>
                  {cols.map((c) => (
                    <td key={c.title} className="py-1.5 text-right">
                      {c.m || label === "Span" ? f(c) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="space-y-0.5 text-xs text-muted">
          {cols.map((c) => (
            <li key={c.title}>
              <span className="text-fg">{c.title}:</span> {c.sub}
              {c.title === "Backtest" && ref ? (
                <>
                  {" "}
                  <Link href={`/strategy-lab/reports/${ref.report_id}`} className="text-accent hover:underline">
                    open report
                  </Link>
                </>
              ) : null}
            </li>
          ))}
        </ul>
        {s.forward_sim && s.forward_sim.open_positions.length ? (
          <p className="text-xs text-muted">
            Simulated open positions:{" "}
            {s.forward_sim.open_positions.map((o) => `${o.symbol} ${o.qty} @ ${o.entry_price} (${fmtUsd(o.unrealized_pnl, true)})`).join(", ")}
          </p>
        ) : null}
        {gates.length ? (
          <div className="border-t border-line pt-3">
            <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">LIVE_CANDIDATE gates (paper record)</div>
            <ul className="grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
              {gates.map((g) => (
                <li key={g.name} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <Badge tone={g.passed ? "gain" : "loss"}>{g.passed ? "pass" : "fail"}</Badge>
                    {g.name.replace(/_/g, " ")}
                  </span>
                  <span className="num text-muted">
                    {g.value == null ? "—" : num(g.value)} {g.threshold}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function GatesNote({ gates }: { gates: Record<string, number> }) {
  return (
    <p className="mt-6 text-xs text-muted">
      LIVE_CANDIDATE gates (policy.yaml): at least {gates.min_paper_sessions} sessions and {gates.min_paper_trades} closed paper
      trades since promotion, profit factor ≥ {gates.min_profit_factor}, drawdown ≤ {gates.max_drawdown_pct}% of budget, average R
      ≥ {gates.min_expectancy_vs_backtest}× the backtest&apos;s, evaluated within {gates.record_max_age_days} days. Promotion stays an
      admin decision; LIVE_CANDIDATE keeps paper trading.
    </p>
  );
}
