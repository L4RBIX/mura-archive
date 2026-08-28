"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { notifyDevSessionChanged } from "@/lib/auth/providers/dev/use-dev-session";
import { useMuraI18n } from "@/lib/i18n";

/**
 * Sign-in for the local development issuer.
 *
 * It reads as the product's own sign-in, because it is on the screen where a
 * family decides whether to trust MURA and developer tooling has no business
 * being what they see. The one honest marker it keeps is a muted line at the
 * foot; see the comment beside it.
 *
 * There is deliberately no password field. Nothing could be checked against
 * one, and rendering an input that is ignored would be a straightforward lie
 * about a security property — the opposite of the point.
 */
export function DevSignInPanel({ redirectTo = "/home" }: { redirectTo?: string }) {
  const { t } = useMuraI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !email.trim()) return;
    setBusy(true);
    setFailed(null);
    try {
      const response = await fetch("/api/dev-auth/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setFailed(body?.error === "invalid_email" ? t("devAuthBadEmail") : t("devAuthFailed"));
        setBusy(false);
        return;
      }
      // The session provider watches this, so the whole app re-bootstraps
      // without a reload — the same behaviour the Clerk path has.
      notifyDevSessionChanged();
      router.push(redirectTo);
      router.refresh();
    } catch {
      setFailed(t("devAuthFailed"));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="w-full">
      <h1 className="text-title font-bold leading-[1.1] tracking-[-0.035em]">
        {t("devAuthTitle")}
      </h1>
      <p className="mt-3 max-w-[38ch] text-body leading-relaxed text-muted">
        {t("devAuthBody")}
      </p>

      <label htmlFor="dev-auth-email" className="mt-8 block text-meta font-medium">
        {t("devAuthEmailLabel")}
      </label>
      <input
        id="dev-auth-email"
        type="email"
        required
        autoComplete="email"
        autoFocus
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder="you@example.com"
        aria-describedby={failed ? "dev-auth-error" : undefined}
        aria-invalid={failed ? true : undefined}
        className="mt-2 h-[52px] w-full rounded-control border border-ink/15 bg-raised px-4 text-body outline-none transition-colors placeholder:text-muted/60 hover:border-ink/25 focus:border-ink/40 focus-ring"
      />

      {failed && (
        <p
          id="dev-auth-error"
          role="alert"
          className="mt-2.5 rounded-control bg-danger-surface px-3 py-2 text-meta text-danger"
        >
          {failed}
        </p>
      )}

      <Button type="submit" size="lg" className="mt-5 w-full" disabled={busy || !email.trim()}>
        {busy ? t("devAuthWorking") : t("devAuthSubmit")}
      </Button>

      {/*
        Honest, and quiet.
        
        This used to be a warning chip reading «ЛОКАЛЬНАЯ РАЗРАБОТКА» over a
        paragraph explaining that no password is checked — which made the
        product look like developer tooling on the one screen where a family is
        deciding whether to trust it.
        
        It cannot simply be deleted: a sign-in that checks nothing must not
        present itself as one that does. But the only person who can ever see
        this screen is someone who set `MURA_DEV_AUTH=true` themselves, so a
        single muted line at the foot is enough to be truthful. Normal users
        reach Clerk's form and never see this component at all.
      */}
      <p className="mt-6 flex items-center gap-2 text-caption text-muted">
        <span aria-hidden className="size-1.5 rounded-full bg-warning/70" />
        {t("devAuthDevNote")}
      </p>
    </form>
  );
}

/** Sign out of the development issuer. Mirrors Clerk's `SignOutButton`. */
export function DevSignOutButton({ className }: { className?: string }) {
  const { t } = useMuraI18n();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const signOut = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await fetch("/api/dev-auth/session", { method: "DELETE" });
    } finally {
      // The provider clears the departing account's local recordings when it
      // sees the session end, so this must fire even if the request failed —
      // otherwise the app keeps showing a session the server has dropped.
      notifyDevSessionChanged();
      router.push("/");
      router.refresh();
      setBusy(false);
    }
  };

  return (
    <button type="button" onClick={signOut} disabled={busy} className={className}>
      {t("signOut")}
    </button>
  );
}
