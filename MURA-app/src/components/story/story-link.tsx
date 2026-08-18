import Link from "next/link";
import { PersonAvatar } from "@/components/ui/person-avatar";
import type { TranslationKey } from "@/lib/i18n";
import type { ArchivePerson, ArchiveStorySummary } from "@/lib/mura/archive-api";
import { resolveStoryPeople } from "@/lib/mura/story-people";

/** How many people are named before the rest are counted. */
const VISIBLE_PEOPLE = 3;

export interface StoryLinkLabels {
  untitled: string;
  today: string;
  yesterday: string;
  thisWeek: string;
  /** `«и ещё {count}»`. */
  morePeople: (count: number) => string;
}

type Translate = (
  key: TranslationKey,
  vars?: Record<string, string | number>,
) => string;

/**
 * Built once per screen rather than per card, so three lists cannot drift into
 * three different words for the same thing.
 */
export function storyLinkLabels(t: Translate): StoryLinkLabels {
  return {
    untitled: t("storyUntitled"),
    today: t("storyToday"),
    yesterday: t("storyYesterday"),
    thisWeek: t("storyThisWeek"),
    morePeople: (count) => t("storyMorePeople", { count }),
  };
}

/**
 * One story in a list.
 *
 * The title is whatever extraction produced, and `untitled` when it produced
 * none — nothing here writes a headline for a family memory. The date shown is
 * when the story was recorded, which the archive genuinely knows, rather than
 * when the events happened, which it often does not.
 *
 * The card is no longer a single `<Link>` wrapper. `ArchiveStorySummary` has
 * always carried `person_ids` and the list threw them away, so a memory gave no
 * hint of who was in it; showing them means the card holds a link per person as
 * well as the link to the story, and an anchor inside an anchor is invalid.
 * The title carries a stretched link that covers the card, and the chips sit
 * above it — so the card is still one big target, and each chip is its own.
 */
export function StoryLink({
  story,
  locale,
  labels,
  /**
   * Canonical people from the archive, by `person_id`.
   *
   * A resolver rather than a name lookup, and deliberately optional: a caller
   * that has not loaded the family's people shows no chips instead of guessing.
   * An id with no person here is skipped — a mention the archive has not
   * resolved to anyone is not a person, and a placeholder chip would invent one.
   */
  peopleById,
}: {
  story: ArchiveStorySummary;
  locale: string;
  labels: StoryLinkLabels;
  peopleById?: ReadonlyMap<string, ArchivePerson>;
}) {
  const { shown, hidden } = resolveStoryPeople(story.person_ids, peopleById, VISIBLE_PEOPLE);

  return (
    <article className="relative rounded-surface bg-raised p-4 transition-colors duration-200 hover:bg-sand">
      <h3 className="text-item font-semibold leading-snug">
        <Link
          href={`/story/${encodeURIComponent(story.story_id)}`}
          className="rounded-surface after:absolute after:inset-0 after:content-[''] focus-ring"
        >
          {story.title ?? labels.untitled}
        </Link>
      </h3>

      {/* Three lines is a preview. A 280-character excerpt at full height turns
          a list of memories into a wall of prose, especially on a phone where
          it fills the whole screen. */}
      {story.excerpt && (
        <p className="mt-1.5 line-clamp-3 text-body leading-relaxed text-ink/70">
          {story.excerpt}
        </p>
      )}

      {shown.length > 0 && (
        <ul className="relative z-10 mt-2.5 flex flex-wrap items-center gap-1.5">
          {shown.map((person) => (
            <li key={person.person_id}>
              <Link
                href={`/person/${encodeURIComponent(person.person_id)}`}
                className="flex items-center gap-1.5 rounded-full bg-paper/70 py-1 pl-1 pr-2.5 text-caption font-medium text-ink/80 hover:bg-paper focus-ring"
              >
                <PersonAvatar
                  personId={person.person_id}
                  displayName={person.display_name}
                  size={20}
                />
                {/* Names are never truncated mid-word here: a shortened family
                    name is worse than a wrapped one. */}
                <span>{person.display_name}</span>
              </Link>
            </li>
          ))}
          {hidden > 0 && (
            <li className="text-caption text-muted">{labels.morePeople(hidden)}</li>
          )}
        </ul>
      )}

      <p className="mt-2 text-meta text-muted">
        {story.speaker_name} · {formatRecordedAt(story.recorded_at, locale, labels)}
      </p>
    </article>
  );
}

/**
 * When a memory was recorded, in words where words are clearer.
 *
 * Only the three cases a person actually reads as "recent" get a relative form.
 * Anything older keeps its date: «3 месяца назад» is a worse answer than
 * «18.08.2026» for an archive people scroll through years later, and rounding a
 * date into a vague phrase is the kind of small imprecision this product avoids.
 */
function formatRecordedAt(
  recordedAt: string,
  locale: string,
  labels: StoryLinkLabels,
): string {
  const recorded = new Date(recordedAt);
  const absolute = recorded.toLocaleDateString(locale === "kk" ? "kk-KZ" : "ru-RU");

  const startOfDay = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const days = Math.round((startOfDay(new Date()) - startOfDay(recorded)) / 86_400_000);

  if (days === 0) return labels.today;
  if (days === 1) return labels.yesterday;
  if (days > 1 && days < 7) return `${labels.thisWeek} · ${absolute}`;
  return absolute;
}
