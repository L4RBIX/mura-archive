"use client";

/**
 * Account controls: who is signed in, and how to leave.
 *
 * Each provider ends its own session: Clerk through its own button, Supabase
 * by dropping the httpOnly cookie server-side. Routing one provider's
 * sign-out through another's leaves the session live and the user still
 * signed in after being told they left.
 *
 * Clerk's button clears its session cookie properly. That matters more than it looks: the server token cache is
 * keyed by Clerk session id and only ever read after `auth()` confirms the
 * session is live, so ending the session at the provider is what makes the
 * cached token unreachable. Nothing needs clearing in the browser, because the
 * browser never held a token in the first place.
 *
 * The user shown here is MURA's own `user_id` and profile metadata from
 * `/v1/me`, not Clerk's user object -- the app's notion of identity stays the
 * internal one.
 */

import { SignOutButton } from "@clerk/nextjs";
import { DevSignOutButton } from "@/components/auth/dev-auth-panel";
import { SupabaseSignOutButton } from "@/components/auth/supabase-sign-out";
import { useMuraI18n } from "@/lib/i18n";
import { useMuraSession } from "@/lib/mura/session-provider";

// Outlined, not `bg-sand`. Sand reads as a button on a raised card, but this
// group sits directly on paper now and #ece9e2 on #eee8df is not a visible
// edge — the control had stopped looking like one.
const SIGN_OUT_CLASS =
  "h-11 shrink-0 rounded-full border border-ink/20 px-5 text-meta font-semibold text-ink/75 focus-ring";

export function AccountSection() {
  const { t } = useMuraI18n();
  const { auth, provider } = useMuraSession();

  if (auth.status !== "authenticated") return null;

  return (
    // The «АККАУНТ» group label already names this section, so the card
    // heading that used to repeat it is gone along with the card.
    <section className="flex items-center justify-between gap-4">
      {/* `user_a78b1a9c…` is an internal identifier, not a name. When the
          provider supplies neither a display name nor an email there is
          nothing to call the user, and saying so plainly beats printing a
          developer-facing id at them. */}
      <p className="min-w-0 truncate text-body font-semibold">
        {auth.user.displayName ?? auth.user.email ?? t("accountSignedIn")}
      </p>
      {/* `SignOutButton` throws outside `<ClerkProvider>`, which the app does
          not mount when another provider is in force. Each provider ends its
          own session; nothing here reaches across that seam. */}
      {provider === "clerk" ? (
        <SignOutButton>
          <button type="button" className={SIGN_OUT_CLASS}>
            {t("signOut")}
          </button>
        </SignOutButton>
      ) : provider === "supabase" ? (
        <SupabaseSignOutButton className={SIGN_OUT_CLASS} />
      ) : (
        <DevSignOutButton className={SIGN_OUT_CLASS} />
      )}
    </section>
  );
}
