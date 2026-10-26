import { NextResponse } from "next/server";
import { proxyToApi } from "@/lib/proxy";

type Ctx = { params: Promise<{ id: string }> };

// Admin-only, password re-entry and validation gates are enforced by the API.
export async function POST(req: Request, { params }: Ctx) {
  const { id } = await params;
  const body = (await req.json().catch(() => null)) as { status?: unknown; reason?: unknown; password?: unknown } | null;
  if (!body || typeof body.status !== "string" || typeof body.reason !== "string" || typeof body.password !== "string") {
    return NextResponse.json({ error: "status, reason and password required" }, { status: 400 });
  }
  return proxyToApi(req, `/api/v1/strategies/${encodeURIComponent(id)}/status`, {
    method: "POST",
    body: { status: body.status, reason: body.reason, password: body.password },
  });
}
