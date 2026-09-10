"use client";

import { useMuraI18n } from "@/lib/i18n";

/**
 * End a Supabase session.
 *
 * A form POST, not a link: a GET sign-out can be triggered by any image tag on
 * any page. The server drops the httpOnly cookie and redirects; nothing needs
 * clearing in the browser, because the browser never held a token.
 */
export function SupabaseSignOutButton({ className }: { className?: string }) {
  const { t } = useMuraI18n();
  return (
    <form action="/api/auth/sign-out" method="post" className="shrink-0">
      <button type="submit" className={className}>
        {t("signOut")}
      </button>
    </form>
  );
}
