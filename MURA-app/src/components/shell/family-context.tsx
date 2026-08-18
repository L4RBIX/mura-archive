"use client";

/**
 * Whose archive am I looking at?
 *
 * Quiet by design. With one family this is a label, not a control: a
 * full-width switcher offering a single option is the "workspace picker" look
 * the product is explicitly not going for. A switcher appears only when there
 * is genuinely a choice.
 *
 * It states the signed-out and no-family cases too, because "which family"
 * having no answer is itself information the user needs.
 */

import { ChevronsUpDown } from "lucide-react";
import { useMuraI18n } from "@/lib/i18n";
import { useMuraSession } from "@/lib/mura/session-provider";

export function FamilyContext({ className }: { className?: string }) {
  const { t } = useMuraI18n();
  const { auth, family, phase, selectFamily } = useMuraSession();

  const base = className ?? "min-w-0";

  if (phase === "booting" || phase === "families_loading") {
    return (
      <div className={base} aria-hidden>
        <div className="h-3 w-20 animate-pulse rounded-full bg-sand" />
        <div className="mt-1.5 h-4 w-32 animate-pulse rounded-full bg-sand" />
      </div>
    );
  }

  const label = (text: string, muted = false) => (
    <div className={base}>
      <p className="text-caption font-semibold uppercase tracking-[0.1em] text-muted">
        {t("yourArchive")}
      </p>
      <p
        className={`truncate text-body font-semibold ${muted ? "text-muted" : "text-ink"}`}
        title={text}
      >
        {text}
      </p>
    </div>
  );

  if (auth.status !== "authenticated") return label(t("signedOutArchive"), true);
  if (!family.selectedFamily) return label(t("noFamilyYet"), true);

  // One family is a fact to state, not a menu to open.
  if (family.families.length < 2) return label(family.selectedFamily.name);

  return (
    <div className={base}>
      <label
        htmlFor="family-context-switcher"
        className="text-caption font-semibold uppercase tracking-[0.1em] text-muted"
      >
        {t("yourArchive")}
      </label>
      <div className="relative mt-0.5 flex items-center">
        <select
          id="family-context-switcher"
          value={family.selectedFamilyId ?? ""}
          onChange={(event) => selectFamily(event.target.value)}
          className="w-full cursor-pointer appearance-none truncate rounded-control bg-transparent pr-6 text-body font-semibold text-ink outline-none focus-ring"
        >
          {family.families.map((entry) => (
            <option key={entry.family_id} value={entry.family_id}>
              {entry.name}
            </option>
          ))}
        </select>
        <ChevronsUpDown
          aria-hidden
          className="pointer-events-none absolute right-0 size-3.5 shrink-0 text-muted"
        />
      </div>
    </div>
  );
}
