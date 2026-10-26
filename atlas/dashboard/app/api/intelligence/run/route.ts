import { proxyToApi } from "@/lib/proxy";

// Operator or admin; the API enforces the role and records the request in the audit log.
export async function POST(req: Request) {
  return proxyToApi(req, "/api/v1/intelligence/run", { method: "POST" });
}
