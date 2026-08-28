import { NextResponse } from "next/server";
import { isDevAuthAllowed } from "@/lib/auth/providers/dev/config";
import { devJwks } from "@/lib/auth/providers/dev/keys";

/**
 * The development issuer's JWK Set.
 *
 * Core fetches this from its own configuration (`AUTH_JWKS_URL`) and verifies
 * every token against it — the same RS256 path production uses. A token can
 * never influence where Core looks for keys, which is what keeps a forged `iss`
 * from becoming SSRF, so this endpoint being public is not a weakness: it
 * serves a public key, which is what a JWKS is for.
 *
 * It 404s when the provider is not allowed to run, so a build that should have
 * no development issuer does not advertise one.
 */
export async function GET() {
  if (!isDevAuthAllowed()) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  return NextResponse.json(devJwks(), {
    headers: {
      // Core caches JWKS itself; a short cache keeps a key rotation from
      // needing a Core restart to be noticed.
      "cache-control": "public, max-age=60",
    },
  });
}
