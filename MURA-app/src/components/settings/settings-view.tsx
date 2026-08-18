"use client";

import { AccountSection } from "@/components/family/account-section";
import { AuthStrip } from "@/components/family/auth-strip";
import { FamilySwitcher } from "@/components/family/family-gate";
import { AppHeader } from "@/components/layout/app-header";
import { PageContainer } from "@/components/shell/page-container";
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
      {/* A control's width, not a content width: the segmented RU/KK toggle
          stretches to its container, and a 560px-wide pair of two-letter
          buttons looks like a mistake. Deliberately not a container token. */}
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
      <AppHeader title={t("settings")} fallbackHref="/home" width="form" />

      {/* Settings used to declare `max-w-[560px]` and its own gutter, which is
          how the product ended up with a third content width nobody chose.
          The width is now a name from the container's list. */}
      <PageContainer
        width="form"
        className="flex flex-col gap-7 pb-[max(env(safe-area-inset-bottom),32px)] pt-2"
      >
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
      </PageContainer>
    </div>
  );
}
