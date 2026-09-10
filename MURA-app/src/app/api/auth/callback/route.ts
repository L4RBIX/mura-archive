import { NextResponse } from "next/server";
import { exchangeAuthCode } from "@/lib/auth/providers/supabase/adapter";
import { readSupabaseAuthConfig } from "@/lib/auth/providers/supabase/config";
import {
  PKCE_COOKIE,
  SESSION_COOKIE,
  cookieOptions,
  encodeSession,
} from "@/lib/auth/providers/supabase/session-cookie";

/**
 * Complete the OAuth round trip.
 *
 * The code-for-token exchange happens here, on the server, and the resulting
 * tokens are written straight into an httpOnly cookie. Neither token is ever
 * serialised into the page, so the browser cannot read or exfiltrate them.
 */
export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const next = url.searchParams.get("next") ?? "/home";
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/home";

  const failure = (reason: string): Response =>
    NextResponse.redirect(new URL(`/sign-in?error=${reason}`, request.url));

  // Supabase reports provider-side refusals here rather than by status code.
  if (url.searchParams.get("error")) return failure("oauth_denied");

  const code = url.searchParams.get("code");
  if (!code) return failure("missing_code");

  const configuration = readSupabaseAuthConfig();
  if (!configuration.ok) return failure("provider_unconfigured");

  const verifier = request.headers
    .get("cookie")
    ?.split("; ")
    .find((entry) => entry.startsWith(`${PKCE_COOKIE}=`))
    ?.slice(PKCE_COOKIE.length + 1);
  if (!verifier) return failure("missing_verifier");

  const session = await exchangeAuthCode(configuration.config, code, verifier);
  if (!session) return failure("exchange_failed");

  const response = NextResponse.redirect(new URL(safeNext, request.url));
  response.cookies.set(SESSION_COOKIE, encodeSession(session), cookieOptions(60 * 60 * 24 * 30));
  response.cookies.set(PKCE_COOKIE, "", cookieOptions(0));
  return response;
}
