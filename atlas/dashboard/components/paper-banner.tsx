export function PaperBanner() {
  return (
    // Sticky so the PAPER warning never scrolls away; the solid backing keeps page content
    // from showing through the translucent tint.
    <div className="sticky top-0 z-40 bg-bg">
      <div
        role="status"
        className="flex items-center justify-center gap-2 border-b border-warn/30 bg-warn/10 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-warn"
      >
        <span className="h-1.5 w-1.5 rounded-full bg-warn" aria-hidden />
        Paper trading — simulated orders only — no real money at risk
      </div>
    </div>
  );
}
