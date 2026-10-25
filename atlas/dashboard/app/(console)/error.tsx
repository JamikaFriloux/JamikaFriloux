"use client";

import { Button } from "@/components/ui/button";

export default function ConsoleError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-lg rounded-xl border border-loss/30 bg-loss/5 p-6">
      <h2 className="text-sm font-semibold text-loss">ATLAS API unavailable</h2>
      <p className="mt-2 text-sm text-muted">
        The dashboard could not load live data. No values are shown rather than stale or invented
        ones. {error.message}
      </p>
      <Button variant="outline" size="sm" className="mt-4" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
