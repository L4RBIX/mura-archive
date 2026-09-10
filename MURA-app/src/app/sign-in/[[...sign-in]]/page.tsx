import type { Metadata } from "next";
import { SignIn } from "@clerk/nextjs";
import { AuthFrame } from "@/components/auth/auth-frame";
import { DevSignInPanel } from "@/components/auth/dev-auth-panel";
import { isClerkConfigured } from "@/lib/auth/providers/clerk/config";
import { isDevAuthAllowed } from "@/lib/auth/providers/dev/config";
import { isSupabaseAuthConfigured } from "@/lib/auth/providers/supabase/config";
import { SupabaseSignIn } from "@/components/auth/supabase-sign-in";
import { safeRedirectPath } from "@/lib/auth/redirect";

export const metadata: Metadata = { title: "Войти" };

/**
 * Clerk's own sign-in component.
 *
 * Deliberately not a hand-written credential form: password handling, MFA,
 * lockout and account recovery are exactly the things worth not reimplementing.
 * The methods offered are whatever the Clerk instance actually enables.
 */
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ redirect_url?: string }>;
}) {
  // The caller asked to come back somewhere; only a same-origin path is honoured.
  const destination = safeRedirectPath((await searchParams).redirect_url);
  // The local development issuer, when one is running. It is chosen by its own
  // gate and never because Clerk is missing, so an unconfigured deployment still
  // says it is unconfigured rather than growing a sign-in that mints identities.
  if (isDevAuthAllowed()) {
    return (
      <AuthFrame>
        <DevSignInPanel redirectTo={destination} />
      </AuthFrame>
    );
  }
  // Mirrors the provider order in `server-session.ts`: the page must not
  // offer a sign-in that resolves to a different provider than the proxy.
  if (isSupabaseAuthConfigured()) {
    return (
      <AuthFrame>
        <SupabaseSignIn redirectTo={destination} />
      </AuthFrame>
    );
  }
  if (!isClerkConfigured()) {
    return (
      <AuthFrame>
        <p className="text-body leading-relaxed text-ink/70">
          Вход ещё не подключён. Семейный архив откроется, когда появится вход.
        </p>
      </AuthFrame>
    );
  }
  return (
    <AuthFrame>
      <SignIn
        signUpUrl={`/sign-up?redirect_url=${encodeURIComponent(destination)}`}
        fallbackRedirectUrl={destination}
      />
    </AuthFrame>
  );
}
