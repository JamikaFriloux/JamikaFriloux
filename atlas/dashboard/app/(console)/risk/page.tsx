import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { KillSwitchControl } from "@/components/kill-switch-control";
import { PageHeader } from "@/components/page-header";
import { ReferenceCard } from "@/components/risk/reference-card";
import { getMe, getReference, getRiskDecisions, getStatus } from "@/lib/api";
import { checkLabel } from "@/components/trading/labels";
import { fmtTime, fmtUsd } from "@/lib/utils";

const LIMIT_LABELS: Record<string, [string, string]> = {
  max_risk_per_trade_pct: ["Max risk per trade", "% of equity"],
  max_daily_loss_pct: ["Max daily loss", "% of starting-day equity"],
  max_drawdown_pct: ["Max drawdown", "% from high-water mark"],
  drawdown_cooldown_sessions: ["Drawdown halt cooldown", "sessions, then HWM resets"],
  max_position_allocation_pct: ["Max position allocation", "% of equity"],
  max_concurrent_positions: ["Max concurrent positions", "positions"],
  max_sector_exposure_pct: ["Max sector exposure", "% of equity"],
  max_gross_exposure_pct: ["Max gross exposure", "% of equity"],
  max_new_trades_per_day: ["Max new trades per day", "trades"],
  max_order_notional_usd: ["Max order notional", "USD"],
  min_cash_buffer_usd: ["Min cash buffer", "USD"],
};

export default async function RiskPage() {
  const [s, me, rejections, reference] = await Promise.all([getStatus(), getMe(), getRiskDecisions(true, 12), getReference()]);
  const ks = s.kill_switch;
  const a = s.account;
  const limits = s.policy.limits;

  let dailyUse: number | null = null;
  let grossUse: number | null = null;
  if (a) {
    const equity = Number(a.equity);
    const dayStart = equity - Number(a.day_pl);
    const allowedLoss = (dayStart * limits.max_daily_loss_pct) / 100;
    dailyUse = allowedLoss > 0 ? Math.max(0, -Number(a.day_pl)) / allowedLoss : null;
    grossUse = equity > 0 ? Number(a.long_market_value) / ((equity * limits.max_gross_exposure_pct) / 100) : null;
  }

  return (
    <>
      <PageHeader title="Risk Center" subtitle="Deterministic limits enforced by the risk engine. Agents cannot modify them." />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className={ks.engaged ? "border-loss/40" : ""}>
          <CardHeader>
            <CardTitle>Kill switch</CardTitle>
            {ks.engaged ? <Badge tone="loss">ENGAGED</Badge> : <Badge tone="gain">ARMED · trading allowed</Badge>}
          </CardHeader>
          <CardContent className="space-y-4">
            {ks.engaged ? (
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between gap-4"><dt className="text-muted">Reason</dt><dd className="text-right">{ks.reason}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-muted">By</dt><dd>{ks.engaged_by}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-muted">At</dt><dd>{fmtTime(ks.engaged_at)}</dd></div>
              </dl>
            ) : (
              <p className="text-sm text-muted">Last resumed by {ks.resumed_by ?? "—"} at {fmtTime(ks.resumed_at)}.</p>
            )}
            <KillSwitchControl engaged={ks.engaged} role={me.role} />
            <p className="text-xs text-muted">Engaging cancels open orders and reconciles state. Positions are not liquidated.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Utilization</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            <Meter label="Daily loss limit" value={dailyUse} />
            <Meter label="Gross exposure limit" value={grossUse} />
            <Meter
              label="Drawdown limit"
              value={s.drawdown && Number(s.drawdown.limit) > 0 ? Number(s.drawdown.drawdown) / Number(s.drawdown.limit) : null}
            />
            {s.drawdown?.cooldown_sessions_remaining ? (
              <Badge tone="loss">
                Drawdown halt since {s.drawdown.halted_on}: new entries blocked for {s.drawdown.cooldown_sessions_remaining} more
                sessions
              </Badge>
            ) : null}
            <p className="text-xs text-muted">
              {a ? `Based on broker sync at ${fmtTime(a.as_of)}.` : "Unavailable until the first broker sync."}{" "}
              {s.drawdown ? `High-water mark ${fmtUsd(s.drawdown.high_water_mark)}, limit ${fmtUsd(s.drawdown.limit)}. ` : ""}The risk engine
              sizes and limits against a capital base of min(broker equity, policy starting equity). Exposure is also
              capped per sector bucket (see Reference data below); unclassified symbols share one bucket.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Risk rejections</CardTitle>
            <span className="text-[11px] text-muted">latest {rejections.length}</span>
          </CardHeader>
          <CardContent>
            {rejections.length === 0 ? (
              <p className="text-sm text-muted">No rejections recorded. Signals are evaluated during the session after they are generated.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {rejections.map((d) => (
                  <li key={d.id} className="border-t border-line pt-2 first:border-t-0 first:pt-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span>
                        <span className="font-medium">{d.symbol}</span> <span className="text-muted">{d.kind} · {d.strategy_id}</span>
                        {d.mode === "shadow" ? <Badge tone="neutral" className="ml-2">shadow</Badge> : null}
                      </span>
                      <span className="text-[11px] text-muted">{fmtTime(d.ts)}</span>
                    </div>
                    <div className="text-xs text-loss">{d.failed.map(checkLabel).join(", ")}</div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Active policy</CardTitle>
          <span className="num text-[11px] text-muted">v{s.policy.version} · sha256 {s.policy.sha256.slice(0, 12)}…</span>
        </CardHeader>
        <CardContent>
          <div className="grid gap-x-8 sm:grid-cols-2">
            {Object.entries(limits).map(([k, v]) => {
              const [label, unit] = LIMIT_LABELS[k] ?? [k, ""];
              return (
                <div key={k} className="flex items-baseline justify-between border-t border-line py-2 text-sm">
                  <span className="text-muted">{label}</span>
                  <span className="num">{unit === "USD" ? fmtUsd(v) : v}<span className="ml-1 font-sans text-xs text-muted">{unit !== "USD" ? unit : ""}</span></span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
      <ReferenceCard r={reference} />
    </>
  );
}

function Meter({ label, value }: { label: string; value: number | null }) {
  const pct = value === null ? null : Math.min(100, Math.max(0, value * 100));
  const tone = pct === null ? "bg-line" : pct >= 80 ? "bg-loss" : pct >= 50 ? "bg-warn" : "bg-gain";
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="num">{pct === null ? "—" : `${pct.toFixed(1)}%`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-panel-2">
        <div className={`h-full ${tone}`} style={{ width: `${pct ?? 0}%` }} />
      </div>
    </div>
  );
}
