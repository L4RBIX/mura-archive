"use client";

import Link from "next/link";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import type { ArchivePerson } from "@/lib/mura/archive-api";

/**
 * The people the archive knows most about.
 *
 * ## Why rows, not a grid
 *
 * This was a two- and three-column grid of avatar-plus-name cells. In a 300px
 * rail that gave each cell about 90px, so every name truncated to an initial
 * and a full stop — «А.», «Г..», «М.» — and the memory counts truncated to
 * «6…». A family archive listing its own family as single letters is the worst
 * possible failure on this screen, and it was invisible in a test suite.
 *
 * One column of rows. A name gets the full width of the rail, which is the
 * least this component owes it.
 *
 * Ordered by how many stories resolved to each canonical person, which is the
 * archive's own answer to "who does this family talk about" — never a
 * client-side tally of names that happen to appear in some text. Every person
 * is addressed by `person_id` throughout: two relatives share a name and one
 * relative has several spellings across Russian and Kazakh.
 */

/** Enough to recognise the family, short enough to stay a glance. */
const LIMIT = 5;

export function PeopleStrip({ people }: { people: ArchivePerson[] }) {
  const { t } = useMuraI18n();

  const featured = [...people]
    .sort((a, b) => b.story_count - a.story_count || a.display_name.localeCompare(b.display_name))
    .slice(0, LIMIT);

  if (featured.length === 0) return null;

  return (
    <section aria-labelledby="home-people">
      <div className="flex items-baseline justify-between gap-4">
        {/* A heading, not a label. The uppercase eyebrow this replaces said
            nothing the heading does not, in a size nobody can read. */}
        <h2 id="home-people" className="text-item font-semibold tracking-[-0.01em]">
          {t("homePeopleTitle")}
        </h2>
        <Link
          href="/tree"
          className="-mr-2 flex min-h-11 shrink-0 items-center rounded-control px-2 text-meta font-medium text-ink/65 underline decoration-ink/25 underline-offset-4 transition-colors hover:text-ink focus-ring"
        >
          {t("homePeopleAll")}
        </Link>
      </div>

      <ul className="mt-3 divide-y divide-ink/[0.07] border-t border-ink/[0.07]">
        {featured.map((person) => (
          <li key={person.person_id}>
            <Link
              href={`/person/${encodeURIComponent(person.person_id)}`}
              className="-mx-2 flex min-h-[52px] items-center gap-3 rounded-control px-2 transition-colors hover:bg-raised focus-ring"
            >
              <PersonAvatar
                personId={person.person_id}
                displayName={person.display_name}
                size={34}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body font-medium leading-tight">
                  {person.display_name}
                </span>
                {person.relation_to_speaker && (
                  <span className="block truncate text-caption text-muted">
                    {person.relation_to_speaker}
                  </span>
                )}
              </span>
              {/* The count sits at the end of the row as a figure, where it
                  cannot compete with the name and cannot be truncated by it. */}
              <span className="shrink-0 text-caption tabular-nums text-muted">
                {person.story_count}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
