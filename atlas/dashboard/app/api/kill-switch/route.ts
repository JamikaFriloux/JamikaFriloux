import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, apiBase, isSameOrigin } from "@/lib/session";

// Proxies kill-switch actions to the API. Authorization (operator to engage, admin + password
// to resume) is enforced by the API, not here.
export async function POST(req: Request) {
  if (!isSameOrigin(req)) return NextResponse.json({ error: "bad origin" }, { status: 403 });
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "not authenticated" }, { status: 401 });
  const body = (await req.json().catch(() => null)) as
    | { action?: string; reason?: string; password?: string }
    | null;
  if (!body || (body.action !== "engage" && body.action !== "resume")) {
    return NextResponse.json({ error: "invalid action" }, { status: 400 });
  }
  const payload =
    body.action === "engage"
      ? { reason: body.reason ?? "" }
      : { reason: body.reason ?? "", password: body.password ?? "" };
  try {
    const res = await fetch(`${apiBase()}/api/v1/kill-switch/${body.action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "ATLAS API unreachable" }, { status: 502 });
  }
}
