/**
 * Where the Supabase session lives: an httpOnly cookie, and nowhere else.
 *
 * Supabase's own browser SDK keeps the session in `localStorage`, which would
 * put a bearer token for the family archive inside reach of any script on the
 * page. MURA's boundary is the opposite: the token exists server-side, the
 * proxy attaches it, and the browser never holds a credential it could leak.
 *
 * That is why this integration speaks to Supabase's REST API directly instead
 * of using the SDK. The cost is this file; the benefit is that an XSS bug
 * cannot walk away with a family's memories.
 */

export const SESSION_COOKIE = "mura_session";
export const PKCE_COOKIE = "mura_pkce";

export interface StoredSession {
  accessToken: string;
  refreshToken: string;
  /** Epoch seconds. */
  expiresAt: number;
}

/** Refresh this long before expiry so a request never races the deadline. */
export const REFRESH_MARGIN_SECONDS = 60;

export function encodeSession(session: StoredSession): string {
  return Buffer.from(JSON.stringify(session), "utf8").toString("base64url");
}

export function decodeSession(raw: string | undefined): StoredSession | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
    if (typeof parsed !== "object" || parsed === null) return null;
    const { accessToken, refreshToken, expiresAt } = parsed as Record<string, unknown>;
    if (typeof accessToken !== "string" || !accessToken) return null;
    if (typeof refreshToken !== "string" || !refreshToken) return null;
    if (typeof expiresAt !== "number" || !Number.isFinite(expiresAt)) return null;
    return { accessToken, refreshToken, expiresAt };
  } catch {
    // A malformed cookie is an absent session, never an error page.
    return null;
  }
}

export function isExpired(session: StoredSession, nowSeconds = Date.now() / 1000): boolean {
  return session.expiresAt - REFRESH_MARGIN_SECONDS <= nowSeconds;
}

/** Cookie attributes. Secure everywhere except a local http origin. */
export function cookieOptions(maxAgeSeconds: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: maxAgeSeconds,
  };
}
