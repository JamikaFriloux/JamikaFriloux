import { cn } from "@/lib/utils";

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "gain" | "loss" | "neutral";
}) {
  return (
    <div className="rounded-xl border border-line bg-panel px-5 py-4">
      <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted">{label}</div>
      <div
        className={cn(
          "num mt-2 text-2xl font-semibold tracking-tight",
          tone === "gain" && "text-gain",
          tone === "loss" && "text-loss",
        )}
      >
        {value}
      </div>
      {sub ? <div className="mt-1 text-xs text-muted">{sub}</div> : null}
    </div>
  );
}

export function plTone(v: string | null | undefined): "gain" | "loss" | "neutral" {
  const n = Number(v);
  if (!v || !Number.isFinite(n) || n === 0) return "neutral";
  return n > 0 ? "gain" : "loss";
}
