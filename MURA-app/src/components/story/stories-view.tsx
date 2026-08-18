"use client";

import { useCallback } from "react";
import { ArchiveState } from "@/components/archive/archive-state";
import { FamilyGate } from "@/components/family/family-gate";
import { AppHeader } from "@/components/layout/app-header";
import { PageContainer } from "@/components/shell/page-container";
import { StoryLink } from "@/components/story/story-link";
import { Button } from "@/components/ui/button";
import { useMuraI18n } from "@/lib/i18n";
import Link from "next/link";
import { fetchArchiveStories, type ArchiveStoryPage } from "@/lib/mura/archive-api";
import { useArchiveResource } from "@/lib/mura/use-archive";

/**
 * Every memory in the family archive, newest first.
 *
 * Ordered by when the story was recorded, which the archive knows, rather than
 * by when the events happened, which it usually does not. Inventing a
 * chronology for undated memories would put a false history on a family.
 *
 * The first page only. A family archive is meant to grow for years, so the
 * endpoint pages and this asks for a bounded slice.
 */
function StoriesContent() {
  const { t, locale } = useMuraI18n();
  const load = useCallback(
    (familyId: string, signal: AbortSignal) =>
      fetchArchiveStories(familyId, { limit: 30, signal }),
    [],
  );
  const stories = useArchiveResource<ArchiveStoryPage>(load);

  return (
    <div className="pb-16">
      <AppHeader title={t("storiesTitle")} fallbackHref="/home" />

      <ArchiveState
        resource={stories}
        loadingLabel={t("storiesLoading")}
        isEmpty={(stories.data?.items.length ?? 0) === 0}
        empty={
          <PageContainer>
            <div className="mx-auto max-w-[46ch] py-14 text-center">
              <h1 className="text-balance text-section font-bold leading-snug tracking-[-0.02em]">
                {t("storiesEmptyTitle")}
              </h1>
              <p className="mt-2.5 text-body leading-relaxed text-muted">
                {t("storiesEmptyBody")}
              </p>
              <Button asChild size="lg" className="mt-6">
                <Link href="/record">{t("recordMemory")}</Link>
              </Button>
            </div>
          </PageContainer>
        }
      >
        <PageContainer>
          <ul className="space-y-2.5 pt-1">
            {stories.data?.items.map((story) => (
              <li key={story.story_id}>
                <StoryLink story={story} locale={locale} untitled={t("storyUntitled")} />
              </li>
            ))}
          </ul>
        </PageContainer>
      </ArchiveState>
    </div>
  );
}

export function StoriesView() {
  return (
    <FamilyGate>
      <StoriesContent />
    </FamilyGate>
  );
}
