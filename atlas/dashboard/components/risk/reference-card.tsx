import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReferenceData } from "@/lib/api";
import { fmtTime, fmtUsd } from "@/lib/utils";

const CLEARANCE: Record<string, { tone: "gain" | "loss" | "warn" | "neutral"; label: string }> = {
  clear: { tone: "gain", label: "clear" },
  blackout: { tone: "loss", label: "earnings blackout" },
  unknown: { tone: "warn", label: "no clearance" },
  disabled: { tone: "neutral", label: "check disabled" },
};

/** Instrument classification and earnings clearance for every watched symbol. */
export function ReferenceCard({ r }: { r: ReferenceData }) {
  const counts = r.watched.reduce<Record<string, number>>((acc, w) => ((acc[w.earnings] = (acc[w.earnings] ?? 0) + 1), acc), {});
  const cov = r.latest_coverage;
  const bySector = new Map<string, string[]>();
  for (const w of r.watched) bySector.set(w.sector, [...(bySector.get(w.sector) ?? []), w.symbol]);
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Reference data: earnings and sectors</CardTitle>
        <span className="flex flex-wrap gap-2">
          {Object.entries(counts).map(([k, n]) => (
            <Badge key={k} tone={CLEARANCE[k]?.tone ?? "neutral"}>
              {n} {CLEARANCE[k]?.label ?? k}
            </Badge>
          ))}
        </span>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-xs text-muted">
          Entries are blocked for {r.blackout_days} sessions before earnings (span now: {r.blackout_span.join(", ") || "—"}).
          ETFs never report earnings. A stock is cleared only by an earnings calendar fetched within the last{" "}
          {r.earnings_max_age_hours} h that covers the span; otherwise its entries are rejected.{" "}
          {cov ? (
            <>
              Latest calendar: {cov.source}, {fmtTime(cov.fetched_at)}, {cov.window_start} → {cov.window_end}, {cov.events} reports.
            </>
          ) : (
            <span className="text-warn">No earnings calendar has been fetched: every stock entry is rejected.</span>
          )}
        </p>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Sector buckets (watched symbols)</div>
            <ul className="space-y-1">
              {[...bySector.entries()].map(([sector, syms]) => (
                <li key={sector} className="flex flex-wrap items-baseline justify-between gap-2 border-t border-line pt-1">
                  <span className={sector === "unknown" ? "text-warn" : ""}>{sector.replace(/_/g, " ")}</span>
                  <span className="num text-right text-xs text-muted">
                    {syms.join(" ")}
                    {r.sector_exposure[sector] ? ` · held ${fmtUsd(r.sector_exposure[sector])}` : ""}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[11px] text-muted">
              Each bucket is capped at {r.max_sector_exposure_pct}% of the capital base; unclassified symbols share the unknown bucket.
            </p>
          </div>
          <div>
            <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Earnings clearance</div>
            <div className="flex flex-wrap gap-1.5">
              {r.watched.map((w) => (
                <Badge key={w.symbol} tone={CLEARANCE[w.earnings]?.tone ?? "neutral"} title={`${w.asset_type ?? "unclassified"} · ${w.source ?? "no source"}`}>
                  {w.symbol}
                  {w.asset_type === "etf" ? " · ETF" : ""}
                </Badge>
              ))}
            </div>
            {r.upcoming_earnings.length ? (
              <ul className="mt-3 space-y-0.5 text-xs">
                {r.upcoming_earnings.map((e) => (
                  <li key={`${e.symbol}-${e.day}`} className="num">
                    {e.day} {e.symbol} ({e.timing})
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-xs text-muted">No upcoming reports stored for watched symbols.</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
