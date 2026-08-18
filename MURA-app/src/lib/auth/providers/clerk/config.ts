/**
 * Clerk configuration, read from the environment and validated once.
 *
 * Everything here is a name, never a value baked into source. Clerk development
 * and production instances have different issuers and keys, so the deployment
 * supplies them; nothing branches on a hardcoded `*.clerk.accounts.dev` domain.
 *
 * Missing configuration fails closed. An app that cannot establish who the
 * caller is must refuse, not fall back — the whole point of the PR-03B
 * enforcement work is that there is no second way in.
 */

/**
 * The JWT template that mints tokens for Mura Core.
 *
 * Core validates `aud`, and Clerk's session token has no `aud` claim: the
 * documented default claims are azp, exp, fva, iat, iss, jti, nbf, sid, sub, v,
 * pla and fea. A JWT template is the mechanism Clerk documents for setting a
 * custom audience, so that is what this uses. The template name is
 * configurable because it is created by hand in the Clerk Dashboard and its
 * name is a deployment detail, not a constant of the code.
 */
export const DEFAULT_TOKEN_TEMPLATE = "mura-core";

/**
 * The audience Core requires, mirrored here so the proxy can tell locally
 * whether a plain session token would already satisfy it -- and skip the
 * Backend API round trip when it would. It is not a secret: it travels in
 * every token.
 */
export const DEFAULT_CORE_AUDIENCE = "mura-core";

export interface ClerkConfig {
  /** Name of the Dashboard JWT template whose `aud` matches Core's AUTH_AUDIENCE. */
  tokenTemplate: string;
  /** Must equal Core's AUTH_AUDIENCE, or Core rejects every request. */
  audience: string;
}

export type ClerkConfigResult =
  | { ok: true; config: ClerkConfig }
  | { ok: false; missing: string[] };

/**
 * Publishable key is required by the Clerk provider in the browser bundle;
 * the secret key is server-only and must never be exposed. Both are read here
 * only to decide whether the provider is configured -- neither value is
 * returned, logged, or attached to any error.
 */
export function readClerkConfig(
  env: Record<string, string | undefined> = process.env,
): ClerkConfigResult {
  const missing: string[] = [];
  if (!env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) missing.push("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY");
  if (!env.CLERK_SECRET_KEY) missing.push("CLERK_SECRET_KEY");
  if (missing.length > 0) return { ok: false, missing };
  return {
    ok: true,
    config: {
      tokenTemplate: env.CLERK_JWT_TEMPLATE || DEFAULT_TOKEN_TEMPLATE,
      audience: env.MURA_CORE_AUDIENCE || DEFAULT_CORE_AUDIENCE,
    },
  };
}

export function isClerkConfigured(
  env: Record<string, string | undefined> = process.env,
): boolean {
  return readClerkConfig(env).ok;
}
