/**
 * Clerk middleware.
 *
 * It establishes the request-scoped auth context that `auth()` reads; without
 * it the server adapter cannot see a session at all. It deliberately does *not*
 * protect routes by itself: authorization is Core's job, enforced against
 * PostgreSQL membership on every request, and a middleware allowlist that
 * disagreed with Core would be a second, weaker policy to keep in sync.
 *
 * The proxy still refuses unauthenticated calls on its own, so a request that
 * slips past middleware ordering cannot reach Core without a user token.
 */

import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { isClerkConfigured } from "@/lib/auth/providers/clerk/config";

/**
 * With no Clerk keys, `clerkMiddleware()` throws on every request and the app
 * would fail as an opaque 500. Passing requests through instead lets the proxy
 * answer `auth_provider_unconfigured`, which the UI already knows how to show.
 * Nothing is unlocked by this: the proxy refuses either way.
 */
export default isClerkConfigured() ? clerkMiddleware() : () => NextResponse.next();

export const config = {
  matcher: [
    // Everything except Next internals and static files, plus API routes.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
