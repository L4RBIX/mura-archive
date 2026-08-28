"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { READING_WIDTH } from "@/components/shell/page-container";
import { TranscriptReader } from "@/components/story/transcript-reader";
import { formatDuration } from "@/lib/format";
import { useMuraI18n } from "@/lib/i18n";
import {
  getMemoryAudio,
  getSavedMemory,
  useMemoryOwner,
  type SavedMemory,
} from "@/lib/memory-store";

export function LocalStoryView({ memoryId }: { memoryId: string }) {
  const { locale, t } = useMuraI18n();
  const [memory, setMemory] = useState<SavedMemory | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const memoryOwner = useMemoryOwner();

  useEffect(() => {
    let active = true;
    // Dropping the previous URL first revokes it through the cleanup below, so
    // a sign-out cannot leave the last account's audio playable in an open tab.
    setAudioUrl(null);
    const current = getSavedMemory(memoryId);
    setMemory(current);
    if (!current) {
      setLoaded(true);
      return;
    }
    void getMemoryAudio(memoryId)
      .then((audio) => {
        if (!active || !audio) return;
        setAudioUrl(URL.createObjectURL(audio));
      })
      .finally(() => {
        if (active) setLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [memoryId, memoryOwner]);

  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );

  const recordedAt = useMemo(() => {
    if (!memory) return "";
    return new Intl.DateTimeFormat(locale === "kk" ? "kk-KZ" : "ru-RU", {
      dateStyle: "long",
      timeStyle: "short",
    }).format(new Date(memory.createdAt));
  }, [locale, memory]);

  if (!loaded) return null;
  if (!memory) {
    return (
      <div>
        <AppHeader title={t("memory")} fallbackHref="/home" ownTitle width="reading" />
        <p className="mx-auto max-w-[46ch] px-6 pt-16 text-center text-muted">{t("memoryNotFound")}</p>
      </div>
    );
  }

  return (
    <div className="pb-20">
      <AppHeader title={t("memory")} fallbackHref="/home" ownTitle width="reading" />
      <motion.article
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className={`mx-auto w-full ${READING_WIDTH} px-5 pt-2 sm:px-6 lg:px-8`}
      >
        <p className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
          {recordedAt}
        </p>
        <h1 className="mt-2 text-display font-bold leading-[1.1] tracking-[-0.03em]">
          {memory.title}
        </h1>
        <p className="mt-3 text-meta text-muted">
          {formatDuration(memory.durationSec)}
        </p>

        {audioUrl && (
          <div className="mt-7 rounded-panel bg-raised p-5 shadow-card">
            <audio className="w-full" controls preload="metadata" src={audioUrl}>
              <track kind="captions" />
            </audio>
          </div>
        )}

        {/* «Кратко» — the pipeline's retelling. While the analysis is still
            running this stays a status line rather than showing the raw
            transcript as if it were a finished result. */}
        <section className="mt-10 rounded-panel bg-peach/55 p-5">
          <h2 className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
            {t("aiSummary")}
          </h2>
          {memory.summary ? (
            <p className="mt-3 text-pretty text-reading font-medium leading-relaxed">
              {memory.summary}
            </p>
          ) : (
            <p className="mt-3 text-body leading-relaxed text-ink/60">
              {memory.status === "failed" ? t("analysisFailed") : t("analysisPending")}
            </p>
          )}
          {memory.status === "needs_review" && memory.summary && (
            <p className="mt-3 text-meta leading-relaxed text-ink/55">
              {t("needsReviewNote")}
            </p>
          )}
        </section>

        {memory.people.length > 0 && (
          <section className="mt-12">
            <h2 className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
              {t("inThisMemory")}
            </h2>
            <ul className="mt-4 space-y-2.5">
              {memory.people.map((person, index) => {
                // Link only on a canonical id from Core. The previous check
                // resolved that id against demo fixtures, so it never matched
                // and no link ever appeared.
                const known = person.personId;
                return (
                  <li
                    key={`${person.name}-${index}`}
                    className="rounded-surface bg-raised p-4"
                  >
                    <p className="text-body font-semibold">{person.name}</p>
                    {person.relationship && (
                      <p className="mt-0.5 text-meta text-ink/65">
                        {person.relationship}
                      </p>
                    )}
                    {person.isNew && (
                      <p className="mt-1.5 text-caption leading-snug text-ink/55">
                        {t("addedFromMemory")}
                      </p>
                    )}
                    {known && (
                      <Link
                        href={`/person/${encodeURIComponent(known)}`}
                        className="mt-2 inline-block text-meta font-semibold text-ink underline underline-offset-4"
                      >
                        {t("openInTree")}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {Boolean(memory.events?.length || memory.places?.length) && (
          <section className="mt-12">
            <h2 className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
              {t("eventsAndPlaces")}
            </h2>
            <ul className="mt-4 space-y-2.5">
              {memory.events?.map((event, index) => (
                <li
                  key={`${event.title}-${index}`}
                  className="rounded-surface bg-raised p-4"
                >
                  <p className="text-body font-semibold">
                    {event.title || event.description}
                  </p>
                  {(event.dateText || event.location) && (
                    <p className="mt-1 text-meta text-ink/65">
                      {[event.dateText, event.location].filter(Boolean).join(" · ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
            {memory.places && memory.places.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {memory.places.map((place) => (
                  <span
                    key={place}
                    className="rounded-full bg-sand px-3.5 py-1.5 text-meta font-medium text-ink/75"
                  >
                    {place}
                  </span>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="mt-12">
          <h2 className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
            {t("transcript")}
          </h2>
          <div className="mt-4">
            <TranscriptReader
              paragraphs={[
                memory.cleanTranscript || memory.transcript || t("transcriptUnavailable"),
              ]}
            />
          </div>
        </section>
      </motion.article>
    </div>
  );
}
