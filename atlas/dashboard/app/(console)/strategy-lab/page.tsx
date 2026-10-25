import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <>
      <PageHeader title="Strategy Lab" subtitle="Strategy library, backtests and promotion status" />
      <EmptyState title="Not built yet — Phase 4">
        The backtesting engine, walk-forward validation and the RESEARCH → PAPER → LIVE_CANDIDATE promotion gates are built in Phase 4.
      </EmptyState>
    </>
  );
}
