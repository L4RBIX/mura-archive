"use client";

/**
 * The gate every family-scoped screen sits behind.
 *
 * It renders children only once there is a signed-in user *and* an authorized
 * family, so screens below can rely on `useSelectedFamily()` being present.
 *
 * The states it distinguishes are the point. "Still loading", "no provider
 * configured", "sign in", "you have no family yet" and "Core is unreachable"
 * are five different situations with five different remedies, and merging them
 * into one apology is how a login problem gets reported as an outage. Nothing
 * here renders a signed-out call to action until the session has actually
 * settled -- that flash was the "auth feels buggy" report.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { MascotStage } from "@/components/mascot/mascot-stage";
import { useMuraI18n } from "@/lib/i18n";
import { useMuraSession } from "@/lib/mura/session-provider";

function Notice({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div
      className="mx-auto flex min-h-dvh w-full max-w-measure flex-col items-center justify-center gap-3 px-6 text-center sm:px-8"
      role="status"
      aria-live="polite"
    >
      <p className="text-balance text-section font-semibold leading-snug">{title}</p>
      {hint && <p className="max-w-measure text-body leading-relaxed text-muted">{hint}</p>}
      {action}
    </div>
  );
}

/** A calm placeholder while the session settles, so nothing flashes. */
function Booting() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-8">
      <div className="size-12 animate-pulse rounded-full bg-clay/60" />
      <div className="h-3 w-40 animate-pulse rounded-full bg-raised" />
    </div>
  );
}

/**
 * Sign-in and sign-up, always offered together.
 *
 * The current path is carried through so the user returns to the screen they
 * wanted instead of being dumped somewhere unrelated.
 */
export function AuthActions({ className }: { className?: string }) {
  const { t } = useMuraI18n();
  const pathname = usePathname();
  const back = pathname && pathname.startsWith("/") ? pathname : "/home";
  const query = `?redirect_url=${encodeURIComponent(back)}`;

  return (
    <div className={className ?? "mt-2 flex flex-wrap items-center justify-center gap-2"}>
      {/* 44px, like every other secondary control in the product. These were
          41px — a height nobody chose, arrived at from padding plus a 14px
          label, and just under the touch-target floor. */}
      <Link
        href={`/sign-in${query}`}
        className="flex h-11 items-center rounded-full bg-clay px-5 text-meta font-semibold focus-ring"
      >
        {t("signIn")}
      </Link>
      <Link
        href={`/sign-up${query}`}
        className="flex h-11 items-center rounded-full bg-sand px-5 text-meta font-semibold text-ink/70 focus-ring"
      >
        {t("signUp")}
      </Link>
    </div>
  );
}

/**
 * The whole of family creation, and no more.
 *
 * Only `name` is sent because that is the only field Core accepts; the owner is
 * the authenticated principal and the body cannot name one.
 */
function CreateFamily() {
  const { t } = useMuraI18n();
  const { createFamily } = useMuraSession();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || name.trim().length === 0) return;
    setBusy(true);
    setFailed(false);
    try {
      // No reload afterwards: the provider re-reads the authorized list and
      // selects the new family, which unblocks the screen behind this gate.
      await createFamily(name.trim());
    } catch {
      setFailed(true);
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-form flex-col items-center justify-center px-6 sm:px-8">
      {/* First run is an emotional moment, not a form to dispatch. The swallow
          and the breathing room are the difference between "create a
          workspace" and "start your family archive". */}
      <MascotStage state="idle" size={200} className="mb-2" />
      <div className="w-full max-w-measure text-center">
        <h1 className="text-balance text-title font-bold leading-tight tracking-[-0.03em]">
          {t("noFamilyTitle")}
        </h1>
        <p className="mt-3 text-body leading-relaxed text-muted">{t("noFamilyHint")}</p>
        <form onSubmit={submit} className="mt-7 flex flex-col gap-3">
          <label htmlFor="family-name" className="sr-only">
            {t("familyNameLabel")}
          </label>
          <input
            id="family-name"
            name="family-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("familyNamePlaceholder")}
            maxLength={256}
            autoComplete="off"
            className="h-12 rounded-surface bg-raised px-4 text-body outline-none"
          />
          <button
            type="submit"
            disabled={busy || name.trim().length === 0}
            className="h-12 rounded-surface bg-clay text-body font-semibold shadow-soft disabled:opacity-50"
          >
            {busy ? t("creatingFamily") : t("createFamily")}
          </button>
        </form>
        {failed && (
          <p className="mt-3 text-meta leading-relaxed text-danger">
            {t("createFamilyFailed")}
          </p>
        )}
      </div>
    </div>
  );
}

export function FamilyGate({ children }: { children: ReactNode }) {
  const { t } = useMuraI18n();
  const { auth, family, phase } = useMuraSession();

  // Nothing is concluded until the session has settled. Rendering a signed-out
  // prompt here is what made the app flash "Войдите" on every load.
  if (phase === "booting" || phase === "families_loading") return <Booting />;

  if (auth.status === "provider_unconfigured") {
    return <Notice title={t("signInRequired")} hint={t("signInProviderPending")} />;
  }
  if (auth.status === "unauthenticated" || family.status === "auth_required") {
    return <Notice title={t("signInRequired")} action={<AuthActions />} />;
  }
  if (auth.status === "error") {
    return <Notice title={t("coreUnavailable")} hint={t("coreUnavailableHint")} />;
  }
  if (family.status === "error") {
    return <Notice title={t("familyLoadFailed")} hint={t("coreUnavailableHint")} />;
  }
  if (family.status === "no_families") return <CreateFamily />;
  if (!family.selectedFamily) return <Notice title={t("familyUnavailable")} />;

  return <>{children}</>;
}

/**
 * Family switcher. Rendered only when there is genuinely a choice.
 *
 * With one family there is nothing to pick, so the control does not appear at
 * all rather than showing a chooser with a single option.
 */
export function FamilySwitcher({ className }: { className?: string }) {
  const { t } = useMuraI18n();
  const { family, selectFamily } = useMuraSession();

  if (family.families.length < 2 || !family.selectedFamilyId) return null;

  return (
    <div className={className}>
      <label htmlFor="family-switcher" className="sr-only">
        {t("switchFamily")}
      </label>
      <select
        id="family-switcher"
        value={family.selectedFamilyId}
        onChange={(event) => selectFamily(event.target.value)}
        // Full width and 44px: this names the family whose memories the whole
        // app is about, and it was a 36px pill holding a name long enough to
        // reach the edge of a phone.
        className="h-11 w-full max-w-full rounded-control bg-raised px-3.5 text-body font-semibold outline-none focus-ring"
      >
        {family.families.map((entry) => (
          <option key={entry.family_id} value={entry.family_id}>
            {entry.name}
          </option>
        ))}
      </select>
    </div>
  );
}
