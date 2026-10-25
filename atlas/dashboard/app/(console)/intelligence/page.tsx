import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <>
      <PageHeader title="AI Intelligence" subtitle="Market briefings, news analysis and agent activity" />
      <EmptyState title="Not built yet — Phase 5">
        Research agents (structured, schema-validated outputs with source evidence) are built in Phase 5. They will never place orders.
      </EmptyState>
    </>
  );
}
