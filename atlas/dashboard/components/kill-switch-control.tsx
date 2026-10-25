"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function KillSwitchControl({ engaged, role }: { engaged: boolean; role: string }) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const canEngage = role === "operator" || role === "admin";
  const canResume = role === "admin";

  async function act(action: "engage" | "resume") {
    if (action === "engage" && !confirm("Engage the kill switch? New paper orders will be disabled and open orders cancelled.")) return;
    setPending(true);
    setMessage(null);
    const res = await fetch("/api/kill-switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, reason, password }),
    });
    const data = await res.json().catch(() => ({}));
    setPending(false);
    setPassword("");
    if (!res.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : data.error ?? `Request failed (${res.status})`);
      return;
    }
    setReason("");
    router.refresh();
  }

  if (!engaged) {
    return (
      <div className="space-y-3">
        <Input placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button variant="danger" className="w-full" disabled={!canEngage || pending || reason.trim().length < 3} onClick={() => act("engage")}>
          Engage kill switch
        </Button>
        {!canEngage ? <p className="text-xs text-muted">Operator role required.</p> : null}
        {message ? <p className="text-xs text-loss">{message}</p> : null}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Input placeholder="Reason for resuming (required)" value={reason} onChange={(e) => setReason(e.target.value)} disabled={!canResume} />
      <Input type="password" placeholder="Re-enter your password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={!canResume} autoComplete="current-password" />
      <Button variant="outline" className="w-full" disabled={!canResume || pending || reason.trim().length < 3 || !password} onClick={() => act("resume")}>
        Authorize resume
      </Button>
      <p className="text-xs text-muted">
        {canResume ? "Resuming requires admin re-authentication and is recorded in the audit log." : "Admin role required to resume."}
      </p>
      {message ? <p className="text-xs text-loss">{message}</p> : null}
    </div>
  );
}
