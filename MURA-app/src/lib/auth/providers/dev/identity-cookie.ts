/**
 * The cookie that says which development identity is signed in.
 *
 * It carries an identity *selector* — subject, email, display name — and never
 * a token. The bearer Core sees is minted server-side on each request, exactly
 * as the Clerk adapter mints one, so the invariant that no JWT ever reaches the
 * browser holds for this provider too.
 *
 * `httpOnly` for the same reason: script on the page has no business reading
 * even this much, and the client learns who is signed in by asking the server
 * (`GET /api/dev-auth/session`) rather than by parsing a cookie.
 *
 * Anyone who can set this cookie can sign in as anyone. That is what a
 * development sign-in *is*, and it is contained by the provider being unable to
 * run outside development at all (see `config.ts`) — not by the cookie being
 * hard to forge.
 */

export const DEV_IDENTITY_COOKIE = "mura_dev_identity";

export interface DevIdentityCookie {
  subject: string;
  email: string;
  displayName: string;
}

/** Stable subject for an email, so signing in twice is the same MURA user. */
export function subjectForEmail(email: string): string {
  const normalized = email.trim().toLowerCase();
  // Not a hash: the subject is an opaque, stable string and readability in a
  // development database is worth more here than opacity.
  return `dev|${normalized}`;
}

export function encodeDevIdentity(identity: DevIdentityCookie): string {
  return Buffer.from(JSON.stringify(identity), "utf8").toString("base64url");
}

/**
 * Parse the cookie, rejecting anything that is not a complete identity.
 *
 * A half-formed value must not become a user with an empty subject — Core would
 * resolve that to *some* row, and which one is not a question worth asking.
 */
export function decodeDevIdentity(value: string | undefined): DevIdentityCookie | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(Buffer.from(value, "base64url").toString("utf8"));
    const { subject, email, displayName } = parsed ?? {};
    if (typeof subject !== "string" || subject.trim() === "") return null;
    if (typeof email !== "string" || email.trim() === "") return null;
    if (typeof displayName !== "string") return null;
    return { subject, email, displayName };
  } catch {
    return null;
  }
}
