"use client";

import { useCallback, useMemo } from "react";
import { ArchiveState } from "@/components/archive/archive-state";
import { FamilyGate } from "@/components/family/family-gate";
import { AppHeader } from "@/components/layout/app-header";
import { PageContainer } from "@/components/shell/page-container";
import { StoryLink, storyLinkLabels } from "@/components/story/story-link";
import { Button } from "@/components/ui/button";
import { useMuraI18n } from "@/lib/i18n";
import Link from "next/link";
import {
  fetchArchivePeople,
  fetchArchiveStories,
  type ArchivePerson,
  type ArchiveStorySummary,
} from "@/lib/mura/archive-api";
import { useArchivePages, useArchiveResource } from "@/lib/mura/use-archive";

/** One page of memories. Core clamps this to 1..100 server-side as well. */
const PAGE_SIZE = 30;

/**
 * Every memory in the family archive, newest first.
 *
 * Ordered by when the story was recorded, which the archive knows, rather than
 * by when the events happened, which it usually does not. Inventing a
 * chronology for undated memories would put a false history on a family.
 *
 * This asked for 30 and stopped — no next page, no indication anything had been
 * cut. For a product whose promise is an archive a family adds to for years,
 * memory 31 onwards was simply unreachable. It pages now, and says how much of
 * the archive is on screen while there is more.
 */
function StoriesContent() {
  const { t, locale } = useMuraI18n();

  const loadStories = useCallback(
    async (familyId: string, offset: number, signal: AbortSignal) => {
      const page = await fetchArchiveStories(familyId, {
        limit: PAGE_SIZE,
        offset,
        signal,
      });
      return { items: page.items, total: page.page.total };
    },
    [],
  );
  const stories = useArchivePages<ArchiveStorySummary>(loadStories);

  // People are loaded once and reused by every page; a second page of memories
  // does not need the family's people fetched again.
  const loadPeople = useCallback(
    (familyId: string, signal: AbortSignal) => fetchArchivePeople(familyId, signal),
    [],
  );
  const people = useArchiveResource<ArchivePerson[]>(loadPeople);
  const peopleById = useMemo(
    () => new Map((people.data ?? []).map((person) => [person.person_id, person])),
    [people.data],
  );

  const labels = storyLinkLabels(t);

  // `ArchiveState` speaks the single-resource shape; the paged list carries the
  // same four fields, so it is adapted rather than duplicated.
  const asResource = {
    status: stories.status,
    data: stories.items,
    familyId: stories.familyId,
    error: stories.error,
    reload: stories.reload,
  };

  return (
    <div className="pb-16">
      <AppHeader title={t("storiesTitle")} fallbackHref="/home" />

      <ArchiveState
        resource={asResource}
        loadingLabel={t("storiesLoading")}
        isEmpty={stories.items.length === 0}
        empty={
          <PageContainer>
            <div className="mx-auto max-w-measure py-14 text-center">
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
            {stories.items.map((story) => (
              <li key={story.story_id}>
                <StoryLink
                  story={story}
                  locale={locale}
                  labels={labels}
                  peopleById={peopleById}
                />
              </li>
            ))}
          </ul>

          {/* Announced, because the list grows below the button that grew it
              and a sighted user sees that happen while a screen reader user
              would not. */}
          <p className="sr-only" role="status" aria-live="polite">
            {t("storiesShownOf", { shown: stories.items.length, total: stories.total })}
          </p>

          {stories.hasMore && (
            <div className="flex flex-col items-center gap-2 pt-6">
              <Button
                variant="soft"
                onClick={stories.loadMore}
                disabled={stories.loadingMore}
              >
                {stories.loadingMore ? t("storiesLoadingMore") : t("storiesLoadMore")}
              </Button>
              <p className="text-meta text-muted">
                {t("storiesShownOf", {
                  shown: stories.items.length,
                  total: stories.total,
                })}
              </p>
            </div>
          )}
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
