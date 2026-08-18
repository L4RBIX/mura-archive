/**
 * Which Clerk token to send to Core, and what it costs.
 *
 * Measured against the live development instance:
 *
 *   session token      no `aud`,  60s lifetime,  ~0ms   (already in the request)
 *   mura-core template `aud` set, 60s lifetime,  ~550ms (Clerk Backend API call)
 *
 * Core validates `aud`, so today only the template qualifies and every miss
 * costs half a second. That is the whole of the "Clerk feels slow" report.
 *
 * The strategy below therefore prefers the session token *whenever it already
 * carries the required audience*, and falls back to the template otherwise. If
 * the Clerk Dashboard is configured to add `aud` to the session token, this
 * upgrade happens on its own with no code change and the Backend API call
 * disappears entirely. Until then the fallback keeps working.
 *
 * The audience is checked locally before use, so a session token that does not
 * qualify is never sent: Core would reject it, and guessing would trade a
 * latency win for broken auth.
 */

export interface TokenClaims {
  aud?: unknown;
  exp?: unknown;
}

/** Decode claims without verifying. Core verifies; this only routes and schedules. */
export function readClaims(token: string): TokenClaims | null {
  const segments = token.split(".");
  if (segments.length !== 3) return null;
  try {
    const payload: unknown = JSON.parse(
      Buffer.from(segments[1], "base64url").toString("utf8"),
    );
    if (typeof payload !== "object" || payload === null) return null;
    return payload as TokenClaims;
  } catch {
    return null;
  }
}

/**
 * True when this token satisfies Core's audience check.
 *
 * `aud` may be a string or an array per RFC 7519, and both forms are accepted
 * here because PyJWT accepts both on the other side.
 */
export function satisfiesAudience(token: string, audience: string): boolean {
  const claims = readClaims(token);
  if (!claims) return false;
  const aud = claims.aud;
  if (typeof aud === "string") return aud === audience;
  if (Array.isArray(aud)) return aud.includes(audience);
  return false;
}

export type TokenSource = "session" | "template";

export interface TokenChoice {
  token: string;
  source: TokenSource;
}
