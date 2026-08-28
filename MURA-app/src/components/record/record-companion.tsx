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
import { useMuraI18n } from "@/lib/i18n";
import type { ArchivePerson } from "@/lib/mura/archive-api";
import { promptsForRole, useNarratorRole } from "@/lib/mura/narrator-role";

/** Who the recording is of. `personId` only when the archive already knows them. */
export interface Speaker {
  name: string;
  personId: string | null;
}

/**
 * Three at a time, not eight.
 *
 * The panel listed every prompt it had, which turned the companion into a wall
 * of eight cards beside the microphone — the list dominated the screen whose
 * subject is a person about to speak. Three is a choice; eight is a menu to
 * read, at the moment somebody is trying to stop reading and start talking.
 */
const VISIBLE_PROMPTS = 3;

/** People shown before the list asks to be expanded. */
const VISIBLE_PEOPLE = 6;

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
  const { role } = useNarratorRole();
  const [typed, setTyped] = useState("");
  const [allPeople, setAllPeople] = useState(false);
  /** Which window of the prompt list is on screen. «Ещё идеи» advances it. */
  const [promptPage, setPromptPage] = useState(0);

  const ordered = promptsForRole(role);
  const start = (promptPage * VISIBLE_PROMPTS) % ordered.length;
  const prompts = [...ordered, ...ordered].slice(start, start + VISIBLE_PROMPTS);

  const shownPeople = allPeople ? people : people.slice(0, VISIBLE_PEOPLE);

  return (
    <div className="flex w-full flex-col gap-8 text-left">
      {/* Focus mode keeps the rail off this screen, which also removed every
          hint of which archive a recording is about to be written into. */}
      {familyName && (
        <p className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
          {familyName}
        </p>
      )}

      <section>
        <h2 className="text-item font-semibold">{t("recordWhoTitle")}</h2>
        <p className="mt-1 text-meta leading-relaxed text-muted">{t("recordWhoHint")}</p>

        {people.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {shownPeople.map((person) => {
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
                    className={`flex min-h-11 items-center gap-2 rounded-full py-1.5 pl-1.5 pr-4 text-meta font-medium transition-colors focus-ring ${
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
            {!allPeople && people.length > VISIBLE_PEOPLE && (
              <li>
                <button
                  type="button"
                  onClick={() => setAllPeople(true)}
                  className="flex min-h-11 items-center rounded-full px-3 text-meta font-medium text-ink/65 underline decoration-ink/25 underline-offset-4 hover:text-ink focus-ring"
                >
                  {t("recordShowAllPeople")}
                </button>
              </li>
            )}
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
        {/* Rules, not cards: three consecutive suggestions are a list, and a
            box around each was three more containers on a screen that wants
            fewer things to look at. */}
        <ul className="mt-3 divide-y divide-ink/[0.08] border-y border-ink/[0.08]">
          {prompts.map((key) => (
            <li key={key} className="py-3 text-body leading-snug text-ink/80">
              {t(key)}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => setPromptPage((page) => page + 1)}
          className="mt-3 flex min-h-11 items-center text-meta font-medium text-ink/65 underline decoration-ink/25 underline-offset-4 transition-colors hover:text-ink focus-ring"
        >
          {t("recordMoreIdeas")}
        </button>
      </section>
    </div>
  );
}
