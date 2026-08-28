"use client";

import Link from "next/link";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import type { ArchivePerson } from "@/lib/mura/archive-api";
import { promptsForRole, useNarratorRole } from "@/lib/mura/narrator-role";

/**
 * A reason to come back tomorrow.
 *
 * ## The honesty problem this solves
 *
 * The obvious version of this is «Вы ещё не рассказывали о доме, где прошло
 * ваше детство» — a claim about what is missing from the archive. MURA cannot
 * know that. Deciding it would mean matching a topic against transcript text,
 * which is the same name-matching this codebase rejects everywhere else, and
 * being wrong would mean telling a family they never mentioned something they
 * spent an hour on.
 *
 * So it is built from the one fact the archive can prove: `story_count === 0`
 * on a canonical person. The archive knows this person exists — extraction
 * resolved them from something somebody actually said — and holds no story
 * about them. That is checkable, specific, and the most affecting thing this
 * screen can say, because the people with no stories are usually the ones who
 * are gone.
 *
 * When every known person has a story, it falls back to offering a question
 * rather than asserting an absence. A suggestion is honest; a false claim
 * about someone's own family is not.
 */
export function NextMemory({ people }: { people: ArchivePerson[] }) {
  const { t } = useMuraI18n();
  const { role } = useNarratorRole();

  // Stable across renders: the first, by the archive's own ordering, rather
  // than a random pick that changes under the user on every navigation.
  const unwritten = people.find((person) => person.story_count === 0) ?? null;

  if (unwritten) {
    return (
      <section aria-labelledby="home-next">
        <h2 id="home-next" className="text-item font-semibold tracking-[-0.01em]">
          {t("homeNextTitle")}
        </h2>

        <div className="mt-3 rounded-surface border border-ink/[0.08] bg-raised p-4">
          <div className="flex items-start gap-3">
            <PersonAvatar
              personId={unwritten.person_id}
              displayName={unwritten.display_name}
              size={40}
            />
            <p className="min-w-0 text-body leading-relaxed text-ink/80">
              {t("homeNoStoriesAbout", { name: unwritten.display_name })}
            </p>
          </div>

          <Link
            href="/record"
            className="mt-4 flex min-h-11 items-center justify-center rounded-full bg-ink px-4 text-meta font-semibold text-raised transition-transform duration-200 active:scale-[0.98] focus-ring"
          >
            {t("homeTellAbout", { name: unwritten.display_name })}
          </Link>
        </div>
      </section>
    );
  }

  // Nothing provable to point at, so this offers a question instead of
  // claiming an absence.
  const [prompt] = promptsForRole(role, 1);
  return (
    <section aria-labelledby="home-next">
      <h2 id="home-next" className="text-item font-semibold tracking-[-0.01em]">
        {t("homeNextTitle")}
      </h2>
      <div className="mt-3 rounded-surface border border-ink/[0.08] bg-raised p-4">
        <p className="text-body leading-relaxed text-ink/85">{t(prompt)}</p>
        <p className="mt-1.5 text-meta text-muted">{t("homeNextIdea")}</p>
        <Link
          href="/record"
          className="mt-4 flex min-h-11 items-center justify-center rounded-full bg-ink px-4 text-meta font-semibold text-raised transition-transform duration-200 active:scale-[0.98] focus-ring"
        >
          {t("recordMemory")}
        </Link>
      </div>
    </section>
  );
}
