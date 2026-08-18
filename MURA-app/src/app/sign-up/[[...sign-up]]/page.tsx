import type { Metadata } from "next";
import { SignUp } from "@clerk/nextjs";
import { AuthFrame } from "@/components/auth/auth-frame";
import { safeRedirectPath } from "@/lib/auth/redirect";

export const metadata: Metadata = { title: "Создать аккаунт" };

/**
 * Signing up creates a Clerk account and nothing else.
 *
 * Core provisions the MURA UserRow on the first authenticated request, keyed by
 * issuer + subject. It does not create a family, and it emphatically does not
 * create an archive Person -- an account is not a person in the family tree.
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
      <SignUp
        signInUrl={`/sign-in?redirect_url=${encodeURIComponent(destination)}`}
        fallbackRedirectUrl={destination}
      />
    </AuthFrame>
  );
}
