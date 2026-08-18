"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DemoBadge } from "@/components/demo/demo-notice";
import { AuthStrip } from "@/components/family/auth-strip";
import { ArchiveDoorways } from "@/components/home/archive-doorways";
import { RecordButton } from "@/components/record/record-button";
import { PageContainer } from "@/components/shell/page-container";
import { StoryLink, storyLinkLabels } from "@/components/story/story-link";
import { useMuraI18n } from "@/lib/i18n";
import {
  fetchArchiveOverview,
  fetchArchivePeople,
  type ArchiveOverview,
  type ArchivePerson,
} from "@/lib/mura/archive-api";
import { useMuraSession } from "@/lib/mura/session-provider";
import { useArchiveResource } from "@/lib/mura/use-archive";

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07, delayChildren: 0.04 } },
};

const item = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.23, 1, 0.32, 1] as const } },
};

/**
 * The emotional centre of the product, not a dashboard.
 *
 * Two things were wrong once real data arrived. «Недавние записи» listed local
 * drafts while a doorway beside it counted archive stories, so the page could
 * say «Здесь пока пусто» directly above «2 рассказов» — one screen
 * contradicting itself. It reads the archive now, and the contradiction went
 * away along with a whole competing section.
 *
 * And four identical cards left nothing dominant. Recording is the one thing
 * this product exists for, so it is the only heavy element on the page; the
 * ways further in are a quiet list beside it.
 */
interface HomeBundle {
  archive: ArchiveOverview;
  peopleById: Map<string, ArchivePerson>;
}

export function HomeView() {
  const { greetingForHour, t, locale } = useMuraI18n();
  // Set after mount so the prerendered greeting never mismatches the client.
  const [greeting, setGreeting] = useState(() => greetingForHour(13));
  useEffect(() => setGreeting(greetingForHour(new Date().getHours())), [greetingForHour, locale]);

  const load = useCallback(
    async (familyId: string, signal: AbortSignal): Promise<HomeBundle> => {
      const [archive, people] = await Promise.all([
        fetchArchiveOverview(familyId, signal),
        fetchArchivePeople(familyId, signal),
      ]);
      return {
        archive,
        peopleById: new Map(people.map((person) => [person.person_id, person])),
      };
    },
    [],
  );
  const overview = useArchiveResource<HomeBundle>(load);
  const data = overview.data?.archive;
  const labels = storyLinkLabels(t);
  const { family } = useMuraSession();
  const familyName = family.selectedFamily?.name ?? null;
  const stories = data?.recent_stories ?? [];
  // Signed out there is no archive to summarise, and there is no longer a
  // demonstration one to stand in for it. A section heading with nothing
  // under it is worse than no section.
  const hasArchive = overview.status !== "idle";

  return (
    <PageContainer width="wide" className="pb-16 pt-screen">
      <motion.div variants={container} initial="hidden" animate="visible">
        <motion.header variants={item}>
          <p className="text-meta text-muted">
            {greeting}
            {/* Below `lg` there is no rail, so nothing on the screen said whose
                archive this is — the one question Home has to answer before
                «what should I do next?». Stated here rather than added as a
                second element, and hidden at `lg` where the rail already
                answers it. */}
            {familyName && (
              <span className="lg:hidden">
                {" · "}
                <span className="font-medium text-ink/75">{familyName}</span>
              </span>
            )}
          </p>
          <h1 className="mt-1 text-title font-bold leading-[1.08] tracking-[-0.03em] sm:text-display">
            {t("todaysMemories")}
          </h1>
        </motion.header>

        <motion.div variants={item} className="mt-6">
          <AuthStrip />
        </motion.div>

        {/*
          One page grid, not a band stacked on a row.

          The record button and the doorways used to sit in a flex row of their
          own above a full-width memories list. Because that row only needed
          ~640px, it left a ~460px hole to the right of it at 1440 while the
          list underneath ran the full 1100 — two different widths on one page,
          which reads as a layout fault rather than a composition.

          Now everything the user reads sits in column one, so the record button
          and the memories share an edge, and the archive doorways occupy
          column two for the whole height of the page instead of a corner of it.
          Source order is record → doorways → memories, which is also the right
          order stacked on a phone; `col/row-start` puts them back into two
          columns from `lg` without moving anything in the DOM.
        */}
        <div className="mt-8 grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_300px] 2xl:gap-x-16 2xl:grid-cols-[minmax(0,1fr)_340px]">
          <motion.div
            variants={item}
            className="flex justify-center sm:justify-start lg:col-start-1 lg:row-start-1"
          >
            <RecordButton
              href="/record"
              label={t("recordMemory")}
              sublabel={t("pressAndSpeak")}
            />
          </motion.div>

          <motion.aside
            variants={item}
            className="min-w-0 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-start"
          >
            {data && <ArchiveDoorways overview={data} />}
            <Link
              href="/ask"
              className="mt-3 flex items-center gap-2.5 py-2 text-meta focus-ring"
            >
              <span className="font-medium text-ink/70">{t("askCardTitle")}</span>
              <DemoBadge />
            </Link>
          </motion.aside>

          {hasArchive && (
          <motion.section
            variants={item}
            className="min-w-0 lg:col-start-1 lg:row-start-2"
          >
            <h2 className="text-caption font-semibold uppercase tracking-[0.16em] text-muted">
              {t("recentRecordings")}
            </h2>
            {/* Two columns only once column one is genuinely wide enough —
                which, beside a 300px aside, is `xl` and not `lg`. */}
            <div className="mt-3 grid gap-2.5 xl:grid-cols-2">
              {stories.map((story) => (
                <StoryLink
                  key={story.story_id}
                  story={story}
                  locale={locale}
                  labels={labels}
                  peopleById={overview.data?.peopleById}
                />
              ))}
              {overview.status === "ready" && stories.length === 0 && (
                // One sentence. An empty archive does not need a heading, a
                // paragraph and a card of its own to say so.
                <p className="text-body leading-relaxed text-muted">{t("homeEmptyBody")}</p>
              )}
            </div>
            {stories.length > 0 && (
              <Link
                href="/stories"
                className="mt-4 inline-block text-meta font-medium text-ink/70 underline underline-offset-4 focus-ring"
              >
                {t("homeOpenStories")}
              </Link>
            )}
          </motion.section>
          )}
        </div>
      </motion.div>
    </PageContainer>
  );
}
