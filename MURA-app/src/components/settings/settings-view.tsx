"use client";

import { AccountSection } from "@/components/family/account-section";
import { AuthStrip } from "@/components/family/auth-strip";
import { FamilySwitcher } from "@/components/family/family-gate";
import { ScreenHeader } from "@/components/layout/screen-header";
import { LanguageSwitcher, useMuraI18n } from "@/lib/i18n";
import type { FamilyRole } from "@/lib/mura/core-api";
import { useMuraSession } from "@/lib/mura/session-provider";

const ROLE_KEY: Record<FamilyRole, "roleOwner" | "roleEditor" | "roleViewer"> = {
  owner: "roleOwner",
  editor: "roleEditor",
  viewer: "roleViewer",
};

/**
 * The current family, and a switcher when there is genuinely a choice.
 *
 * Deliberately not member administration: adding someone needs an invitation
 * lifecycle Core does not have, and inventing "add by email" here would create
 * memberships nobody agreed to.
 */
function FamilySection() {
  const { t } = useMuraI18n();
  const { family } = useMuraSession();
  const selected = family.selectedFamily;
  if (!selected) return null;
  // With several families the switcher already names the current one, so
  // printing it again above is the same fact twice.
  const switcherNamesIt = family.families.length > 1;

  return (
    <section>
      {switcherNamesIt ? (
        <FamilySwitcher />
      ) : (
        <p className="text-item font-semibold">{selected.name}</p>
      )}
      <p className="mt-2 text-meta text-muted">{t(ROLE_KEY[selected.role])}</p>
    </section>
  );
}

/**
 * Settings as a product page rather than a stack of cards.
 *
 * Sections are labelled so the page can be scanned, and the language control
 * lives here as well as in the chrome -- the rail is where you change it in
 * passing, this is where you look for it.
 *
 * Nothing unsupported is offered. There is no member administration because
 * Core has no invitation lifecycle, and inventing "add by email" would create
 * memberships nobody agreed to. The swallow holds one calm pose; the voice
 * preview she once fronted was removed with the rest of the assistant.
 */
/**
 * One group of settings: a label, a hairline, and the controls.
 *
 * This replaces three `rounded-panel bg-raised p-5` cards, each of which
 * opened by repeating its own section label as a heading — «АККАУНТ» above a
 * card headed «Аккаунт», «ЯЗЫК ИНТЕРФЕЙСА» above one headed «Язык интерфейса».
 * A settings page is a list of things you can change, not a set of panels, and
 * a rule costs less than a filled surface.
 */
function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-ink/[0.08] pt-4">
      <h2 className="text-caption font-semibold uppercase tracking-[0.18em] text-muted">
        {label}
      </h2>
      <div className="mt-3.5">{children}</div>
    </section>
  );
}

function LanguageSection() {
  const { t } = useMuraI18n();
  return (
    <>
      <div className="max-w-[320px]">
        <LanguageSwitcher variant="inline" />
      </div>
      <p className="mt-2.5 max-w-[46ch] text-meta leading-relaxed text-muted">
        {t("settingsLanguageHint")}
      </p>
    </>
  );
}

export function SettingsView() {
  const { t } = useMuraI18n();
  return (
    <div className="flex min-h-dvh flex-col">
      <ScreenHeader title={t("settings")} fallbackHref="/home" />

      <div className="mx-auto flex w-full max-w-[560px] flex-col gap-7 px-5 pb-[max(env(safe-area-inset-bottom),32px)] pt-2 sm:px-6 lg:px-8">
        {/* No demo archive sits below this screen, so it must not promise one. */}
        <AuthStrip hintKey="signInToSaveHintSettings" />

        <Group label={t("settingsFamily")}>
          <FamilySection />
        </Group>

        <Group label={t("settingsAccount")}>
          <AccountSection />
        </Group>

        <Group label={t("settingsLanguage")}>
          <LanguageSection />
        </Group>
      </div>
    </div>
  );
}
