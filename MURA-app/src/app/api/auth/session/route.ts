import { NextResponse } from "next/server";
import { readServerAuthSession } from "@/lib/auth/server-session";

/**
 * Whether the caller has a session, for the client to read.
 *
 * The session cookie is `httpOnly`, so the browser cannot answer this for
 * itself. It asks here instead, and gets back only two facts: signed in or not,
 * and an opaque key that changes when the account changes. The access token
 * stays on the server.
 */
export async function GET(request: Request): Promise<Response> {
  const session = await readServerAuthSession(request);

  if (session.status !== "authenticated") {
    return NextResponse.json(
      { signedIn: false, sessionKey: null },
      { headers: { "cache-control": "no-store, private" } },
    );
  }

  return NextResponse.json(
    { signedIn: true, sessionKey: subjectOf(session.accessToken) },
    { headers: { "cache-control": "no-store, private" } },
  );
}

/**
 * The token's `sub`, used only to notice that the account changed.
 *
 * Read without verifying, deliberately: nothing is authorised on the strength
 * of this value. Core verifies the token properly on every request, and this
 * only has to differ between two accounts. Returning null on anything
 * unexpected keeps a malformed token from becoming an exception.
 */
function subjectOf(token: string): string | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const claims: unknown = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (typeof claims !== "object" || claims === null) return null;
    const sub = (claims as Record<string, unknown>).sub;
    return typeof sub === "string" && sub ? sub : null;
  } catch {
    return null;
  }
}
