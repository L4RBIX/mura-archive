"use client";

import { motion } from "framer-motion";
import { Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AuthStrip } from "@/components/family/auth-strip";
import { NextMemory } from "@/components/home/next-memory";
import { PeopleStrip } from "@/components/home/people-strip";
import { RecordHero } from "@/components/home/record-hero";
import { FirstRunFlow } from "@/components/onboarding/first-run-flow";
import { useArchiveSearch } from "@/components/search/search-provider";
import { PageContainer } from "@/components/shell/page-container";
import { StoryLink, storyLinkLabels } from "@/components/story/story-link";
import { useMuraI18n } from "@/lib/i18n";
import {
  fetchArchivePeople,
  fetchArchiveRelationships,
  type ArchivePerson,
  type ArchiveRelationship,
} from "@/lib/mura/archive-api";
import { buildFamilyRelations } from "@/lib/mura/family-graph";
import { generationCount } from "@/lib/mura/generations";
import { useMuraSession } from "@/lib/mura/session-provider";
import { useArchiveResource } from "@/lib/mura/use-archive";
import { useArchiveOverviewResource } from "@/lib/mura/use-archive-overview";

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.055, delayChildren: 0.02 } },
};

const item = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.23, 1, 0.32, 1] as const } },
};

/**
 * Home.
 *
 * ## What was wrong
 *
 * A greeting, a black circle floating in beige, and ten identical cards in a
 * grid — on a page whose largest words, «Воспоминания сегодня», told the user
 * nothing they did not already know. Two thirds of a 1440px window was empty,
 * the right rail held two links, and nothing anywhere said how much this
 * family had actually built.
 *
 * ## The shape now
 *
 * A masthead, then a filled hero that asks a question and states the archive's
 * own size, then an editorial list of memories with a rail beside it. Three
 * levels of emphasis instead of one flat plane, and the only card-shaped
 * things left are the two small blocks in the rail, where containment
 * genuinely means something.
 *
 * The memories are entries separated by rules rather than a card grid, and the
 * most recent is set larger: a family archive is a collection that grows, and
 * it should read like one rather than like a table.
 */
interface PeopleBundle {
  people: ArchivePerson[];
  relationships: ArchiveRelationship[];
}

export function HomeView() {
  const { greetingForHour, t, locale } = useMuraI18n();
  // Set after mount so the prerendered greeting never mismatches the client.
  const [greeting, setGreeting] = useState(() => greetingForHour(13));
  useEffect(() => setGreeting(greetingForHour(new Date().getHours())), [greetingForHour, locale]);

  // The summary is read once for the whole shell; Home reads the same object
  // the rail does rather than issuing a second identical request.
  const overview = useArchiveOverviewResource();
  const data = overview?.status === "ready" ? overview.data : null;

  const loadPeople = useCallback(
    async (familyId: string, signal: AbortSignal): Promise<PeopleBundle> => {
      const [people, relationships] = await Promise.all([
        fetchArchivePeople(familyId, signal),
        fetchArchiveRelationships(familyId, signal),
      ]);
      return { people, relationships };
    },
    [],
  );
  const bundle = useArchiveResource<PeopleBundle>(loadPeople);
  const people = bundle.data?.people ?? [];
  const relationships = bundle.data?.relationships ?? [];

  const labels = storyLinkLabels(t);
  const { family, auth } = useMuraSession();
  const search = useArchiveSearch();
  const familyName = family.selectedFamily?.name ?? null;
  const displayName = auth.status === "authenticated" ? auth.user.displayName : null;
  const stories = data?.recent_stories ?? [];
  const peopleById = new Map(people.map((person) => [person.person_id, person]));

  const hasNoFamily = auth.status === "authenticated" && family.status === "no_families";
  const archiveIsReady = overview?.status === "ready" && Boolean(data);
  const isFirstRun = hasNoFamily || (archiveIsReady && data !== null && data.story_count === 0);
  const signedIn = auth.status === "authenticated";

  // Generations are derived from the graph, never estimated. Until the people
  // and edges have arrived it is simply absent rather than shown as zero.
  const snapshot = data
    ? {
        people: data.people_count,
        stories: data.story_count,
        generations:
          people.length > 0
            ? generationCount(buildFamilyRelations(people, relationships))
            : 0,
      }
    : null;

  return (
    <PageContainer width="wide" className="pb-20 pt-screen">
      <motion.div variants={container} initial="hidden" animate="visible">
        {/*
          The masthead. The greeting is the small line and the family's own
          words are the large one — the previous order set «Воспоминания
          сегодня» at display size, which is a section label, not a title.
        */}
        <motion.header variants={item} className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <p className="text-meta text-muted">
              {greeting}
              {displayName ? `, ${displayName}` : ""}
              {familyName && (
                <span className="lg:hidden">
                  {" · "}
                  <span className="font-medium text-ink/75">{familyName}</span>
                </span>
              )}
            </p>
            <h1 className="mt-2 max-w-[16ch] text-balance text-title font-bold leading-[1.05] tracking-[-0.035em]">
              {t("homeFamilyStories")}
            </h1>
          </div>

          {search && (
            <button
              type="button"
              onClick={search.open}
              aria-keyshortcuts="Control+K Meta+K"
              aria-label={t("searchOpen")}
              className="mt-1 flex size-11 shrink-0 items-center justify-center rounded-full border border-ink/[0.1] text-ink/70 transition-colors hover:bg-raised hover:text-ink focus-ring"
            >
              <Search aria-hidden className="size-5" strokeWidth={1.8} />
            </button>
          )}
        </motion.header>

        {!signedIn && (
          <motion.div variants={item} className="mt-8">
            <AuthStrip />
          </motion.div>
        )}

        {isFirstRun ? (
          <motion.div variants={item} className="mt-9">
            <FirstRunFlow />
          </motion.div>
        ) : (
          signedIn && (
            <>
              <motion.div variants={item} className="mt-9">
                <RecordHero snapshot={snapshot} />
              </motion.div>

              <div className="mt-14 grid gap-x-14 gap-y-12 lg:grid-cols-[minmax(0,1fr)_300px] 2xl:gap-x-20 2xl:grid-cols-[minmax(0,1fr)_340px]">
                <motion.section variants={item} className="min-w-0" aria-labelledby="home-recent">
                  <div className="flex items-baseline justify-between gap-4 border-b border-ink/[0.14] pb-3">
                    <h2 id="home-recent" className="text-section font-semibold tracking-[-0.02em]">
                      {t("homeRecent")}
                    </h2>
                    {stories.length > 0 && (
                      <Link
                        href="/stories"
                        className="-mr-2 flex min-h-11 shrink-0 items-center rounded-control px-2 text-meta font-medium text-ink/65 underline decoration-ink/25 underline-offset-4 transition-colors hover:text-ink focus-ring"
                      >
                        {t("homeOpenStories")}
                      </Link>
                    )}
                  </div>

                  <div className="divide-y divide-ink/[0.08]">
                    {stories.map((story, index) => (
                      <StoryLink
                        key={story.story_id}
                        story={story}
                        locale={locale}
                        labels={labels}
                        variant={index === 0 ? "lead" : "entry"}
                        peopleById={peopleById}
                      />
                    ))}
                  </div>
                </motion.section>

                <motion.aside variants={item} className="min-w-0 space-y-10 lg:self-start">
                  {people.length > 0 && <PeopleStrip people={people} />}
                  {people.length > 0 && <NextMemory people={people} />}
                </motion.aside>
              </div>
            </>
          )
        )}
      </motion.div>
    </PageContainer>
  );
}
