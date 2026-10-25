import { NextResponse } from "next/server";
import { proxyToApi } from "@/lib/proxy";

type Ctx = { params: Promise<{ name: string }> };

export async function PUT(req: Request, { params }: Ctx) {
  const { name } = await params;
  const body = (await req.json().catch(() => null)) as { symbols?: unknown } | null;
  if (!body || !Array.isArray(body.symbols)) {
    return NextResponse.json({ error: "symbols required" }, { status: 400 });
  }
  return proxyToApi(req, `/api/v1/watchlists/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: { symbols: body.symbols.map(String) },
  });
}

export async function DELETE(req: Request, { params }: Ctx) {
  const { name } = await params;
  return proxyToApi(req, `/api/v1/watchlists/${encodeURIComponent(name)}`, { method: "DELETE" });
}
