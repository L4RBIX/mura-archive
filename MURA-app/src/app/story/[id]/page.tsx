import type { Metadata } from "next";
import { StoryView } from "@/components/story/story-view";
import { LocalStoryView } from "@/components/story/local-story-view";

export const metadata: Metadata = { title: "Воспоминание" };

/**
 * A memory, addressed by canonical archive story id.
 *
 * `local-` ids are the browser's own drafts, saved before Core has finished
 * processing them. They stay on the local view: those are genuinely the user's
 * recordings, just not yet part of the archive.
 */
export default async function StoryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (id.startsWith("local-")) return <LocalStoryView memoryId={id} />;
  return <StoryView storyId={id} />;
}
