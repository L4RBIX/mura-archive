"use client";

import { AccountSection } from "@/components/family/account-section";
import { AuthStrip } from "@/components/family/auth-strip";
import { FamilySwitcher } from "@/components/family/family-gate";
import { AppHeader } from "@/components/layout/app-header";
import { MembersSection } from "@/components/settings/members-section";
import { PageContainer } from "@/components/shell/page-container";
import { LanguageSwitcher, useMuraI18n } from "@/lib/i18n";
import { AUDIO_LANGUAGE_OPTIONS, useAudioLanguage } from "@/lib/mura/audio-language";
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

/** The index down the side, and the anchors it points at. */
const SECTIONS = [
  { id: "settings-family", labelKey: "settingsFamily" },
  { id: "settings-members", labelKey: "settingsMembers" },
  { id: "settings-account", labelKey: "settingsAccount" },
  { id: "settings-language", labelKey: "settingsLanguage" },
  { id: "settings-audio-language", labelKey: "settingsAudioLanguage" },
  { id: "settings-privacy", labelKey: "settingsPrivacy" },
] as const;

/**
 * One group of settings: a label, a hairline, and the controls.
 *
 * This replaced three `rounded-panel bg-raised p-5` cards, each of which opened
 * by repeating its own section label as a heading — «АККАУНТ» above a card
 * headed «Аккаунт». A settings page is a list of things you can change, not a
 * set of panels, and a rule costs less than a filled surface.
 */
function Group({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-6 border-t border-ink/[0.08] pt-4">
      <h2 className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
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
      {/* A control's width, not a content width: the segmented language toggle
          stretches to its container, and a 560px-wide row of three-letter
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

/**
 * What MURA should expect to hear.
 *
 * A separate group from the interface language on purpose, and each states that
 * it does not affect the other. Before this, the value existed in the types but
 * had no control anywhere in the product, so a Kazakh-speaking family had no way
 * to say what they were about to speak.
 *
 * A radio group rather than a segmented toggle: these are four sentences, not
 * four abbreviations, and the longest of them does not fit in a pill.
 */
function AudioLanguageSection() {
  const { t } = useMuraI18n();
  const { audioLanguage, setAudioLanguage } = useAudioLanguage();

  return (
    <>
      <fieldset className="max-w-form">
        <legend className="sr-only">{t("settingsAudioLanguage")}</legend>
        <div className="flex flex-col gap-1">
          {AUDIO_LANGUAGE_OPTIONS.map((option) => {
            const checked = audioLanguage === option.value;
            return (
              <label
                key={option.value}
                className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-control px-3 py-2 transition-colors ${
                  checked ? "bg-sand" : "hover:bg-sand/60"
                }`}
              >
                <input
                  type="radio"
                  name="audio-language"
                  value={option.value}
                  checked={checked}
                  onChange={() => setAudioLanguage(option.value)}
                  className="size-4 shrink-0 accent-[var(--color-ink)] focus-ring"
                />
                <span className="text-body">{t(option.labelKey)}</span>
              </label>
            );
          })}
        </div>
      </fieldset>
      <p className="mt-2.5 max-w-[46ch] text-meta leading-relaxed text-muted">
        {t("settingsAudioLanguageHint")}
      </p>
    </>
  );
}

/**
 * What the family can expect about who sees what.
 *
 * Every statement here is one the product actually keeps: family-scoped access
 * enforced against the database per request, role capabilities from the policy
 * table, owner-scoped local drafts purged on sign-out. Invitations are named as
 * missing rather than described as though they worked — a privacy page that
 * promised sharing controls that do not exist would be the worst place in the
 * product to be aspirational.
 */
function PrivacySection() {
  const { t } = useMuraI18n();
  const entries = [
    { titleKey: "privacyWhoSeesTitle", bodyKey: "privacyWhoSeesBody" },
    { titleKey: "privacyAudioTitle", bodyKey: "privacyAudioBody" },
    { titleKey: "privacyLocalTitle", bodyKey: "privacyLocalBody" },
    { titleKey: "privacySharingTitle", bodyKey: "privacySharingBody" },
  ] as const;

  return (
    <div className="flex max-w-form flex-col gap-5">
      {entries.map((entry) => (
        <div key={entry.titleKey}>
          <h3 className="text-body font-semibold">{t(entry.titleKey)}</h3>
          <p className="mt-1 max-w-[52ch] text-meta leading-relaxed text-muted">
            {t(entry.bodyKey)}
          </p>
        </div>
      ))}

      <div>
        <h3 className="text-body font-semibold">{t("privacyRolesTitle")}</h3>
        <ul className="mt-1.5 max-w-[52ch] space-y-1.5">
          {(["privacyRoleOwnerBody", "privacyRoleEditorBody", "privacyRoleViewerBody"] as const).map(
            (key) => (
              <li key={key} className="flex gap-2.5 text-meta leading-relaxed text-muted">
                <span aria-hidden className="mt-[0.62em] size-1 shrink-0 rounded-full bg-muted/60" />
                <span>{t(key)}</span>
              </li>
            ),
          )}
        </ul>
      </div>
    </div>
  );
}

export function SettingsView() {
  const { t } = useMuraI18n();
  return (
    <div className="flex min-h-dvh flex-col">
      <AppHeader title={t("settings")} fallbackHref="/home" width="wide" />

      {/*
        Settings is a form column on a phone and a form column on a 1920px
        window, which is the one place where that is nearly right — but it left
        the page with no way to see its own shape. From `lg` the section names
        become a standing index beside the content instead of milestones you
        scroll past.
      */}
      <PageContainer
        width="wide"
        className="pb-[max(env(safe-area-inset-bottom),32px)] pt-2 lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-12 xl:gap-16"
      >
        <nav aria-label={t("settings")} className="hidden lg:block">
          <ul className="sticky top-6 space-y-1">
            {SECTIONS.map((section) => (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  className="flex min-h-11 items-center rounded-control px-3 text-body text-ink/70 transition-colors hover:bg-sand hover:text-ink focus-ring"
                >
                  {t(section.labelKey)}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex max-w-form flex-col gap-7">
          {/* No demo archive sits below this screen, so it must not promise one. */}
          <AuthStrip hintKey="signInToSaveHintSettings" />

          <Group id="settings-family" label={t("settingsFamily")}>
            <FamilySection />
          </Group>

          <Group id="settings-members" label={t("settingsMembers")}>
            <MembersSection />
          </Group>

          <Group id="settings-account" label={t("settingsAccount")}>
            <AccountSection />
          </Group>

          <Group id="settings-language" label={t("settingsLanguage")}>
            <LanguageSection />
          </Group>

          {/* Its own group, directly below the interface language and never
              merged into it. Two adjacent groups that each say they do not
              affect the other is the clearest the distinction can be made. */}
          <Group id="settings-audio-language" label={t("settingsAudioLanguage")}>
            <AudioLanguageSection />
          </Group>

          <Group id="settings-privacy" label={t("settingsPrivacy")}>
            <PrivacySection />
          </Group>
        </div>
      </PageContainer>
    </div>
  );
}
