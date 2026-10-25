"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
    });
    setPending(false);
    if (res.ok) {
      router.replace("/");
      router.refresh();
    } else {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "Sign-in failed");
    }
  }

  return (
    <main className="grid min-h-[calc(100vh-29px)] place-items-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-xl bg-fg text-lg font-bold text-bg">A</div>
          <h1 className="text-lg font-semibold tracking-[0.2em]">ATLAS</h1>
          <p className="mt-1 text-sm text-muted">Autonomous Trading &amp; Learning Analysis System</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-3 rounded-xl border border-line bg-panel p-6">
          <label className="block text-xs text-muted">
            Username
            <Input name="username" autoComplete="username" required className="mt-1.5" />
          </label>
          <label className="block text-xs text-muted">
            Password
            <Input name="password" type="password" autoComplete="current-password" required className="mt-1.5" />
          </label>
          {error ? <p className="text-sm text-loss">{error}</p> : null}
          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-xs text-muted">
          Accounts are created by an administrator with <code className="num">atlas.scripts.create_user</code>.
        </p>
      </div>
    </main>
  );
}
