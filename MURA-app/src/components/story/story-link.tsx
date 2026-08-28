import Link from "next/link";
import { PersonAvatar } from "@/components/ui/person-avatar";
import type { TranslationKey } from "@/lib/i18n";
import type { ArchivePerson, ArchiveStorySummary } from "@/lib/mura/archive-api";
import { resolveStoryPeople } from "@/lib/mura/story-people";
import { cn } from "@/lib/utils";

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
 * Built once per screen rather than per entry, so three lists cannot drift into
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
 * One memory in a list.
 *
 * ## Why this is not a card
 *
 * It was: a `rounded-surface bg-raised` box, repeated in a grid. Ten of them
 * produced a wall of identical rectangles with no hierarchy — every memory the
 * same size and weight as every other, which is the one thing a family archive
 * is not. A card also *contains*, and these do not need containing: they are
 * consecutive entries in a single archive, and a rule between them says that
 * more honestly than a border around each.
 *
 * So: an entry, separated by a hairline, with a title, a lead and a byline —
 * the structure of a printed collection. The hover state washes the row rather
 * than lifting a card, because nothing here is a floating object.
 *
 * ## Variation
 *
 * `lead` gives the most recent memory a larger setting. A list where the first
 * item is visibly the newest reads as an archive being added to; a list of
 * identical rows reads as a table. It is the same component and the same data,
 * set larger — not a second card design to keep in step with this one.
 *
 * The title is whatever extraction produced, and `untitled` when it produced
 * none: nothing here writes a headline for a family memory. The date is when
 * the story was recorded, which the archive genuinely knows, rather than when
 * the events happened, which it often does not.
 */
export function StoryLink({
  story,
  locale,
  labels,
  variant = "entry",
  /**
   * Canonical people from the archive, by `person_id`.
   *
   * A resolver rather than a name lookup, and deliberately optional: a caller
   * that has not loaded the family's people shows no faces instead of guessing.
   * An id with no person here is skipped — a mention the archive has not
   * resolved to anyone is not a person, and a placeholder would invent one.
   */
  peopleById,
}: {
  story: ArchiveStorySummary;
  locale: string;
  labels: StoryLinkLabels;
  variant?: "entry" | "lead";
  peopleById?: ReadonlyMap<string, ArchivePerson>;
}) {
  const { shown, hidden } = resolveStoryPeople(story.person_ids, peopleById, VISIBLE_PEOPLE);
  const isLead = variant === "lead";

  return (
    <article
      className={cn(
        // The negative margin lets the hover wash extend into the gutter, so
        // the row reads as a row rather than as a card that appeared on hover.
        "group relative -mx-3 rounded-surface px-3 transition-colors duration-200",
        "hover:bg-raised",
        isLead ? "py-5" : "py-4",
      )}
    >
      <h3
        className={cn(
          "font-semibold tracking-[-0.02em]",
          isLead ? "text-[clamp(1.5rem,2.4vw,1.9rem)] leading-[1.15]" : "text-item leading-snug",
        )}
      >
        <Link
          href={`/story/${encodeURIComponent(story.story_id)}`}
          className="rounded-surface after:absolute after:inset-0 after:content-[''] focus-ring"
        >
          {story.title ?? labels.untitled}
        </Link>
      </h3>

      {story.excerpt && (
        <p
          className={cn(
            "mt-2 max-w-[62ch] text-ink/70",
            isLead ? "line-clamp-3 text-reading leading-relaxed" : "line-clamp-2 text-body leading-relaxed",
          )}
        >
          {story.excerpt}
        </p>
      )}

      {/* Byline and faces on one line: who told it, when, and who is in it are
          three parts of the same sentence, not three stacked rows. */}
      <div className="relative z-10 mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="text-meta text-muted">
          <span className="font-medium text-ink/75">{story.speaker_name}</span>
          {" · "}
          {formatRecordedAt(story.recorded_at, locale, labels)}
        </p>

        {shown.length > 0 && (
          <ul className="flex items-center">
            {shown.map((person, index) => (
              <li
                key={person.person_id}
                // Overlapped, the way a group of faces actually sits. The ring
                // is the page colour, so each face reads as separate.
                className={cn("relative", index > 0 && "-ml-3.5")}
                style={{ zIndex: shown.length - index }}
              >
                <Link
                  href={`/person/${encodeURIComponent(person.person_id)}`}
                  title={person.display_name}
                  // Padded out to a 44px hit area around a 28px face: the faces
                  // must stay small enough to read as a byline, and still be
                  // tappable on a phone.
                  className="-m-2 block rounded-full p-2 transition-transform duration-200 hover:-translate-y-0.5 focus-ring"
                >
                  <PersonAvatar
                    personId={person.person_id}
                    displayName={person.display_name}
                    size={28}
                  />
                  <span className="sr-only">{person.display_name}</span>
                </Link>
              </li>
            ))}
            {hidden > 0 && (
              <li className="ml-2 text-caption text-muted">{labels.morePeople(hidden)}</li>
            )}
          </ul>
        )}
      </div>
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
  const absolute = recorded.toLocaleDateString(
    locale === "kk" ? "kk-KZ" : locale === "en" ? "en-GB" : "ru-RU",
    { day: "numeric", month: "long", year: "numeric" },
  );

  const startOfDay = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const days = Math.round((startOfDay(new Date()) - startOfDay(recorded)) / 86_400_000);

  if (days === 0) return labels.today;
  if (days === 1) return labels.yesterday;
  if (days > 1 && days < 7) return `${labels.thisWeek} · ${absolute}`;
  return absolute;
}
