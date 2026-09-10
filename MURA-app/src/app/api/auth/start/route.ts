import { NextResponse } from "next/server";
import { authEndpoint, readSupabaseAuthConfig } from "@/lib/auth/providers/supabase/config";
import { PKCE_COOKIE, cookieOptions } from "@/lib/auth/providers/supabase/session-cookie";

/**
 * Begin a Supabase OAuth sign-in.
 *
 * PKCE is used even though this is a confidential server-side exchange: the
 * verifier never leaves an httpOnly cookie, so an intercepted authorization
 * code is worthless on its own.
 */

const base64url = (bytes: ArrayBuffer): string =>
  Buffer.from(bytes).toString("base64url");

export async function GET(request: Request): Promise<Response> {
  const configuration = readSupabaseAuthConfig();
  if (!configuration.ok) {
    return NextResponse.redirect(new URL("/sign-in?error=provider_unconfigured", request.url));
  }

  const requested = new URL(request.url).searchParams;
  const provider = requested.get("provider") ?? "google";
  // Only a path is accepted, so a crafted link cannot bounce a freshly signed-in
  // user out to another origin carrying their session.
  const next = requested.get("next");
  const redirectPath = next && next.startsWith("/") && !next.startsWith("//") ? next : "/home";

  const verifier = base64url(crypto.getRandomValues(new Uint8Array(48)).buffer);
  const challenge = base64url(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)),
  );

  const callback = new URL("/api/auth/callback", request.url);
  callback.searchParams.set("next", redirectPath);

  const authorize = new URL(authEndpoint(configuration.config, "/authorize"));
  authorize.searchParams.set("provider", provider);
  authorize.searchParams.set("redirect_to", callback.toString());
  authorize.searchParams.set("code_challenge", challenge);
  authorize.searchParams.set("code_challenge_method", "s256");

  const response = NextResponse.redirect(authorize.toString());
  response.cookies.set(PKCE_COOKIE, verifier, cookieOptions(600));
  return response;
}
