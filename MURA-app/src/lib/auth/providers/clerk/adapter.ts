/**
 * The Clerk adapter: the only server file that knows the provider's name.
 *
 * Its job is to turn Clerk's server-side auth object into the provider-neutral
 * `ServerAuthSession` the proxy understands. Nothing above this directory
 * imports Clerk, so replacing the provider means replacing these files and no
 * product code.
 *
 * Clerk establishes *identity*, and that is all. No family id, no role, no
 * person id goes into the token: Core loads issuer + subject, finds the
 * UserRow, and reads membership from PostgreSQL on every request. Authorization
 * claims baked into a JWT would be stale the moment an owner changed a role.
 */

import { auth } from "@clerk/nextjs/server";
import type { ServerAuthSession } from "@/lib/auth/server-session";
import { readClerkConfig } from "@/lib/auth/providers/clerk/config";
import {
  cacheToken,
  getCachedToken,
  mintOnce,
} from "@/lib/auth/providers/clerk/token-cache";
import { satisfiesAudience, type TokenChoice } from "@/lib/auth/providers/clerk/token-strategy";

/** The shape of Clerk's `auth()` result that this adapter depends on. */
export interface ClerkAuthState {
  userId: string | null;
  sessionId: string | null;
  getToken: (options?: { template?: string }) => Promise<string | null>;
}

export interface TokenOptions {
  template: string;
  audience: string;
  now?: number;
}

/**
 * Obtain a token Core will accept, as cheaply as possible.
 *
 * The session token is tried first because Clerk already has it in the request
 * context -- no network. It is only used if it genuinely carries the audience
 * Core requires, checked locally, so this can never send a token Core would
 * reject. Otherwise the `mura-core` template is minted, which does cost a
 * Backend API round trip.
 */
export async function obtainCoreToken(
  state: ClerkAuthState,
  options: TokenOptions,
): Promise<TokenChoice | null> {
  const sessionToken = await state.getToken();
  if (sessionToken && satisfiesAudience(sessionToken, options.audience)) {
    return { token: sessionToken, source: "session" };
  }

  const templated = await state.getToken({ template: options.template });
  if (!templated) return null;
  return { token: templated, source: "template" };
}

/**
 * Pure mapping over an injected auth state, so the decision table is testable
 * without Next.js or Clerk.
 *
 * The order is deliberate: configuration is checked by the caller first,
 * because an unconfigured deployment must never look like a signed-out user --
 * that would put a login button in front of someone with nothing to log into.
 */
export async function toServerAuthSession(
  state: ClerkAuthState,
  options: TokenOptions,
): Promise<ServerAuthSession> {
  if (!state.userId || !state.sessionId) return { status: "unauthenticated" };

  const cached = getCachedToken(state.sessionId, options.now);
  if (cached) return { status: "authenticated", accessToken: cached };

  // Concurrent bootstrap requests share one mint rather than each starting
  // their own Backend API call.
  const token = await mintOnce(`${state.sessionId}:${options.template}`, async () => {
    // Re-check inside the flight: a queued caller may find the winner's token
    // already cached and can skip minting entirely.
    const fresh = getCachedToken(state.sessionId as string, options.now);
    if (fresh) return fresh;

    const choice = await obtainCoreToken(state, options);
    if (!choice) return null;
    cacheToken(state.sessionId as string, choice.token, options.now);
    return choice.token;
  });

  // An active session that cannot produce a Core token is not a signed-in user
  // as far as Core is concerned; refusing is the honest answer.
  if (!token) return { status: "unauthenticated" };
  return { status: "authenticated", accessToken: token };
}

/** Resolve the current request's session through Clerk. */
export async function readClerkSession(): Promise<ServerAuthSession> {
  const configuration = readClerkConfig();
  if (!configuration.ok) return { status: "provider_unconfigured" };

  try {
    const state = await auth();
    return await toServerAuthSession(
      { userId: state.userId, sessionId: state.sessionId, getToken: state.getToken },
      {
        template: configuration.config.tokenTemplate,
        audience: configuration.config.audience,
      },
    );
  } catch {
    // A Clerk outage or a misconfigured template is not a signed-out user, but
    // it is equally not a reason to let a request through unauthenticated.
    return { status: "unauthenticated" };
  }
}
