export function EmptyState({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-panel/50 px-6 py-10 text-center">
      <div className="text-sm font-medium text-fg">{title}</div>
      <div className="mx-auto mt-2 max-w-lg text-sm text-muted">{children}</div>
    </div>
  );
}
