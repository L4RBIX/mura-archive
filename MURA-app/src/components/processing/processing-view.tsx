"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { MascotStage } from "@/components/mascot/mascot-stage";
import { useMascot } from "@/hooks/use-mascot";
import {
  completeMemoryFromCore,
  getSavedMemory,
  updateMemory,
  type SavedMemory,
} from "@/lib/memory-store";
import { fetchJob, fetchRecordingResult } from "@/lib/mura/core-api";
import { isPresentable, readAnalysis } from "@/lib/mura/pipeline-result";
import { readWorkflow } from "@/lib/mura/recording-workflow";
import {
  retryCountdownSeconds,
  stateFromJob,
  type PipelineState,
} from "@/lib/mura/pipeline-state";
import { useMuraI18n } from "@/lib/i18n";

const EASE = [0.23, 1, 0.32, 1] as const;

/** Beat between the last caption settling and the result appearing. */
const RESULT_HOLD_MS = 380;

function NameChip({ name, delay }: { name: string; delay: number }) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return (
    <motion.span
      className="flex items-center gap-2 rounded-full bg-raised py-1.5 pl-1.5 pr-4 shadow-soft"
      initial={{ opacity: 0, scale: 0.8, y: 8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 300, damping: 22 }}
    >
      <span className="flex size-7 items-center justify-center rounded-full bg-clay text-caption font-bold">
        {initials}
      </span>
      <span className="text-meta font-semibold">{name}</span>
    </motion.span>
  );
}

export function ProcessingView() {
  const { locale, t } = useMuraI18n();
  const steps = [t("processingListen"), t("processingPeople"), t("processingPlace")];
  const router = useRouter();
  const searchParams = useSearchParams();
  const jobId = searchParams.get("job");
  const memoryId = searchParams.get("memory");
  // The workflow, including the family it was submitted under. Read from the
  // URL rather than from the current selection on purpose: a user who switches
  // family while a memory is processing must still see *that* memory finish, in
  // the archive it actually belongs to.
  const workflow = readWorkflow(searchParams);
  const recordingId = workflow?.recordingId ?? null;
  const recordingFamilyId = workflow?.familyId ?? null;
  const [memory, setMemory] = useState<SavedMemory | null>(null);
  const [step, setStep] = useState(0);
  const [failed, setFailed] = useState(false);
  // `degraded` is the state the screen was missing. A job the backend deferred
  // because ASR is unreachable reports `queued`, which looked exactly like
  // "your turn is coming" — so the mascot thought forever while the tunnel was
  // dead. Now the wait is named, counted down, and escapable.
  const [pipelineState, setPipelineState] = useState<PipelineState>("preprocessing");
  const [retryIn, setRetryIn] = useState<number | null>(null);
  const degraded = pipelineState === "degraded";

  // The two halves of the barrier. The result screen waits for both.
  const [analysisDone, setAnalysisDone] = useState(false);
  const [audioDone, setAudioDone] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const resultHref = useRef<string | null>(null);

  // With no voice-over there is nothing to wait for, so the barrier's audio
  // half is satisfied immediately and the result appears as soon as the
  // pipeline is done.
  const mascot = useMascot({ onIntroFinish: () => setAudioDone(true) });
  const { send, isSpeaking } = mascot;

  useEffect(() => {
    if (memoryId) setMemory(getSavedMemory(memoryId));
  }, [memoryId]);

  // Her pose tracks the real job. While she is narrating she stays speaking;
  // the stage she rejoins afterwards is whichever one the job reached. Once
  // she has finished talking but the backend has not, she waits in THINKING.
  useEffect(() => {
    if (isSpeaking) return;
    if (failed) {
      send("FAIL");
      return;
    }
    if (degraded) {
      // She stops working rather than miming thought at a stalled pipeline.
      send("SETTLE");
      return;
    }
    if (audioDone && !analysisDone) {
      send("THINK");
      return;
    }
    send(step === 0 ? "PROCESS" : step === 1 ? "THINK" : "SEARCH");
  }, [step, failed, degraded, isSpeaking, audioDone, analysisDone, send]);

  // A failure must not wait for her to finish the sentence. The recording and
  // whatever transcript exists stay untouched so the analysis can be retried.
  useEffect(() => {
    if (!failed) return;
    if (memoryId) updateMemory(memoryId, { status: "failed" });
  }, [failed, memoryId]);

  /**
   * The barrier. Neither the recording's narration nor the backend alone is
   * enough — the result appears only once both are done, then after a short
   * hold so the final caption can be read and the screen can fade rather than
   * cut. Any unmount clears the pending navigation, so a user who leaves mid
   * wait is never yanked to a stale route.
   */
  useEffect(() => {
    if (failed || !analysisDone || !audioDone) return;
    const href = resultHref.current;
    if (!href) return;
    setLeaving(true);
    const timer = window.setTimeout(() => router.replace(href), RESULT_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [analysisDone, audioDone, failed, router]);

  useEffect(() => {
    if (jobId || !memoryId) return;
    const timers = [
      window.setTimeout(() => setStep(1), 600),
      window.setTimeout(() => setStep(2), 1300),
      window.setTimeout(() => {
        resultHref.current = `/story/${encodeURIComponent(memoryId)}`;
        setAnalysisDone(true);
      }, 2100),
    ];
    return () => timers.forEach(window.clearTimeout);
  }, [jobId, memoryId, router]);

  useEffect(() => {
    if (!jobId || !recordingId || !memoryId || !recordingFamilyId) return;
    let cancelled = false;
    // A holder rather than a bare binding: `stop` closes over it, and the
    // interval it clears is created after `stop` is defined.
    const handle: { id?: number } = {};

    /**
     * Stop polling for good.
     *
     * `completed` and `failed` are terminal: the answer cannot change, so any
     * further request is pure waste. Without this the interval kept running
     * after the job finished -- indefinitely on the failure screen, which a
     * user can sit on for as long as they like, and on success it re-fetched
     * the full recording result every 1.5s until the screen navigated away.
     */
    const stop = () => {
      cancelled = true;
      if (handle.id !== undefined) window.clearInterval(handle.id);
    };

    const poll = async () => {
      try {
        const job = await fetchJob(jobId, recordingFamilyId);
        if (cancelled) return;
        const next = stateFromJob(job);
        setPipelineState(next);
        setRetryIn(retryCountdownSeconds(job));
        if (next === "failed") {
          stop();
          setFailed(true);
          return;
        }
        if (["cleaning", "extracting"].includes(job.status) || job.stage.startsWith("window_"))
          setStep(1);
        if (["resolving", "completed"].includes(job.status)) setStep(2);
        if (job.status === "completed") {
          {
            // Terminal: stop before the follow-up fetch so a slow result read
            // cannot let another interval tick start a second one.
            stop();
            const coreResult = await fetchRecordingResult(recordingId, recordingFamilyId);
            // The pipeline's own title and summary replace the placeholders
            // written when the recording stopped. Previously this response was
            // stashed in sessionStorage and never read, so «Кратко» kept
            // showing the raw transcript.
            const analysis = readAnalysis(coreResult);
            if (isPresentable(analysis)) {
              completeMemoryFromCore(memoryId, {
                title: analysis.title ?? undefined,
                summary: analysis.summary ?? undefined,
                transcript: analysis.rawTranscript ?? "",
                cleanTranscript: analysis.cleanTranscript ?? undefined,
                audio_language: analysis.languageContext.requested_audio_language,
                detected_audio_language:
                  analysis.languageContext.detected_audio_language,
                transcript_language:
                  analysis.languageContext.transcript_language,
                output_language: analysis.languageContext.requested_output_language,
                people: analysis.people.map((person) => ({
                  name: person.name,
                  relationship: person.relationToSpeaker ?? "",
                  personId: person.personId ?? undefined,
                  isNew: person.isNew,
                })),
                events: analysis.events.map((event) => ({
                  title: event.title,
                  description: event.description,
                  dateText: event.dateText,
                  location: event.location,
                })),
                places: analysis.places.map((place) => place.name),
                status: analysis.needsReview ? "needs_review" : "completed",
                analyzed: true,
              });
            }
            resultHref.current = `/story/${encodeURIComponent(memoryId)}`;
            setAnalysisDone(true);
          }
        }
      } catch {
        if (cancelled) return;
        // A request that failed is not a job that failed, but this screen has
        // no retry budget to spend, so it reports the failure and stops rather
        // than hammering an endpoint that just refused it.
        stop();
        setFailed(true);
      }
    };
    // Interval first, then the immediate poll: `stop()` can only clear a timer
    // that already exists, and starting the timer after an awaiting poll would
    // leave a stopped job with a live interval nobody cancels.
    handle.id = window.setInterval(poll, 1500);
    void poll();
    return stop;
  }, [jobId, memoryId, recordingFamilyId, recordingId, router]);

  // A visible countdown instead of an indeterminate wait. The backend has
  // already scheduled the attempt; this only renders when it lands.
  const counting = degraded && retryIn !== null;
  useEffect(() => {
    if (!counting) return;
    const timer = window.setInterval(() => {
      setRetryIn((value) => (value === null ? null : Math.max(0, value - 1)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [counting]);

  // Core retries a deferred recording by itself and exposes no manual retry
  // operation, so the only honest client action is to record again.
  const restartRecording = () => {
    router.push("/record");
  };

  const dateLabel = useMemo(() => {
    if (!memory) return "";
    return new Intl.DateTimeFormat(locale === "kk" ? "kk-KZ" : "ru-RU", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(memory.createdAt));
  }, [locale, memory]);

  return (
    // Fades rather than cuts on the way to the result, so there is never a
    // blank frame between the two screens.
    <motion.div
      className="relative mx-auto flex h-dvh w-full max-w-[520px] flex-col items-center justify-center px-6 sm:px-8"
      animate={{ opacity: leaving ? 0 : 1 }}
      transition={{ duration: leaving ? 0.34 : 0.2, ease: EASE }}
    >
      <MascotStage state={mascot.state} size={268} className="mb-2" />

      <AnimatePresence mode="wait">
        <motion.h1
          key={step}
          className="text-center text-title font-semibold leading-snug tracking-[-0.02em]"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.4, ease: EASE }}
        >
          {failed ? t("processingFailureTitle") : steps[step]}
        </motion.h1>
      </AnimatePresence>

      <div className="relative mt-9 flex min-h-[168px] w-[280px] flex-col items-center">
        <motion.span
          className="flex max-w-[260px] items-center gap-2.5 rounded-full bg-raised py-2 pl-3 pr-4 shadow-soft"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <span className="size-2.5 shrink-0 animate-pulse rounded-full bg-clay" />
          <span className="truncate text-meta font-semibold">
            {memory?.title ?? t("newMemory")}
          </span>
        </motion.span>

        {step >= 1 && memory && memory.people.length > 0 && (
          <div className="mt-14 flex flex-wrap justify-center gap-2">
            {memory.people.slice(0, 3).map((person, index) => (
              <NameChip key={`${person.name}-${index}`} name={person.name} delay={0.2 + index * 0.12} />
            ))}
          </div>
        )}
      </div>

      <div className="h-12">
        {step >= 2 && !failed && dateLabel && (
          <motion.span
            className="inline-block rounded-full bg-sand px-4 py-1.5 text-meta font-medium text-ink/70"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {dateLabel}
          </motion.span>
        )}
      </div>

      <AnimatePresence>
        {degraded && (
          <motion.div
            className="absolute inset-x-6 bottom-[max(env(safe-area-inset-bottom),28px)] rounded-panel bg-raised p-5 shadow-soft"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            transition={{ duration: 0.24, ease: EASE }}
            role="status"
            aria-live="polite"
          >
            <p className="text-body font-semibold">{t("asrUnavailableTitle")}</p>
            <p className="mt-1.5 text-meta leading-snug text-muted">
              {t("asrUnavailableBody")}
            </p>
            {retryIn !== null && retryIn > 0 && (
              <p className="mt-2 text-meta font-medium text-ink/70">
                {t("asrRetryIn")} {Math.ceil(retryIn)} {t("seconds")}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => router.push("/record?mode=transcript")}
                className="rounded-full bg-clay px-4 py-2 text-meta font-semibold"
              >
                {t("openTranscriptFallback")}
              </button>
              <button
                type="button"
                onClick={() => router.push("/")}
                className="rounded-full bg-sand px-4 py-2 text-meta font-semibold text-ink/70"
              >
                {t("tryAgain")}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!degraded && failed && (
        <div className="absolute inset-x-6 bottom-[max(env(safe-area-inset-bottom),28px)] flex flex-col items-center">
          <p className="max-w-[360px] text-center text-meta leading-relaxed text-muted">
            {t("processingFailed")}
          </p>
          <button
            type="button"
            onClick={restartRecording}
            className="mt-4 rounded-full bg-clay px-5 py-2.5 text-meta font-semibold shadow-soft"
          >
            {t("restart")}
          </button>
        </div>
      )}
      {!degraded && !failed && (
        <p className="absolute bottom-[max(env(safe-area-inset-bottom),32px)] text-meta text-muted">
          {t("processingSafe")}
        </p>
      )}
    </motion.div>
  );
}
