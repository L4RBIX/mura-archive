"use client";

import { useCallback } from "react";
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
  type ArchiveStoryPage,
} from "@/lib/mura/archive-api";
import { useArchiveResource } from "@/lib/mura/use-archive";

/** One page of memories. Core clamps this server-side too. */
const PAGE_SIZE = 30;

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
interface StoriesBundle {
  page: ArchiveStoryPage;
  /** Canonical people, so a card can name who is in a memory by id. */
  peopleById: Map<string, ArchivePerson>;
}

function StoriesContent() {
  const { t, locale } = useMuraI18n();
  const load = useCallback(
    async (familyId: string, signal: AbortSignal): Promise<StoriesBundle> => {
      // Both at once: the list cannot render its people chips without the
      // people, so staggering them would only add a waterfall.
      const [page, people] = await Promise.all([
        fetchArchiveStories(familyId, { limit: PAGE_SIZE, signal }),
        fetchArchivePeople(familyId, signal),
      ]);
      return {
        page,
        peopleById: new Map(people.map((person) => [person.person_id, person])),
      };
    },
    [],
  );
  const stories = useArchiveResource<StoriesBundle>(load);
  const labels = storyLinkLabels(t);
  const page = stories.data?.page;

  return (
    <div className="pb-16">
      <AppHeader title={t("storiesTitle")} fallbackHref="/home" />

      <ArchiveState
        resource={stories}
        loadingLabel={t("storiesLoading")}
        isEmpty={(page?.items.length ?? 0) === 0}
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
            {page?.items.map((story) => (
              <li key={story.story_id}>
                <StoryLink
                  story={story}
                  locale={locale}
                  labels={labels}
                  peopleById={stories.data?.peopleById}
                />
              </li>
            ))}
          </ul>
          {/* The list was silently cut at 30 with no way to tell. Saying how
              much of the archive is on screen is the honest minimum until
              step 3 makes the rest reachable. */}
          {page && page.page.total > page.items.length && (
            <p className="pt-4 text-meta text-muted">
              {t("storiesShownOf", { shown: page.items.length, total: page.page.total })}
            </p>
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
