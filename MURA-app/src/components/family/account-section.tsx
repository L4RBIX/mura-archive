"use client";

/**
 * Account controls: who is signed in, and how to leave.
 *
 * Sign-out goes through Clerk's own button so the provider clears its session
 * cookie properly. That matters more than it looks: the server token cache is
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
import { useMuraI18n } from "@/lib/i18n";
import { useMuraSession } from "@/lib/mura/session-provider";

export function AccountSection() {
  const { t } = useMuraI18n();
  const { auth } = useMuraSession();

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
      <SignOutButton>
        <button
          type="button"
          // Outlined, not `bg-sand`. Sand reads as a button on a raised card,
          // but this group sits directly on paper now and #ece9e2 on #eee8df
          // is not a visible edge — the control had stopped looking like one.
          className="h-11 shrink-0 rounded-full border border-ink/20 px-5 text-meta font-semibold text-ink/75 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink/40"
        >
          {t("signOut")}
        </button>
      </SignOutButton>
    </section>
  );
}
