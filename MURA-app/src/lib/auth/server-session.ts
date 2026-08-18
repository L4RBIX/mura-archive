/**
 * Server-side session resolution. The only place a bearer token ever exists.
 *
 * This stays the provider-neutral seam it was in PR-03C: the proxy asks for a
 * session and gets either an access token for Core or a reason there is none.
 * Clerk lives behind it, in `providers/clerk/`, so no product code imports a
 * vendor API and swapping providers touches one directory.
 *
 * What has *not* changed is the refusal. There is no fallback to the Core
 * service credential when no user session exists, and no environment switch
 * that turns a fake user on. Those are the holes PR-03B closed on the backend,
 * and a provider integration is exactly the moment they get reopened by
 * accident.
 */

import { readClerkSession } from "@/lib/auth/providers/clerk/adapter";

export type ServerAuthSession =
  | { status: "authenticated"; accessToken: string }
  | { status: "unauthenticated" }
  /** Deployment is missing its identity-provider configuration. */
  | { status: "provider_unconfigured" };

/**
 * Resolve the caller's session from the incoming request.
 *
 * The request parameter is intentionally unused: Clerk reads its session from
 * request context established by `clerkMiddleware`, not from anything this
 * function is handed. Any `Authorization` header the browser sent is ignored --
 * the proxy owns this boundary, so a caller cannot present its own bearer and
 * have it forwarded.
 */
export async function readServerAuthSession(request: Request): Promise<ServerAuthSession> {
  void request;
  return readClerkSession();
}
