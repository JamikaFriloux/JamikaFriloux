"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

// Validated pair (dataviz validator, dark surface #111317): blue = account, orange = benchmark.
const SERIES = [
  { key: "a", color: "#3987e5" },
  { key: "b", color: "#d95926" },
] as const;

/** Two series indexed to 100 at the first common session: one axis, legend, crosshair tooltip. */
export function ComparisonChart({
  a,
  b,
  labels,
}: {
  a: [string, number][];
  b: [string, number][];
  labels: [string, string];
}) {
  const bByDay = new Map(b);
  const days = a.filter(([d]) => bByDay.has(d)).map(([d]) => d);
  const aByDay = new Map(a);
  const a0 = days.length ? aByDay.get(days[0])! : 1;
  const b0 = days.length ? bByDay.get(days[0])! : 1;
  const data = days.map((d) => ({ d, a: (aByDay.get(d)! / a0) * 100, b: (bByDay.get(d)! / b0) * 100 }));
  const last = data[data.length - 1];
  return (
    <figure className="space-y-2">
      <figcaption className="flex flex-wrap items-center gap-4 text-xs text-muted">
        {SERIES.map((s, i) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} aria-hidden />
            <span className="text-fg">{labels[i]}</span>
            {last ? <span className="num">{last[s.key].toFixed(1)}</span> : null}
          </span>
        ))}
        <span>indexed to 100 on {days[0] ?? "—"}</span>
      </figcaption>
      <div className="h-56 w-full" role="img" aria-label={`${labels[0]} versus ${labels[1]}, indexed to 100`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="d" tick={{ fill: "var(--color-muted)", fontSize: 11 }} tickLine={false}
              axisLine={{ stroke: "var(--color-line)" }} minTickGap={48} tickFormatter={(d: string) => d.slice(5)} />
            <YAxis tick={{ fill: "var(--color-muted)", fontSize: 11 }} tickLine={false} axisLine={false} width={44}
              domain={["auto", "auto"]} tickFormatter={(v: number) => v.toFixed(0)} />
            <ReferenceLine y={100} stroke="var(--color-muted)" strokeDasharray="4 4" />
            <Tooltip
              cursor={{ stroke: "var(--color-muted)", strokeWidth: 1 }}
              contentStyle={{ background: "var(--color-panel-2)", border: "1px solid var(--color-line)", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "var(--color-muted)" }}
              itemStyle={{ color: "var(--color-fg)" }}
              formatter={(v, name) => [Number(v).toFixed(2), name === "a" ? labels[0] : labels[1]]}
            />
            {SERIES.map((s) => (
              <Line key={s.key} type="monotone" dataKey={s.key} stroke={s.color} strokeWidth={2} dot={false}
                activeDot={{ r: 4, stroke: "var(--color-panel)", strokeWidth: 2 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
