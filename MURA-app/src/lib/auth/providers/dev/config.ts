/**
 * When the local development identity provider is allowed to exist.
 *
 * MURA's auth boundary is provider-neutral by design (`server-session.ts`), and
 * this is a second provider behind that seam — not a bypass of it. Core still
 * performs the full OIDC verification it performs in production: RS256 only,
 * signature checked against a JWKS it fetches from its own configuration, with
 * `iss`, `aud`, `exp`, `nbf` and `sub` all verified. Membership is still read
 * from the database on every request, so BOLA behaviour is unchanged.
 *
 * The only thing that differs from production is *who issues* the token. That
 * is precisely why the gate below is deliberately paranoid: this provider is an
 * issuer, and an issuer that could be switched on in production would be a
 * complete authentication bypass rather than a development convenience.
 *
 * Three conditions, all required:
 *   1. `MURA_DEV_AUTH=true` — an explicit opt-in, never a default.
 *   2. `NODE_ENV !== "production"` — a production build refuses regardless.
 *   3. `VERCEL_ENV` unset or `development` — a preview or production deployment
 *      refuses even if someone sets the variable in a dashboard.
 *
 * There is no way to reach this provider by accident, and no fallback into it
 * when Clerk is unconfigured: an unconfigured deployment reports itself as
 * unconfigured, exactly as before.
 */

/** The single opt-in. Absent or anything but "true" means the issuer is off. */
export const DEV_AUTH_FLAG = "MURA_DEV_AUTH";

/** Claims the minted token carries, and Core is configured to expect. */
export interface DevAuthConfig {
  issuer: string;
  audience: string;
}

export type DevAuthConfigResult =
  | { ok: true; config: DevAuthConfig }
  | { ok: false; reason: string };

/**
 * Whether the dev provider may run at all.
 *
 * Exported separately from `readDevAuthConfig` so the refusal can be asserted
 * on its own, without any configuration present.
 */
export function isDevAuthAllowed(
  env: Record<string, string | undefined> = process.env,
): boolean {
  if (env[DEV_AUTH_FLAG] !== "true") return false;
  if (env.NODE_ENV === "production") return false;
  // Set on every Vercel deployment. Anything that is not a local dev run is a
  // deployment, and a deployment must not mint its own identities.
  if (env.VERCEL_ENV && env.VERCEL_ENV !== "development") return false;
  return true;
}

/**
 * The issuer and audience this provider signs with.
 *
 * Both must match Core's `AUTH_ISSUER` and `AUTH_AUDIENCE` exactly or Core
 * rejects the token — which is the desired failure. They are read from the
 * environment rather than hardcoded so the two sides are configured from one
 * place and cannot silently drift apart.
 */
export function readDevAuthConfig(
  env: Record<string, string | undefined> = process.env,
): DevAuthConfigResult {
  if (!isDevAuthAllowed(env)) return { ok: false, reason: "dev_auth_not_allowed" };

  const issuer = env.DEV_AUTH_ISSUER?.trim();
  const audience = env.DEV_AUTH_AUDIENCE?.trim();
  if (!issuer) return { ok: false, reason: "missing_DEV_AUTH_ISSUER" };
  if (!audience) return { ok: false, reason: "missing_DEV_AUTH_AUDIENCE" };

  return { ok: true, config: { issuer, audience } };
}
