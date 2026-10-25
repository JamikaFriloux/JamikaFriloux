import { Sidebar } from "@/components/sidebar";
import { getMe } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const me = await getMe();
  return (
    <div className="flex min-h-[calc(100vh-29px)] flex-col md:flex-row">
      <Sidebar username={me.username} role={me.role} />
      <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
    </div>
  );
}
