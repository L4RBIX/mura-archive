"use client";

/**
 * Who is speaking, and what to ask them.
 *
 * Two things the record screen never had, and the reason it has room for them
 * now is that a 520px column on a 1440px window was leaving most of the screen
 * empty while the hardest part of using this product went unsupported.
 *
 * **Who is speaking** replaces a fabrication. `currentSpeakerName()` returned
 * the constant «Айсұлу» for every recording in every family, so every memory in
 * the archive was labelled «Со слов Айсұлу» whoever had actually spoken — an
 * invented family fact, written into permanent server data. A canonical
 * `person_id` is sent only when the user picks somebody the archive already
 * knows; a typed name is sent as a name alone and left for Core to resolve,
 * because the browser must never manufacture an identity.
 *
 * **What to ask** is a static human list, not generated. People find it hard to
 * start a conversation with a grandparent, and a question to hand does more for
 * that than any amount of interface.
 */

import { useState } from "react";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n, type TranslationKey } from "@/lib/i18n";
import type { ArchivePerson } from "@/lib/mura/archive-api";

/** Who the recording is of. `personId` only when the archive already knows them. */
export interface Speaker {
  name: string;
  personId: string | null;
}

const PROMPT_KEYS: TranslationKey[] = [
  "promptChildhoodHome",
  "promptFirstMemory",
  "promptParents",
  "promptMeeting",
  "promptHardYears",
  "promptHoliday",
  "promptFood",
  "promptAdvice",
];

export function RecordCompanion({
  people,
  speaker,
  onSpeakerChange,
  familyName,
}: {
  people: ArchivePerson[];
  speaker: Speaker | null;
  onSpeakerChange: (speaker: Speaker | null) => void;
  familyName: string | null;
}) {
  const { t } = useMuraI18n();
  const [typed, setTyped] = useState("");

  return (
    <div className="flex w-full flex-col gap-8 text-left">
      {/* Focus mode keeps the rail off this screen, which also removed every
          hint of which archive a recording is about to be written into. */}
      {familyName && (
        <p className="text-caption font-semibold uppercase tracking-[0.16em] text-muted">
          {familyName}
        </p>
      )}

      <section>
        <h2 className="text-item font-semibold">{t("recordWhoTitle")}</h2>
        <p className="mt-1 text-meta leading-relaxed text-muted">{t("recordWhoHint")}</p>

        {people.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {people.map((person) => {
              const active = speaker?.personId === person.person_id;
              return (
                <li key={person.person_id}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() =>
                      onSpeakerChange(
                        active
                          ? null
                          : { name: person.display_name, personId: person.person_id },
                      )
                    }
                    className={`flex items-center gap-2 rounded-full py-1.5 pl-1.5 pr-3.5 text-meta font-medium transition-colors focus-ring ${
                      active ? "bg-ink text-raised" : "bg-raised text-ink hover:bg-sand"
                    }`}
                  >
                    <PersonAvatar
                      personId={person.person_id}
                      displayName={person.display_name}
                      size={24}
                    />
                    {person.display_name}
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <label htmlFor="record-speaker" className="mt-4 block text-meta text-muted">
          {t("recordWhoOther")}
        </label>
        <input
          id="record-speaker"
          type="text"
          value={typed}
          maxLength={256}
          onChange={(event) => {
            const value = event.target.value;
            setTyped(value);
            // A typed name carries no canonical id. Core resolves it; the
            // browser does not decide that this is an existing person.
            onSpeakerChange(value.trim() ? { name: value.trim(), personId: null } : null);
          }}
          placeholder={t("recordWhoPlaceholder")}
          className="mt-1.5 h-11 w-full rounded-control bg-raised px-3.5 text-body outline-none focus-ring"
        />
      </section>

      <section>
        <h2 className="text-item font-semibold">{t("recordPromptsTitle")}</h2>
        <p className="mt-1 text-meta leading-relaxed text-muted">
          {t("recordPromptsHint")}
        </p>
        <ul className="mt-3 space-y-2">
          {PROMPT_KEYS.map((key) => (
            <li
              key={key}
              className="rounded-surface bg-raised/70 px-3.5 py-2.5 text-body leading-snug text-ink/80"
            >
              {t(key)}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
