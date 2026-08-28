"use client";

import { useEffect, useState } from "react";
import type { ClerkSessionState } from "@/lib/auth/providers/clerk/use-clerk-session";

/**
 * The development issuer's client-side session state.
 *
 * Deliberately the same shape the Clerk hook returns, so `MuraSessionProvider`
 * consumes one type and never branches on which provider is behind it — the
 * seam that already exists on the server, mirrored on the client.
 *
 * It asks the server rather than reading a cookie, because the identity cookie
 * is `httpOnly`. That is a little more work than parsing `document.cookie` and
 * it is the reason no token or identity material is readable by script on the
 * page.
 */

/** Fired after sign-in or sign-out so the hook re-reads without a reload. */
export const DEV_SESSION_CHANGED_EVENT = "mura:dev-session-changed";

export function notifyDevSessionChanged(): void {
  window.dispatchEvent(new Event(DEV_SESSION_CHANGED_EVENT));
}

export function useDevSession(): ClerkSessionState {
  const [state, setState] = useState<ClerkSessionState>({
    ready: false,
    signedIn: false,
    sessionKey: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function read() {
      try {
        const response = await fetch("/api/dev-auth/session", {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error("dev session unavailable");
        const body = await response.json();
        if (cancelled) return;
        setState({
          ready: true,
          signedIn: Boolean(body?.signedIn),
          sessionKey: typeof body?.sessionKey === "string" ? body.sessionKey : null,
        });
      } catch {
        if (cancelled) return;
        // Ready but signed out, not stuck booting: an endpoint that cannot
        // answer is not a session, and leaving the app on its splash forever
        // is the worse failure.
        setState({ ready: true, signedIn: false, sessionKey: null });
      }
    }

    void read();
    const onChange = () => void read();
    window.addEventListener(DEV_SESSION_CHANGED_EVENT, onChange);
    return () => {
      cancelled = true;
      controller.abort();
      window.removeEventListener(DEV_SESSION_CHANGED_EVENT, onChange);
    };
  }, []);

  return state;
}
