export const SESSION_COOKIE = "atlas_session";

export function apiBase(): string {
  return process.env.ATLAS_API_URL ?? "http://localhost:8000";
}

/** Same-origin check for state-changing route handlers (defense in depth with SameSite=strict). */
export function isSameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
