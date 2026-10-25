import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <>
      <PageHeader title="Live Trading" subtitle="Watchlists, prices, strategy signals and order activity" />
      <EmptyState title="Not built yet — Phase 2-3">
        Market data ingestion and the deterministic signal engine are built in Phases 2–3. Open positions and orders already appear on the Overview once the executor syncs.
      </EmptyState>
    </>
  );
}
