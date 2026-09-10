"use client";

import { useEffect, useState } from "react";
import type { ClerkSessionState } from "@/lib/auth/providers/clerk/use-clerk-session";

/**
 * Supabase's client-side session state.
 *
 * The same shape the Clerk and dev hooks return, so `MuraSessionProvider`
 * consumes one type and never branches on which provider is behind it.
 *
 * It asks the server rather than reading a cookie, because the session cookie
 * is `httpOnly` — which is the whole reason no token is readable by script on
 * the page.
 */
export function useSupabaseSession(): ClerkSessionState {
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
        const response = await fetch("/api/auth/session", {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error("session unavailable");
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
        // answer is not a session, and leaving the app on its splash forever is
        // the worse failure.
        setState({ ready: true, signedIn: false, sessionKey: null });
      }
    }

    void read();
    // A tab that was open across a sign-in elsewhere re-reads when refocused.
    const onFocus = () => void read();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      controller.abort();
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  return state;
}
