import type { Metadata } from "next";
import { SignIn } from "@clerk/nextjs";
import { AuthFrame } from "@/components/auth/auth-frame";
import { safeRedirectPath } from "@/lib/auth/redirect";

export const metadata: Metadata = { title: "Sign in" };

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
  return (
    <AuthFrame>
      <SignIn
        signUpUrl={`/sign-up?redirect_url=${encodeURIComponent(destination)}`}
        fallbackRedirectUrl={destination}
      />
    </AuthFrame>
  );
}
