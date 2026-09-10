"use client";

/**
 * One place that answers "who is signed in, and which family are we in".
 *
 * The bug this rewrite fixes: the previous version resolved identity exactly
 * once, on mount. Signing in with Clerk is a client-side navigation, so the
 * provider never remounted and the app stayed "signed out" forever behind a
 * live Clerk session -- the impossible mixed state, and the real reason a
 * signed-in user could not reach the recorder. Only a hard refresh escaped it.
 *
 * Two sources of truth are now kept distinct instead of collapsed:
 *
 *   Clerk  -- is there a provider session at all?
 *   Core   -- does that identity resolve to a MURA principal, and to what?
 *
 * Both matter. Clerk saying "signed in" while Core has not yet provisioned the
 * user is a real, nameable state, not an error and not a logged-out user.
 *
 * The provider watches the Clerk session key, so sign-in, sign-out and session
 * switch each re-run the bootstrap without a page reload.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  UNCONFIGURED_CLERK_SESSION,
  useClerkSession,
  type ClerkSessionState,
} from "@/lib/auth/providers/clerk/use-clerk-session";
import { useDevSession } from "@/lib/auth/providers/dev/use-dev-session";
import { useSupabaseSession } from "@/lib/auth/providers/supabase/use-supabase-session";
import { sessionFromFailure, type AuthSession } from "@/lib/auth/session";
import {
  CoreRequestError,
  createFamily as createFamilyRequest,
  fetchCapabilities,
  fetchFamilies,
  fetchMe,
  type Capabilities,
  type FamilyView,
} from "@/lib/mura/core-api";
import {
  getMemoryOwner,
  purgeLocalRecordingsFor,
  setMemoryOwner,
} from "@/lib/memory-store";
import {
  INITIAL_FAMILY_SESSION,
  readRememberedFamilyId,
  rememberFamilyId,
  resolveFamilySession,
  selectFamily as selectFamilyState,
  type FamilySession,
} from "@/lib/mura/family-session";

/** Coarse phase of the bootstrap, for UI that must not guess from sub-states. */
export type SessionPhase =
  | "booting"
  | "signed_out"
  | "identity_loading"
  | "families_loading"
  | "ready"
  | "error";

interface MuraSession {
  /** Which identity provider is behind this session. Decided on the server. */
  provider: AuthProviderKind;
  auth: AuthSession;
  family: FamilySession;
  /** Product capabilities, or null until they resolve. Never blocks capture. */
  capabilities: Capabilities | null;
  /** True once capabilities have been attempted, so UI can stop guessing. */
  capabilitiesResolved: boolean;
  phase: SessionPhase;
  selectFamily: (familyId: string) => void;
  createFamily: (name: string) => Promise<FamilyView>;
  refreshFamilies: () => Promise<void>;
}

const SessionContext = createContext<MuraSession | null>(null);

function familyFailure(error: unknown): FamilySession {
  if (error instanceof CoreRequestError && (error.status === 401 || error.status === 403)) {
    return { ...INITIAL_FAMILY_SESSION, status: "auth_required" };
  }
  const code = error instanceof CoreRequestError ? error.api.code : "unexpected_response";
  return { ...INITIAL_FAMILY_SESSION, status: "error", errorCode: code };
}

function phaseOf(
  clerkReady: boolean,
  auth: AuthSession,
  family: FamilySession,
): SessionPhase {
  if (!clerkReady || auth.status === "loading") return "booting";
  if (auth.status === "unauthenticated" || auth.status === "provider_unconfigured") {
    return "signed_out";
  }
  if (auth.status === "error") return "error";
  if (family.status === "loading") return "families_loading";
  if (family.status === "error") return "error";
  if (family.status === "auth_required") return "signed_out";
  return "ready";
}

/**
 * Which identity provider the app is running behind.
 *
 * Resolved on the server and passed down, so the client never re-derives it and
 * the two can never disagree. `none` is a real, nameable state — a deployment
 * with no provider configured — and is not the same as signed out.
 */
export type AuthProviderKind = "clerk" | "dev" | "supabase" | "none";

export function MuraSessionProvider({
  children,
  provider = "none",
}: {
  children: ReactNode;
  /** Same decision the root layout makes when it wraps `<ClerkProvider>`. */
  provider?: AuthProviderKind;
}) {
  // Each branch is a distinct component rather than a conditional hook call:
  // `useClerkSession` must not run outside `<ClerkProvider>`, and `useDevSession`
  // must not run when there is no dev issuer to ask.
  if (provider === "clerk") {
    return <MuraSessionWithClerk>{children}</MuraSessionWithClerk>;
  }
  if (provider === "dev") {
    return <MuraSessionWithDevIssuer>{children}</MuraSessionWithDevIssuer>;
  }
  if (provider === "supabase") {
    return <MuraSessionWithSupabase>{children}</MuraSessionWithSupabase>;
  }
  return (
    <MuraSessionInner
      clerk={UNCONFIGURED_CLERK_SESSION}
      providerConfigured={false}
      provider="none"
    >
      {children}
    </MuraSessionInner>
  );
}

function MuraSessionWithSupabase({ children }: { children: ReactNode }) {
  const session = useSupabaseSession();
  return (
    <MuraSessionInner clerk={session} providerConfigured provider="supabase">
      {children}
    </MuraSessionInner>
  );
}

function MuraSessionWithDevIssuer({ children }: { children: ReactNode }) {
  const session = useDevSession();
  return (
    <MuraSessionInner clerk={session} providerConfigured provider="dev">
      {children}
    </MuraSessionInner>
  );
}

function MuraSessionWithClerk({ children }: { children: ReactNode }) {
  const clerk = useClerkSession();
  return (
    <MuraSessionInner clerk={clerk} providerConfigured provider="clerk">
      {children}
    </MuraSessionInner>
  );
}

function MuraSessionInner({
  children,
  clerk,
  providerConfigured,
  provider,
}: {
  children: ReactNode;
  clerk: ClerkSessionState;
  providerConfigured: boolean;
  provider: AuthProviderKind;
}) {
  const [auth, setAuth] = useState<AuthSession>(
    providerConfigured ? { status: "loading" } : { status: "provider_unconfigured" },
  );
  const [family, setFamily] = useState<FamilySession>(INITIAL_FAMILY_SESSION);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilitiesResolved, setCapabilitiesResolved] = useState(false);

  /** Guards against a late response from a previous session overwriting a newer one. */
  const generation = useRef(0);

  const applyFamilies = useCallback((families: FamilyView[]) => {
    // The remembered id is read here and validated inside, never trusted.
    setFamily(resolveFamilySession(families, readRememberedFamilyId()));
  }, []);

  const loadFamilies = useCallback(
    async (signal?: AbortSignal) => {
      try {
        applyFamilies(await fetchFamilies(signal));
      } catch (error) {
        if (signal?.aborted) return;
        setFamily(familyFailure(error));
      }
    },
    [applyFamilies],
  );

  useEffect(() => {
    if (!providerConfigured) {
      setAuth({ status: "provider_unconfigured" });
      setFamily(INITIAL_FAMILY_SESSION);
      setCapabilities(null);
      setCapabilitiesResolved(false);
      return;
    }

    // Nothing may be concluded until the provider has hydrated; concluding
    // early is what produced the "Войдите" flash on every load.
    if (!clerk.ready) return;

    const mine = ++generation.current;
    const controller = new AbortController();
    const current = () => generation.current === mine && !controller.signal.aborted;

    if (!clerk.signedIn) {
      // Signing out deletes the departing account's local recordings. The
      // store is pointed at nobody first, so any screen still mounted reads
      // empty immediately; then that account's own data is erased. Whoever
      // just left is the only account touched.
      const departing = getMemoryOwner();
      setMemoryOwner(null);
      setAuth({ status: "unauthenticated" });
      setFamily(INITIAL_FAMILY_SESSION);
      setCapabilities(null);
      setCapabilitiesResolved(false);
      void purgeLocalRecordingsFor(departing);
      return () => controller.abort();
    }

    // Identity is not known yet this generation, so nothing may be read from
    // the previous account's namespace in the meantime.
    setMemoryOwner(null);

    setAuth({ status: "loading" });
    setFamily({ ...INITIAL_FAMILY_SESSION, status: "loading" });

    (async () => {
      // Identity and families are independent once a Clerk session exists, so
      // they go together rather than in a waterfall. Capabilities are separate
      // on purpose: they describe the deployment, and a failure there must not
      // look like an auth failure.
      const [identity, families] = await Promise.allSettled([
        fetchMe(controller.signal),
        fetchFamilies(controller.signal),
      ]);
      if (!current()) return;

      if (identity.status === "rejected") {
        const error = identity.reason;
        setAuth(
          error instanceof CoreRequestError
            ? sessionFromFailure(error.status, error.api.code)
            : { status: "error", code: "unexpected_response" },
        );
        setFamily(familyFailure(error));
        return;
      }

      const me = identity.value;
      // Recordings are addressed by this id from here on. Signing in clears
      // only the legacy unowned data -- another account's namespace is left
      // alone, because someone else arriving is not a reason to destroy it.
      setMemoryOwner(me.user_id);
      void purgeLocalRecordingsFor(null);
      setAuth({
        status: "authenticated",
        user: { userId: me.user_id, email: me.email, displayName: me.display_name },
      });

      if (families.status === "fulfilled") applyFamilies(families.value);
      else setFamily(familyFailure(families.reason));

      try {
        const view = await fetchCapabilities(controller.signal);
        if (current()) setCapabilities(view);
      } catch {
        // Unknown capabilities are a real state, not an error worth surfacing
        // as one. Recording capture does not depend on this.
        if (current()) setCapabilities(null);
      } finally {
        if (current()) setCapabilitiesResolved(true);
      }
    })();

    return () => controller.abort();
  }, [providerConfigured, clerk.ready, clerk.signedIn, clerk.sessionKey, applyFamilies]);

  const selectFamily = useCallback((familyId: string) => {
    setFamily((currentSession) => {
      const next = selectFamilyState(currentSession, familyId);
      // Only persist a selection the server authorized.
      if (next.selectedFamilyId !== currentSession.selectedFamilyId) {
        rememberFamilyId(next.selectedFamilyId);
      }
      return next;
    });
  }, []);

  const createFamily = useCallback(async (name: string) => {
    const created = await createFamilyRequest(name);
    // Re-read rather than appending locally, so the authorized list stays the
    // server's answer and the new family is selected without a reload.
    const families = await fetchFamilies();
    setFamily(resolveFamilySession(families, created.family_id));
    rememberFamilyId(created.family_id);
    return created;
  }, []);

  const refreshFamilies = useCallback(async () => {
    await loadFamilies();
  }, [loadFamilies]);

  const phase = phaseOf(clerk.ready, auth, family);

  const value = useMemo<MuraSession>(
    () => ({
      provider,
      auth,
      family,
      capabilities,
      capabilitiesResolved,
      phase,
      selectFamily,
      createFamily,
      refreshFamilies,
    }),
    [
      provider,
      auth,
      family,
      capabilities,
      capabilitiesResolved,
      phase,
      selectFamily,
      createFamily,
      refreshFamilies,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useMuraSession(): MuraSession {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useMuraSession must be used inside MuraSessionProvider");
  return value;
}

/**
 * The family the app is currently acting in, or null.
 *
 * Null is a real answer -- signed out, or authorized for no family -- and
 * callers must treat it as "do not issue a family-scoped request" rather than
 * substituting anything.
 */
export function useSelectedFamily(): FamilyView | null {
  return useMuraSession().family.selectedFamily;
}
