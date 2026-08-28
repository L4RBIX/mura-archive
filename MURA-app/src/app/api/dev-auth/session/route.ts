import { NextResponse } from "next/server";
import { isDevAuthAllowed } from "@/lib/auth/providers/dev/config";
import {
  DEV_IDENTITY_COOKIE,
  decodeDevIdentity,
  encodeDevIdentity,
  subjectForEmail,
} from "@/lib/auth/providers/dev/identity-cookie";

/**
 * Sign in, sign out, and report who is signed in — for the development issuer.
 *
 * This is the local stand-in for Clerk's hosted flows. It exists so the whole
 * authenticated product can be exercised on a machine with no Clerk account,
 * against a Core that is doing genuine OIDC verification.
 *
 * Every method refuses with 404 when the provider is not allowed to run, so
 * these routes do not exist at all in a production build.
 */

const NOT_FOUND = NextResponse.json({ error: "not_found" }, { status: 404 });

function guard(): NextResponse | null {
  return isDevAuthAllowed() ? null : NOT_FOUND;
}

/** Who is signed in. The client session hook polls this; no token is returned. */
export async function GET(request: Request) {
  const refused = guard();
  if (refused) return refused;

  const cookie = request.headers
    .get("cookie")
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${DEV_IDENTITY_COOKIE}=`))
    ?.slice(DEV_IDENTITY_COOKIE.length + 1);

  const identity = decodeDevIdentity(cookie);
  if (!identity) {
    return NextResponse.json({ signedIn: false }, { headers: { "cache-control": "no-store" } });
  }

  return NextResponse.json(
    {
      signedIn: true,
      // The subject doubles as the session key the provider watches to
      // re-bootstrap on an account switch, so no separate id is invented.
      sessionKey: identity.subject,
      user: { email: identity.email, displayName: identity.displayName },
    },
    { headers: { "cache-control": "no-store" } },
  );
}

/** Sign in as an email address. Any address works; that is the point locally. */
export async function POST(request: Request) {
  const refused = guard();
  if (refused) return refused;

  let email = "";
  let displayName = "";
  try {
    const body = await request.json();
    email = typeof body?.email === "string" ? body.email.trim() : "";
    displayName = typeof body?.displayName === "string" ? body.displayName.trim() : "";
  } catch {
    return NextResponse.json({ error: "invalid_body" }, { status: 400 });
  }

  // Not validation theatre: an empty address would produce an identity with an
  // empty subject, and Core would resolve that to a user nobody meant.
  if (!email.includes("@") || email.length < 3) {
    return NextResponse.json({ error: "invalid_email" }, { status: 400 });
  }

  const identity = {
    subject: subjectForEmail(email),
    email: email.toLowerCase(),
    displayName: displayName || email.split("@")[0],
  };

  const response = NextResponse.json({ signedIn: true, user: identity });
  response.cookies.set(DEV_IDENTITY_COOKIE, encodeDevIdentity(identity), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    // Deliberately not `secure`: local development is http, and a secure cookie
    // would simply never be sent. This provider cannot run anywhere that is not
    // local, so there is no deployment for the flag to protect.
    secure: false,
    maxAge: 60 * 60 * 12,
  });
  return response;
}

/** Sign out. */
export async function DELETE() {
  const refused = guard();
  if (refused) return refused;

  const response = NextResponse.json({ signedIn: false });
  response.cookies.set(DEV_IDENTITY_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
