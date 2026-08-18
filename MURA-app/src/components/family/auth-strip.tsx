"use client";

/**
 * The signed-out banner on otherwise-public screens.
 *
 * Sign-in used to be reachable only by walking into a gated screen and reading
 * a notice, which is why it was reported as effectively absent: `/home` is
 * where people land, and it offered no way in at all. This puts the two
 * actions where they are visible without turning the home screen into a login
 * wall — the demo content below it still reads fine while signed out.
 *
 * It renders nothing while the session is still settling, so the page does not
 * flash a sign-in prompt at an already-signed-in user, and nothing once signed
 * in, so it costs a signed-in user no space.
 */

import { AuthActions } from "@/components/family/family-gate";
import { useMuraI18n, type TranslationKey } from "@/lib/i18n";
import { useMuraSession } from "@/lib/mura/session-provider";

export function AuthStrip({
  className,
  hintKey,
}: {
  className?: string;
  /**
   * A second line, only where it says something the title does not.
   *
   * On `/home` there is no hint: the title is already «Войдите, чтобы
   * записывать воспоминания» and the paragraph under it read «Войдите, чтобы
   * открыть семейный архив и записывать воспоминания» — the same sentence
   * twice, one of them longer. `/settings` passes its own, because there the
   * strip is the whole screen and what sign-in unlocks genuinely differs.
   */
  hintKey?: TranslationKey;
}) {
  const { t } = useMuraI18n();
  const { auth, phase } = useMuraSession();

  // Clerk hydrates on the client, so the server render cannot yet know whether
  // anyone is signed in. A neutral placeholder holds the space instead of a
  // sign-in prompt, so the layout does not jump and a signed-in user is never
  // shown a login call to action that then disappears.
  if (phase === "booting") {
    return (
      <div
        className={className ?? "mb-8 rounded-panel bg-raised p-5"}
        aria-hidden
      >
        <div className="h-4 w-48 animate-pulse rounded-full bg-sand" />
        <div className="mt-2 h-3 w-full animate-pulse rounded-full bg-sand/70" />
      </div>
    );
  }
  if (auth.status === "authenticated") return null;

  const unconfigured = auth.status === "provider_unconfigured";

  return (
    <div className={className ?? "mb-8 rounded-panel bg-raised p-5"}>
      <p className="text-item font-semibold leading-snug">{t("signInToSave")}</p>
      {(unconfigured || hintKey) && (
        <p className="mt-1.5 max-w-[52ch] text-meta leading-relaxed text-muted">
          {unconfigured ? t("signInProviderPending") : t(hintKey as TranslationKey)}
        </p>
      )}
      {!unconfigured && <AuthActions className="mt-4 flex flex-wrap gap-2" />}
    </div>
  );
}
