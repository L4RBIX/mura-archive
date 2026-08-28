"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useCallback } from "react";
import { ArchiveState } from "@/components/archive/archive-state";
import { FamilyGate } from "@/components/family/family-gate";
import { AppHeader } from "@/components/layout/app-header";
import { READING_WIDTH } from "@/components/shell/page-container";
import { RecordingPlayer } from "@/components/story/recording-player";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import { fetchArchiveStory, type ArchiveDate, type ArchiveStoryDetail } from "@/lib/mura/archive-api";
import { useArchiveResource } from "@/lib/mura/use-archive";

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.23, 1, 0.32, 1] as const } },
};

/**
 * Render a date at the precision the archive actually has.
 *
 * The whole point of carrying `precision` through the API is this function
 * refusing to print a day when the archive only ever heard a year. Where an
 * original expression was recorded — "летом 1963" — it is preferred, because
 * that is what somebody actually said.
 */
function formatArchiveDate(date: ArchiveDate): string | null {
  if (date.original_expression) return date.original_expression;
  if (!date.value) return null;
  return date.approximate ? `≈ ${date.value}` : date.value;
}

function StoryContent({ storyId }: { storyId: string }) {
  const { t, locale } = useMuraI18n();

  const load = useCallback(
    (familyId: string, signal: AbortSignal) => fetchArchiveStory(familyId, storyId, signal),
    [storyId],
  );
  const story = useArchiveResource<ArchiveStoryDetail>(load);
  const data = story.data;
  const dateLocale = locale === "kk" ? "kk-KZ" : "ru-RU";

  return (
    <div className="pb-20">
      <AppHeader title={t("memory")} fallbackHref="/stories" ownTitle width="reading" />

      <ArchiveState resource={story} loadingLabel={t("storyLoading")}>
        {!data ? null : (
          <motion.article
            variants={container}
            initial="hidden"
            animate="visible"
            // The reading measure is `PageContainer`'s to state, not this
            // screen's. It was hardcoded here as well, so the one number that
            // decides how a memoir reads lived in two places and the container
            // token had quietly stopped applying to the only long-form screen
            // in the product.
            className={`mx-auto w-full ${READING_WIDTH} px-5 pt-2 sm:px-6 lg:px-8`}
          >
            <motion.p
              variants={item}
              className="text-meta font-semibold tracking-[-0.005em] text-ink/70"
            >
              {new Date(data.recorded_at).toLocaleDateString(dateLocale)}
            </motion.p>

            <motion.h1
              variants={item}
              className="mt-2 text-balance text-display font-bold leading-[1.1] tracking-[-0.03em]"
            >
              {data.title ?? t("storyUntitled")}
            </motion.h1>

            <motion.p variants={item} className="mt-2 text-meta text-muted">
              {t("storyToldBy", { name: data.speaker_name })}
            </motion.p>

            <motion.div variants={item} className="mt-6">
              <RecordingPlayer
                familyId={story.familyId as string}
                recordingId={data.recording_id}
                available={data.audio_available}
              />
            </motion.div>

            {data.summary && (
              <motion.p
                variants={item}
                className="mt-8 text-reading leading-[1.75] text-ink/90"
              >
                {data.summary}
              </motion.p>
            )}

            {data.events.length > 0 && (
              <motion.section variants={item} className="mt-9">
                <SectionLabel>{t("eventsAndPlaces")}</SectionLabel>
                <ul className="space-y-3">
                  {data.events.map((event) => {
                    const when = event.date ? formatArchiveDate(event.date) : null;
                    return (
                      <li key={event.event_id} className="rounded-surface bg-raised p-4">
                        <p className="text-body font-semibold">{event.title}</p>
                        {event.description && (
                          <p className="mt-1 text-meta leading-relaxed text-muted">
                            {event.description}
                          </p>
                        )}
                        {(when || event.location) && (
                          <p className="mt-2 text-caption text-muted">
                            {[when, event.location].filter(Boolean).join(" · ")}
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </motion.section>
            )}

            {data.people.length > 0 && (
              <motion.section variants={item} className="mt-9">
                <SectionLabel>{t("inThisMemory")}</SectionLabel>
                <ul className="flex flex-wrap gap-2">
                  {data.people.map((person) => (
                    <li key={person.person_id}>
                      <Link
                        href={`/person/${encodeURIComponent(person.person_id)}`}
                        className="flex items-center gap-2 rounded-full bg-raised py-1.5 pl-1.5 pr-3.5 text-meta font-medium shadow-soft focus-ring"
                      >
                        <PersonAvatar
                          personId={person.person_id}
                          displayName={person.display_name}
                          size={26}
                        />
                        {person.display_name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </motion.section>
            )}

            {/* Provenance in human terms. The evidence machinery -- classes,
                assertion modes, confidences -- stays on the server; what a
                family member needs is which recording this came from. */}
            <motion.section variants={item} className="mt-10">
              <SectionLabel>{t("storySourceTitle")}</SectionLabel>
              <p className="text-meta leading-relaxed text-muted">
                {t("storySourceLine", {
                  date: new Date(data.source.recorded_at).toLocaleDateString(dateLocale),
                })}{" "}
                · {data.source.speaker_name}
              </p>
            </motion.section>
          </motion.article>
        )}
      </ArchiveState>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-meta font-semibold tracking-[-0.005em] text-ink/70">
      {children}
    </h2>
  );
}

export function StoryView({ storyId }: { storyId: string }) {
  return (
    <FamilyGate>
      <StoryContent storyId={storyId} />
    </FamilyGate>
  );
}
