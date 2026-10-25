import { proxyToApi } from "@/lib/proxy";

export async function GET(req: Request) {
  return proxyToApi(req, "/api/v1/market/live");
}
