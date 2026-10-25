import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <>
      <PageHeader title="Performance" subtitle="P&L, statistics and benchmark comparison" />
      <EmptyState title="Not built yet — Phase 4-6">
        Performance analytics require recorded trades. Metrics (profit factor, expectancy, Sharpe, Sortino, SPY comparison) are built in Phases 4–6.
      </EmptyState>
    </>
  );
}
