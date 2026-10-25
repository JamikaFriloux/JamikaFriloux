import { NextResponse } from "next/server";
import { SESSION_COOKIE, apiBase, isSameOrigin } from "@/lib/session";

// Login: exchange credentials for an API token, stored in an httpOnly cookie so page scripts
// can never read it.
export async function POST(req: Request) {
  if (!isSameOrigin(req)) return NextResponse.json({ error: "bad origin" }, { status: 403 });
  const body = (await req.json().catch(() => null)) as { username?: string; password?: string } | null;
  if (!body?.username || !body?.password) {
    return NextResponse.json({ error: "username and password required" }, { status: 400 });
  }
  let res: Response;
  try {
    res = await fetch(`${apiBase()}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: body.username, password: body.password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "ATLAS API unreachable" }, { status: 502 });
  }
  if (!res.ok) {
    const status = res.status === 429 ? 429 : 401;
    return NextResponse.json(
      { error: status === 429 ? "Too many attempts. Try again in a minute." : "Invalid credentials" },
      { status },
    );
  }
  const data = (await res.json()) as { access_token: string; expires_in: number };
  const out = NextResponse.json({ ok: true });
  out.cookies.set(SESSION_COOKIE, data.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: data.expires_in,
  });
  return out;
}

export async function DELETE(req: Request) {
  if (!isSameOrigin(req)) return NextResponse.json({ error: "bad origin" }, { status: 403 });
  const out = NextResponse.json({ ok: true });
  out.cookies.delete(SESSION_COOKIE);
  return out;
}
