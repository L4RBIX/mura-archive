/**
 * Supabase Auth as an OIDC issuer behind MURA's provider seam.
 *
 * Core does not trust this module. It fetches Supabase's JWKS from its own
 * configuration and verifies every token itself — signature, `iss`, `aud`,
 * `exp`, `nbf`, `sub` — then reads family membership from PostgreSQL on every
 * request. Supabase decides who someone is; MURA still decides what they may do.
 *
 * The project reference is the only required setting: every URL below is
 * derived from it, so the issuer, the token endpoint and the JWKS Core reads
 * cannot drift apart by being configured in three places.
 */

export interface SupabaseAuthConfig {
  /** e.g. https://abcd.supabase.co */
  projectUrl: string;
  /** Anonymous key. Public by design; it authorises nothing on its own. */
  anonKey: string;
}

export type SupabaseAuthConfigResult =
  | { ok: true; config: SupabaseAuthConfig }
  | { ok: false; reason: string };

export function readSupabaseAuthConfig(
  env: Record<string, string | undefined> = process.env,
): SupabaseAuthConfigResult {
  const projectUrl = env.NEXT_PUBLIC_SUPABASE_URL?.trim().replace(/\/$/, "");
  const anonKey = env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();

  if (!projectUrl) return { ok: false, reason: "missing_NEXT_PUBLIC_SUPABASE_URL" };
  if (!anonKey) return { ok: false, reason: "missing_NEXT_PUBLIC_SUPABASE_ANON_KEY" };
  if (!/^https:\/\/[\w-]+\.supabase\.co$/.test(projectUrl)) {
    return { ok: false, reason: "invalid_NEXT_PUBLIC_SUPABASE_URL" };
  }

  return { ok: true, config: { projectUrl, anonKey } };
}

export function isSupabaseAuthConfigured(
  env: Record<string, string | undefined> = process.env,
): boolean {
  return readSupabaseAuthConfig(env).ok;
}

export const authEndpoint = (config: SupabaseAuthConfig, path: string): string =>
  `${config.projectUrl}/auth/v1${path}`;
