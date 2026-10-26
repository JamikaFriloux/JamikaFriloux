"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtUsd } from "@/lib/utils";

/** Single-series equity curve: 2px line, recessive axes, crosshair tooltip, no legend. */
export function EquityChart({ points, start }: { points: [string, number][]; start: number }) {
  const data = points.map(([d, v]) => ({ d, v }));
  return (
    <div className="h-64 w-full" role="img" aria-label="Simulated account equity over the backtest">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="var(--color-line)" strokeDasharray="0" vertical={false} />
          <XAxis dataKey="d" tick={{ fill: "var(--color-muted)", fontSize: 11 }} tickLine={false}
            axisLine={{ stroke: "var(--color-line)" }} minTickGap={48} tickFormatter={(d: string) => d.slice(0, 7)} />
          <YAxis tick={{ fill: "var(--color-muted)", fontSize: 11 }} tickLine={false} axisLine={false} width={64}
            domain={["auto", "auto"]} tickFormatter={(v: number) => `$${Math.round(v).toLocaleString("en-US")}`} />
          <ReferenceLine y={start} stroke="var(--color-muted)" strokeDasharray="4 4"
            label={{ value: "start", fill: "var(--color-muted)", fontSize: 11, position: "insideTopLeft" }} />
          <Tooltip
            cursor={{ stroke: "var(--color-muted)", strokeWidth: 1 }}
            contentStyle={{ background: "var(--color-panel-2)", border: "1px solid var(--color-line)", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "var(--color-muted)" }}
            itemStyle={{ color: "var(--color-fg)" }}
            formatter={(v) => [fmtUsd(Number(v)), "Equity"]}
          />
          <Line type="monotone" dataKey="v" stroke="var(--color-accent)" strokeWidth={2} dot={false}
            activeDot={{ r: 4, stroke: "var(--color-panel)", strokeWidth: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
