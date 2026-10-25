import { NextResponse } from "next/server";
import { proxyToApi } from "@/lib/proxy";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as { name?: unknown; symbols?: unknown } | null;
  if (!body || typeof body.name !== "string" || !Array.isArray(body.symbols)) {
    return NextResponse.json({ error: "name and symbols required" }, { status: 400 });
  }
  return proxyToApi(req, "/api/v1/watchlists", {
    method: "POST",
    body: { name: body.name, symbols: body.symbols.map(String) },
  });
}
