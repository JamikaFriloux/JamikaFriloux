"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

export function RunAgentsButton() {
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function run() {
    setPending(true);
    setMessage(null);
    const res = await fetch("/api/intelligence/run", { method: "POST" }).catch(() => null);
    const data = res ? await res.json().catch(() => ({})) : {};
    setPending(false);
    setMessage(
      res?.ok
        ? { ok: true, text: "Queued. Refresh in a minute to see new reports." }
        : { ok: false, text: typeof data.detail === "string" ? data.detail : data.error ?? "Request failed" },
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="outline" size="sm" disabled={pending} onClick={run}>
        Run agents now
      </Button>
      {message ? (
        <span className={`text-xs ${message.ok ? "text-muted" : "text-loss"}`} role="status">
          {message.text}
        </span>
      ) : null}
    </div>
  );
}
