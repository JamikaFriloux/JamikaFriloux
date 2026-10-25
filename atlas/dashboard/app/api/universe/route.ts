import { proxyToApi } from "@/lib/proxy";

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams.get("q")?.slice(0, 32) ?? "";
  return proxyToApi(req, `/api/v1/universe?limit=12&q=${encodeURIComponent(q)}`);
}
