import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SignalRow } from "@/lib/api";
import { fmtUsd } from "@/lib/utils";
import { checkLabel, STATUS_TONE } from "./labels";

export function SignalsTable({ signals }: { signals: SignalRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Strategy signals</CardTitle>
        <span className="text-[11px] text-muted">From each session&apos;s close · acted on the next session</span>
      </CardHeader>
      <CardContent>
        {signals.length === 0 ? (
          <p className="text-sm text-muted">No signals yet. Strategies run after each close on benchmarks and watchlist symbols in the universe.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="py-2 font-medium">Session</th>
                  <th className="py-2 font-medium">Strategy</th>
                  <th className="py-2 font-medium">Signal</th>
                  <th className="py-2 text-right font-medium">Close</th>
                  <th className="py-2 text-right font-medium">Stop</th>
                  <th className="py-2 font-medium pl-4">Status</th>
                  <th className="py-2 font-medium">Risk decision</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => (
                  <tr key={s.id} className="border-t border-line align-top">
                    <td className="num py-2 text-muted">{s.as_of}</td>
                    <td className="py-2">{s.strategy_id}</td>
                    <td className="py-2">
                      <span className="font-medium">{s.symbol}</span>{" "}
                      <span className={s.kind === "entry" ? "text-gain" : "text-loss"}>{s.kind === "entry" ? "buy" : "sell"}</span>
                    </td>
                    <td className="num py-2 text-right">{fmtUsd(s.ref_price)}</td>
                    <td className="num py-2 text-right">{s.stop_price ? fmtUsd(s.stop_price) : "—"}</td>
                    <td className="py-2 pl-4">
                      <div className="flex flex-wrap gap-1">
                        <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
                        {s.mode === "shadow" ? <Badge tone="neutral">shadow</Badge> : null}
                      </div>
                    </td>
                    <td className="py-2 text-xs">
                      {!s.decision ? (
                        <span className="text-muted">pending</span>
                      ) : s.decision.approved ? (
                        <span className="text-gain">
                          {s.mode === "shadow" ? "would pass" : "approved"}
                          {s.decision.qty ? ` · ${s.decision.qty} @ ${fmtUsd(s.decision.limit_price)}` : ""}
                        </span>
                      ) : (
                        <span className="text-loss">{s.decision.failed.map(checkLabel).join(", ")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
