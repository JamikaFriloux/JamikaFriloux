import "server-only";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, apiBase, isSameOrigin } from "./session";

/**
 * Forward a dashboard request to the ATLAS API with the httpOnly session token.
 * Authorization is enforced by the API; state-changing methods additionally require a
 * same-origin request (defense in depth with the SameSite=strict cookie).
 */
export async function proxyToApi(
  req: Request,
  path: string,
  init: { method?: "GET" | "POST" | "PUT" | "DELETE"; body?: unknown } = {},
): Promise<NextResponse> {
  const method = init.method ?? "GET";
  if (method !== "GET" && !isSameOrigin(req)) {
    return NextResponse.json({ error: "bad origin" }, { status: 403 });
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "not authenticated" }, { status: 401 });
  try {
    const res = await fetch(`${apiBase()}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
    });
    if (res.status === 204) return new NextResponse(null, { status: 204 });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "ATLAS API unreachable" }, { status: 502 });
  }
}
