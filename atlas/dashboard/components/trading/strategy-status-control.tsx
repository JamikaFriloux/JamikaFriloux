"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const TARGETS: Record<string, string[]> = {
  RESEARCH: ["PAPER", "RETIRED"],
  PAPER: ["RESEARCH", "LIVE_CANDIDATE", "RETIRED"],
  LIVE_CANDIDATE: ["PAPER", "RESEARCH", "RETIRED"],
  RETIRED: ["RESEARCH"],
};

export function StrategyStatusControl({ id, status }: { id: string; status: string }) {
  const router = useRouter();
  const targets = TARGETS[status] ?? [];
  const [target, setTarget] = useState(targets[0] ?? "");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/strategies/${encodeURIComponent(id)}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: target, reason, password }),
    }).catch(() => null);
    const data = res ? await res.json().catch(() => ({})) : {};
    setPending(false);
    setPassword("");
    if (!res || !res.ok) {
      setMessage({ ok: false, text: typeof data.detail === "string" ? data.detail : data.error ?? "Request failed" });
      return;
    }
    setReason("");
    setMessage({ ok: true, text: `Now ${data.status}` });
    router.refresh();
  }

  return (
    <div className="space-y-2 border-t border-line pt-3">
      <div className="flex gap-2">
        <select
          className="h-9 rounded-lg border border-line bg-panel-2 px-2 text-sm"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          aria-label={`New status for ${id}`}
        >
          {targets.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <Input className="h-9" placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <div className="flex gap-2">
        <Input className="h-9" type="password" placeholder="Re-enter your password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button variant="outline" className="shrink-0 whitespace-nowrap" disabled={pending || reason.trim().length < 3 || !password} onClick={submit}>
          Change status
        </Button>
      </div>
      {message ? <p className={`text-xs ${message.ok ? "text-gain" : "text-loss"}`} role="alert">{message.text}</p> : null}
    </div>
  );
}
