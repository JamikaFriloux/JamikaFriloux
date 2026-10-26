"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

export function ValidateButton({ id }: { id: string }) {
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function run() {
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/strategies/${encodeURIComponent(id)}/validate`, { method: "POST" }).catch(() => null);
    const data = res ? await res.json().catch(() => ({})) : {};
    setPending(false);
    setMessage(
      res?.ok
        ? { ok: true, text: "Queued. A full validation takes several minutes; refresh to see the report." }
        : { ok: false, text: typeof data.detail === "string" ? data.detail : data.error ?? "Request failed" },
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="outline" size="sm" disabled={pending} onClick={run}>
        Run validation
      </Button>
      {message ? <span className={`text-xs ${message.ok ? "text-muted" : "text-loss"}`} role="status">{message.text}</span> : null}
    </div>
  );
}
