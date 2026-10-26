"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BrainCircuit,
  FlaskConical,
  Gauge,
  LineChart,
  LogOut,
  Settings,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/live", label: "Live Trading", icon: Activity },
  { href: "/strategy-lab", label: "Strategy Lab", icon: FlaskConical },
  { href: "/intelligence", label: "AI Intelligence", icon: BrainCircuit },
  { href: "/risk", label: "Risk Center", icon: ShieldAlert },
  { href: "/performance", label: "Performance", icon: LineChart },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ username, role }: { username: string; role: string }) {
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    await fetch("/api/session", { method: "DELETE" });
    router.replace("/login");
  }

  return (
    <aside className="flex w-full shrink-0 flex-col border-line bg-panel md:sticky md:top-[29px] md:h-[calc(100vh-29px)] md:w-60 md:border-r">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-fg text-[13px] font-bold text-bg">A</div>
        <div>
          <div className="text-sm font-semibold tracking-[0.18em]">ATLAS</div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-muted">Paper environment</div>
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-visible">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active ? "bg-panel-2 text-fg" : "text-muted hover:bg-panel-2/60 hover:text-fg",
              )}
            >
              <Icon className="h-4 w-4" strokeWidth={1.75} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="hidden border-t border-line px-5 py-4 md:block">
        <div className="text-sm">{username}</div>
        <div className="mb-3 text-[11px] uppercase tracking-wider text-muted">{role}</div>
        <button onClick={logout} className="flex items-center gap-2 text-xs text-muted hover:text-fg">
          <LogOut className="h-3.5 w-3.5" /> Sign out
        </button>
      </div>
    </aside>
  );
}
