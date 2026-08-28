import { createSign } from "node:crypto";
import { devKeyPair, DEV_KEY_ID } from "@/lib/auth/providers/dev/keys";
import type { DevAuthConfig } from "@/lib/auth/providers/dev/config";

/**
 * RS256 token minting for the local development issuer.
 *
 * Hand-rolled rather than pulled from a JWT library on purpose: the app already
 * ships no signing dependency, and adding one to the browser bundle's
 * dependency tree to serve a development-only issuer is a poor trade. RS256 is
 * RSASSA-PKCS1-v1_5 over SHA-256 with base64url segments, which `node:crypto`
 * does directly.
 *
 * Every claim Core verifies is set here, with the same meaning production has.
 * Nothing about authorization appears: no family, no role, no person id. Core
 * resolves the subject to a user and reads membership from the database on
 * every request, and a claim baked in here would be stale the moment an owner
 * changed a role.
 */

/** Who the token is about. An identity, and nothing more. */
export interface DevIdentity {
  subject: string;
  email: string;
  displayName: string;
}

/** Short, because a development issuer refreshing often is a feature. */
export const DEV_TOKEN_TTL_SECONDS = 60 * 60;

function base64url(input: Buffer | string): string {
  return Buffer.from(input)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export interface MintOptions {
  identity: DevIdentity;
  config: DevAuthConfig;
  /** Seconds since the epoch. Injected so expiry is testable. */
  now?: number;
  ttlSeconds?: number;
}

/**
 * Mint a token Core will accept.
 *
 * `nbf` is set one second in the past rather than exactly now: Core verifies it,
 * and a token whose `nbf` equals the verifying clock's next tick is rejected on
 * a machine whose clocks differ by a millisecond. This is the standard reason
 * for a small backdate, not a widening of anything.
 */
export function mintDevToken({
  identity,
  config,
  now = Math.floor(Date.now() / 1000),
  ttlSeconds = DEV_TOKEN_TTL_SECONDS,
}: MintOptions): string {
  const header = { alg: "RS256", typ: "JWT", kid: DEV_KEY_ID };
  const payload = {
    iss: config.issuer,
    aud: config.audience,
    sub: identity.subject,
    email: identity.email,
    name: identity.displayName,
    iat: now,
    nbf: now - 1,
    exp: now + ttlSeconds,
  };

  const signingInput = `${base64url(JSON.stringify(header))}.${base64url(JSON.stringify(payload))}`;
  const signer = createSign("RSA-SHA256");
  signer.update(signingInput);
  signer.end();
  const signature = base64url(signer.sign(devKeyPair().privateKey));
  return `${signingInput}.${signature}`;
}

/**
 * Read a token's payload without verifying it.
 *
 * Used only to decide whether a cached token is still fresh enough to reuse.
 * It is never used to establish identity — Core verifies the signature, and
 * trusting an unverified payload for anything else is how tokens get forged.
 */
export function readUnverifiedExpiry(token: string): number | null {
  const segments = token.split(".");
  if (segments.length !== 3) return null;
  try {
    const payload = JSON.parse(Buffer.from(segments[1], "base64url").toString("utf8"));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}
