/**
 * The provider-neutral auth boundary.
 *
 * Nothing above this module knows which identity provider MURA eventually uses.
 * The application asks for a session status and, when authenticated, an internal
 * user — never an issuer, a subject, or a raw token.
 *
 * The browser deliberately never receives an access token at all. The Next.js
 * proxy owns the session and attaches the bearer server-side, so there is no
 * token to leak through localStorage, a devtools inspection or an XSS payload.
 * Session status is therefore *derived* from what Core answers, which has the
 * useful property that the client's idea of "signed in" can never drift from
 * the server's.
 */

/** Codes the proxy and Core use for the two distinguishable 401s. */
export const AUTHENTICATION_REQUIRED = "authentication_required";
export const INVALID_TOKEN = "invalid_token";
/** The proxy's own code: no identity provider is configured yet. */
export const AUTH_PROVIDER_UNCONFIGURED = "auth_provider_unconfigured";

export type AuthStatus =
  | "loading"
  | "authenticated"
  | "unauthenticated"
  /** No identity provider is wired up. Not an outage, and not a login prompt. */
  | "provider_unconfigured"
  | "error";

/** Safe self-description. Provider subject and issuer are deliberately absent. */
export interface AuthUser {
  userId: string;
  email: string | null;
  displayName: string | null;
}

export type AuthSession =
  | { status: "loading" }
  | { status: "authenticated"; user: AuthUser }
  | { status: "unauthenticated" }
  | { status: "provider_unconfigured" }
  | { status: "error"; code: string };

export const LOADING_SESSION: AuthSession = { status: "loading" };

/**
 * Turn a failed `/v1/me` into a session status.
 *
 * A 401 is not automatically "please log in": if no provider is configured yet
 * there is nothing to log into, and telling the user to sign in would be a lie.
 * Anything that is not an authentication problem stays `error`, so a Core outage
 * never silently presents as a signed-out app.
 */
export function sessionFromFailure(status: number, code: string): AuthSession {
  if (status !== 401 && status !== 403) return { status: "error", code };
  if (code === AUTH_PROVIDER_UNCONFIGURED) return { status: "provider_unconfigured" };
  if (code === AUTHENTICATION_REQUIRED || code === INVALID_TOKEN) {
    return { status: "unauthenticated" };
  }
  return { status: "error", code };
}

/** True while the app may not issue family-scoped Core requests. */
export function isSignedIn(session: AuthSession): boolean {
  return session.status === "authenticated";
}

/**
 * Whether a failed request should be retried at all.
 *
 * With no provider there is no refresh mechanism, so retrying a rejected token
 * would just hammer Core with the same rejected token forever.
 */
export function shouldRetryAfter(session: AuthSession): boolean {
  return session.status !== "unauthenticated" && session.status !== "provider_unconfigured";
}
