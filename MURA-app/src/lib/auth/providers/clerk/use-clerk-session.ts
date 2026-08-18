"use client";

/**
 * The client half of the provider seam.
 *
 * The app needs to know two different things, and PR-03C collapsed them into
 * one: whether the *identity provider* has a session, and whether that identity
 * resolves to a MURA principal. Deriving the first from `/v1/me` alone was the
 * bug behind "signed in but the app still says signed out" -- `/v1/me` is only
 * fetched on mount, and signing in is a client-side navigation, so nothing ever
 * re-asked.
 *
 * This hook reports the provider's own view, and re-reports it the moment it
 * changes. The session provider watches it and re-resolves the MURA principal.
 * No Clerk type escapes this file.
 */

import { useAuth } from "@clerk/nextjs";

export interface ClerkSessionState {
  /** False until the provider has hydrated. Nothing may be concluded before it. */
  ready: boolean;
  signedIn: boolean;
  /** Provider-side session id. Only used to detect that the session changed. */
  sessionKey: string | null;
}

export function useClerkSession(): ClerkSessionState {
  const { isLoaded, isSignedIn, sessionId } = useAuth();
  return {
    ready: isLoaded,
    signedIn: Boolean(isSignedIn),
    sessionKey: sessionId ?? null,
  };
}
