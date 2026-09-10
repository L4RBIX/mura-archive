import { cookies } from "next/headers";
import {
  authEndpoint,
  readSupabaseAuthConfig,
  type SupabaseAuthConfig,
} from "@/lib/auth/providers/supabase/config";
import {
  SESSION_COOKIE,
  cookieOptions,
  decodeSession,
  encodeSession,
  isExpired,
  type StoredSession,
} from "@/lib/auth/providers/supabase/session-cookie";
import type { ServerAuthSession } from "@/lib/auth/server-session";

/**
 * The Supabase adapter, answering the one question the seam asks: is there a
 * session, and if so what bearer should go to Core.
 *
 * A near-expired access token is refreshed here rather than at the proxy, so a
 * long-lived tab keeps working without the browser ever seeing either token.
 */

interface TokenResponse {
  access_token?: unknown;
  refresh_token?: unknown;
  expires_in?: unknown;
}

/** Map Supabase's token payload onto a session, or null if it is unusable. */
export function toStoredSession(
  payload: TokenResponse,
  nowSeconds = Date.now() / 1000,
): StoredSession | null {
  const { access_token: access, refresh_token: refresh, expires_in: expires } = payload;
  if (typeof access !== "string" || !access) return null;
  if (typeof refresh !== "string" || !refresh) return null;
  const lifetime = typeof expires === "number" && Number.isFinite(expires) ? expires : 3600;
  return {
    accessToken: access,
    refreshToken: refresh,
    expiresAt: Math.floor(nowSeconds + lifetime),
  };
}

async function requestTokens(
  config: SupabaseAuthConfig,
  grant: string,
  body: Record<string, string>,
): Promise<StoredSession | null> {
  let response: Response;
  try {
    response = await fetch(authEndpoint(config, `/token?grant_type=${grant}`), {
      method: "POST",
      headers: { "content-type": "application/json", apikey: config.anonKey },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return null;
  }
  if (!response.ok) return null;
  try {
    return toStoredSession((await response.json()) as TokenResponse);
  } catch {
    return null;
  }
}

export const exchangeAuthCode = (
  config: SupabaseAuthConfig,
  authCode: string,
  codeVerifier: string,
): Promise<StoredSession | null> =>
  requestTokens(config, "pkce", { auth_code: authCode, code_verifier: codeVerifier });

export const refreshSession = (
  config: SupabaseAuthConfig,
  refreshToken: string,
): Promise<StoredSession | null> =>
  requestTokens(config, "refresh_token", { refresh_token: refreshToken });

/** Persist a session, replacing whatever was there. */
export async function writeSession(session: StoredSession): Promise<void> {
  const store = await cookies();
  // Outlive the access token so a refresh is still possible after idle time.
  store.set(SESSION_COOKIE, encodeSession(session), cookieOptions(60 * 60 * 24 * 30));
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", cookieOptions(0));
}

export async function readSupabaseSession(): Promise<ServerAuthSession> {
  const configuration = readSupabaseAuthConfig();
  if (!configuration.ok) return { status: "provider_unconfigured" };

  const store = await cookies();
  const session = decodeSession(store.get(SESSION_COOKIE)?.value);
  if (!session) return { status: "unauthenticated" };

  if (!isExpired(session)) {
    return { status: "authenticated", accessToken: session.accessToken };
  }

  const refreshed = await refreshSession(configuration.config, session.refreshToken);
  if (!refreshed) {
    // The refresh token is spent or revoked. Treat it as signed out rather than
    // as an error: the user's next action is to sign in again either way.
    return { status: "unauthenticated" };
  }
  await writeSession(refreshed);
  return { status: "authenticated", accessToken: refreshed.accessToken };
}
