import Link from "next/link";
import type { ArchiveStorySummary } from "@/lib/mura/archive-api";

/**
 * One story in a list.
 *
 * The title is whatever extraction produced, and `untitled` when it produced
 * none — nothing here writes a headline for a family memory. The date shown is
 * when the story was recorded, which the archive genuinely knows, rather than
 * when the events happened, which it often does not.
 */
export function StoryLink({
  story,
  locale,
  untitled,
}: {
  story: ArchiveStorySummary;
  locale: string;
  untitled: string;
}) {
  return (
    <Link
      href={`/story/${encodeURIComponent(story.story_id)}`}
      className="block rounded-surface bg-raised p-4 transition-colors duration-200 hover:bg-sand focus-ring"
    >
      <p className="text-item font-semibold leading-snug">{story.title ?? untitled}</p>
      {/* Three lines is a preview. A 280-character excerpt at full height turns
          a list of memories into a wall of prose, especially on a phone where
          it fills the whole screen. */}
      {story.excerpt && (
        <p className="mt-1.5 line-clamp-3 text-body leading-relaxed text-ink/70">
          {story.excerpt}
        </p>
      )}
      <p className="mt-2 text-meta text-muted">
        {story.speaker_name} ·{" "}
        {new Date(story.recorded_at).toLocaleDateString(locale === "kk" ? "kk-KZ" : "ru-RU")}
      </p>
    </Link>
  );
}
