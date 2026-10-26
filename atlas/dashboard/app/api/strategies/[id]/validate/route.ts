import { proxyToApi } from "@/lib/proxy";

type Ctx = { params: Promise<{ id: string }> };

// Admin-only; the API enforces the role and records the request in the audit log.
export async function POST(req: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyToApi(req, `/api/v1/strategies/${encodeURIComponent(id)}/validate`, { method: "POST" });
}
