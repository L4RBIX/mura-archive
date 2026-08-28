"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useCallback, useState, useRef } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { Lastochka } from "@/components/mascot/lastochka";
import { submitRecording } from "@/lib/mura/core-api";
import { processingHref } from "@/lib/mura/recording-workflow";
import {
  canSubmitRecording,
  captureAvailability,
  processingAvailability,
  processingNotice,
  type CaptureBlocker,
} from "@/lib/mura/recording-availability";
import { useAudioLanguage } from "@/lib/mura/audio-language";
import { useMuraSession } from "@/lib/mura/session-provider";
import { useMicrophoneState } from "@/hooks/use-microphone-state";
import { fetchArchivePeople, type ArchivePerson } from "@/lib/mura/archive-api";
import { useArchiveResource } from "@/lib/mura/use-archive";
import { MascotStage } from "@/components/mascot/mascot-stage";
import { LiveTranscript } from "@/components/record/live-transcript";
import { RecordButton } from "@/components/record/record-button";
import { RecordCompanion, type Speaker } from "@/components/record/record-companion";
import { RecordControls } from "@/components/record/record-controls";
import { Waveform } from "@/components/record/waveform";
import { useLiveTranscript } from "@/hooks/use-live-transcript";
import { useMascot } from "@/hooks/use-mascot";
import { useRecorder } from "@/hooks/use-recorder";
import { formatTimer } from "@/lib/format";
import {
  DEFAULT_OUTPUT_LANGUAGE,
} from "@/lib/language";
import { cn } from "@/lib/utils";
import { useMuraI18n } from "@/lib/i18n";
import { saveMemory, type SavedMemory } from "@/lib/memory-store";

const EASE = [0.23, 1, 0.32, 1] as const;

/** Every capture blocker names itself, so no state is unexplained. */
const BLOCKER_MESSAGE: Record<CaptureBlocker, Parameters<ReturnType<typeof useMuraI18n>["t"]>[0]> = {
  authenticating: "sessionLoading",
  sign_in_required: "signInRequired",
  family_required: "familyRequiredToRecord",
  role_forbidden: "recordingNotAllowed",
  browser_unsupported: "recordingUnsupported",
  microphone_denied: "microphoneDenied",
  microphone_missing: "microphoneMissing",
};

function TimerChip({ seconds, recording }: { seconds: number; recording: boolean }) {
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.94 }}
      transition={{ duration: 0.26, ease: EASE }}
      className="flex h-11 shrink-0 items-center gap-2 rounded-full bg-raised px-4 shadow-soft"
    >
      {/* A slow breath rather than `animate-pulse`, whose hard opacity blink
          reads as an alert next to everything else on this screen. */}
      <motion.span
        className={cn("size-2 rounded-full", recording ? "bg-ink" : "bg-ink/35")}
        animate={recording ? { opacity: [1, 0.25, 1] } : { opacity: 1 }}
        transition={
          recording
            ? { duration: 1.7, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0.25 }
        }
      />
      <span className="text-body font-semibold leading-none tabular-nums">
        {formatTimer(seconds)}
      </span>
    </motion.span>
  );
}

export function RecordView() {
  const { locale: uiLanguage, t } = useMuraI18n();
  const router = useRouter();
  const { auth, family: familySession, capabilities, capabilitiesResolved } = useMuraSession();
  const family = familySession.selectedFamily;
  const microphone = useMicrophoneState();

  // Capture and processing are asked separately on purpose: a recogniser that
  // is merely degraded must not disable the microphone, because Core queues the
  // job durably and will process it when the recogniser returns.
  const capture = captureAvailability({
    authSettled: auth.status !== "loading",
    signedIn: auth.status === "authenticated",
    family,
    microphone,
  });
  const processing = processingAvailability(capabilities, capabilitiesResolved);
  const notice = processingNotice(processing);
  const maySubmit = canSubmitRecording(processing);
  // Who is speaking. Nothing is assumed: until the user says, the recording
  // cannot be submitted, because the alternative was labelling every memory in
  // every family with one hardcoded name.
  const [speaker, setSpeaker] = useState<Speaker | null>(null);
  const loadPeople = useCallback(
    (familyId: string, signal: AbortSignal) => fetchArchivePeople(familyId, signal),
    [],
  );
  const people = useArchiveResource<ArchivePerson[]>(loadPeople);
  /*
   * What MURA should expect to hear, chosen by the user in Settings.
   *
   * This was `useState(DEFAULT_AUDIO_LANGUAGE)` with no setter, so the four
   * language types were correctly separated but the audio one was unreachable —
   * a Kazakh-speaking family could not say what they were about to speak.
   *
   * Deliberately *not* derived from `uiLanguage`. Reading the interface in
   * Russian while recording a Kazakh grandmother is the normal case here, and
   * coupling the two is the bug this whole architecture exists to prevent.
   */
  const { audioLanguage } = useAudioLanguage();
  const [outputLanguage] = useState(DEFAULT_OUTPUT_LANGUAGE);
  const { status, seconds, level, error: recorderError, start, pause, resume, restart, finish: finishAudio } = useRecorder();
  const [uploading, setUploading] = useState(false);
  /** Synchronous double-submit guard; see `finish`. */
  const submitting = useRef(false);
  const [uploadError, setUploadError] = useState<"upload" | null>(null);
  const { sentences, reset, supported, error: recognitionError } = useLiveTranscript({
    listening: status === "recording",
    audioLanguage,
  });
  const mascot = useMascot();

  const startRecording = async () => {
    reset();
    setUploadError(null);
    mascot.send("LISTEN");
    await start();
  };

  const finish = async () => {
    // `uploading` is state, so two taps inside one frame both read `false` —
    // React has not re-rendered between them. A ref is set synchronously, so
    // the second tap sees the guard and no second job is created.
    if (seconds <= 0 || uploading || submitting.current) return;
    if (!speaker) return;
    // The family is captured here, once, and every later step of this workflow
    // uses this value. Switching the global selection mid-upload must not
    // redirect an in-flight recording into a different archive.
    const recordingFamilyId = family?.family_id;
    if (!recordingFamilyId) {
      setUploadError("upload");
      return;
    }
    submitting.current = true;
    // Thinking begins on the same tick the mic closes.
    mascot.send("PROCESS");
    setUploading(true);
    setUploadError(null);
    const audio = await finishAudio();
    if (!audio) {
      setUploadError("upload");
      setUploading(false);
      submitting.current = false;
      return;
    }
    const extension = audio.type.includes("mp4") ? "m4a" : "webm";
    const memoryId = `local-${crypto.randomUUID()}`;
    try {
      // The narrator sends a descriptive name and never a fabricated canonical
      // person id -- the signed-in account is not an archive Person.
      const accepted = await submitRecording(
        {
          audio,
          filename: `mura-recording.${extension}`,
          // The name the user gave, and a canonical id only when they picked
          // somebody the archive already knows. A typed name carries no id:
          // the browser must never manufacture an archive identity.
          speakerName: speaker.name,
          speakerPersonId: speaker.personId,
          audioLanguage,
          outputLanguage,
        },
        recordingFamilyId,
      );
      {
        const baseMemory: SavedMemory = {
          id: memoryId,
          createdAt: new Date().toISOString(),
          ui_language_at_creation: uiLanguage,
          audio_language: audioLanguage,
          detected_audio_language: "unknown",
          transcript_language: "unknown",
          output_language: outputLanguage,
          title: t("audioMemoryTitle"),
          // Deliberately empty: the pipeline writes the real summary when the
          // analysis validates. Seeding it with the transcript is what made
          // «Кратко» a verbatim copy of the recording.
          summary: "",
          // Web Speech is only a preview. The authoritative Core transcript
          // replaces this empty value after GigaAM completes.
          transcript: "",
          people: [],
          durationSec: seconds,
          source: "mura_core",
          status: "processing",
          analyzed: false,
        };
        await saveMemory({ ...baseMemory, source: "mura_core" }, audio);
        // The captured family travels with the workflow rather than being
        // re-derived downstream, so a reload or a global switch cannot rescope
        // the job poll or the result fetch.
        router.push(
          processingHref({
            jobId: accepted.job_id,
            recordingId: accepted.recording_id,
            memoryId,
            familyId: recordingFamilyId,
          }),
        );
        return;
      }
    } catch {
      setUploadError("upload");
      setUploading(false);
      submitting.current = false;
    }
  };

  const handleRestart = () => {
    reset();
    restart();
  };

  return (
    <div className="flex h-dvh flex-col">
      <AppHeader
        title={t("newMemory")}
        fallbackHref="/home"
        // Focus mode: this screen deliberately has no rail, so the back button
        // is the only way out and stays at every width. Step 5 revisits how the
        // screen uses desktop space; the header behaviour is unchanged here.
        standalone
        actions={
          <AnimatePresence>
            {(status !== "idle" || uploading) && (
              <TimerChip
                key="timer"
                seconds={seconds}
                recording={status === "recording"}
              />
            )}
          </AnimatePresence>
        }
      />

      <AnimatePresence mode="wait">
        {status === "idle" && !uploading ? (
          <motion.div
            key="idle"
            className="flex min-h-0 flex-1 flex-col overflow-y-auto"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, scale: 0.985 }}
            transition={{ duration: 0.3, ease: EASE }}
          >
            {/*
              One task, two halves, from `lg`.

              This was a 520px column centred in whatever window it got, so on a
              laptop several hundred pixels sat empty on either side of it while
              the two things that actually help — knowing who is speaking, and
              having a question to ask them — did not exist anywhere. The left
              half is unchanged and still the whole screen on a phone; the right
              half is the companion, which stacks underneath below `lg`.
            */}
            {/*
              The composition, rebuilt.

              What it replaces: a 224px swallow marooned at the top of an empty
              column, a display-sized heading crushed against the bottom of it,
              and the microphone — the only control this screen exists for —
              *below the fold* at 1440x900. Beside it, eight prompt cards in a
              wall that dominated the screen.

              Now the left column is one vertical group: mascot, question,
              control, in that order, sized so all three are visible together at
              900px. The heading steps down from display to title because it is
              a sentence spoken to a person, not a hero; the swallow grows
              because she is the warmth this moment needs.
            */}
            <div className="mx-auto grid min-h-full w-full max-w-focus grid-cols-1 items-center gap-10 px-page pb-8 lg:max-w-wide lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-16 xl:gap-20">
            <div className="flex w-full flex-col items-center justify-center gap-5 text-center">
              <MascotStage state={mascot.state} size={244} />
              <div className="w-full">
                <h1 className="text-balance text-title font-bold leading-[1.1] tracking-[-0.03em]">
                  {t("rememberPrompt").split("\n").map((line) => (
                    <span key={line} className="block">{line}</span>
                  ))}
                </h1>
                <p className="mx-auto mt-3 max-w-[32ch] text-body leading-relaxed text-muted">
                  {t("recordHintSecondary")}
                </p>
              </div>
              {/*
                The control is always here.

                It used to be replaced by a line of grey text whenever a speaker
                had not been chosen, which meant the record screen frequently
                had no record button on it at all. Now it is present and plainly
                disabled, with the one missing thing named directly underneath —
                and that thing is one tap away in the panel beside this.
              */}
              {capture.available && maySubmit ? (
                <div className="flex flex-col items-center gap-4">
                  <RecordButton
                    onClick={startRecording}
                    size={104}
                    label={t("startRecording")}
                    disabled={!speaker}
                  />
                  {!speaker && (
                    <p className="max-w-measure text-meta leading-relaxed text-muted">
                      {t("recordWhoRequired")}
                    </p>
                  )}
                  {/* Degradation is a status the user should see, but it is not
                      the subject of the screen: a filled warning block above the
                      microphone shouted louder than the thing it qualifies. */}
                  {notice === "queued_later" && (
                    <p
                      role="status"
                      className="flex max-w-measure items-start gap-2 text-meta leading-relaxed text-warning"
                    >
                      <span aria-hidden className="mt-[0.45em] size-1.5 shrink-0 rounded-full bg-warning" />
                      {t("processingDelayedNotice")}
                    </p>
                  )}
                </div>
              ) : (
                // Never a silently disabled button: say which condition failed
                // and, where the user can act, what to do about it.
                <p
                  role="status"
                  className="w-full max-w-measure rounded-surface bg-warning-surface px-4 py-2.5 text-meta leading-relaxed text-warning"
                >
                  {capture.available
                    ? t(processing === "unconfigured" ? "processingUnconfigured" : "coreUnavailable")
                    : t(BLOCKER_MESSAGE[capture.reason])}
                </p>
              )}
              {(recorderError || uploadError) && (
                <p
                  role="alert"
                  className="w-full max-w-measure rounded-surface bg-danger-surface px-4 py-2.5 text-meta leading-relaxed text-danger"
                >
                  {recorderError ? t("microphoneError") : t("uploadError")}
                </p>
              )}
            </div>

            <RecordCompanion
              people={people.data ?? []}
              speaker={speaker}
              onSpeakerChange={setSpeaker}
              familyName={family?.name ?? null}
            />
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="recording"
            className="mx-auto flex min-h-0 w-full max-w-default flex-1 flex-col px-5 sm:px-6"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.4, ease: EASE }}
          >
            <LiveTranscript
              sentences={sentences}
              listening={status === "recording"}
              supported={supported}
              recognitionError={recognitionError}
              className="min-h-0 flex-1"
            />
            <div className="shrink-0 pb-[max(env(safe-area-inset-bottom),20px)] pt-4">
              {/* She stays in frame while you talk, leaning in beside the waveform. */}
              <div className="mb-4 flex items-center gap-1">
                <Lastochka
                  state={mascot.state}
                  size={132}
                  className="-my-7 -ml-7 -mr-2"
                />
                <Waveform active={status === "recording"} level={level} className="flex-1" />
              </div>
              {!uploading && (
                <RecordControls
                  paused={status === "paused"}
                  onPause={pause}
                  onResume={resume}
                  onRestart={handleRestart}
                  onFinish={finish}
                />
              )}
              {uploading && (
                <p className="mt-3 text-center text-meta font-medium text-muted">
                  {t("uploading")}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
