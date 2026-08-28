import { cookies } from "next/headers";
import type { ServerAuthSession } from "@/lib/auth/server-session";
import { isDevAuthAllowed, readDevAuthConfig } from "@/lib/auth/providers/dev/config";
import {
  DEV_IDENTITY_COOKIE,
  decodeDevIdentity,
  type DevIdentityCookie,
} from "@/lib/auth/providers/dev/identity-cookie";
import { mintDevToken } from "@/lib/auth/providers/dev/token";

/**
 * The development issuer's adapter, sitting behind the same seam as Clerk's.
 *
 * It answers the one question `server-session.ts` asks — is there a session, and
 * if so what bearer should go to Core — and nothing above this directory knows
 * which provider produced the answer.
 */

/**
 * Pure mapping from a cookie to a session, so the decision table is testable
 * without Next.js request context.
 *
 * The refusal at the top is the important line. If the provider is not allowed
 * to run, this reports *unconfigured*, never a signed-in user: a build that
 * should not have a development issuer must not acquire one because a cookie
 * happened to be present.
 */
export function toDevServerAuthSession(
  identity: DevIdentityCookie | null,
  env: Record<string, string | undefined> = process.env,
  now?: number,
): ServerAuthSession {
  if (!isDevAuthAllowed(env)) return { status: "provider_unconfigured" };

  const configuration = readDevAuthConfig(env);
  if (!configuration.ok) return { status: "provider_unconfigured" };

  if (!identity) return { status: "unauthenticated" };

  return {
    status: "authenticated",
    accessToken: mintDevToken({
      identity: {
        subject: identity.subject,
        email: identity.email,
        displayName: identity.displayName,
      },
      config: configuration.config,
      now,
    }),
  };
}

/** Resolve the current request's session through the development issuer. */
export async function readDevSession(): Promise<ServerAuthSession> {
  // Checked before touching request context so an unrelated deployment never
  // pays for a cookie read it would discard anyway.
  if (!isDevAuthAllowed()) return { status: "provider_unconfigured" };

  const store = await cookies();
  const identity = decodeDevIdentity(store.get(DEV_IDENTITY_COOKIE)?.value);
  return toDevServerAuthSession(identity);
}
