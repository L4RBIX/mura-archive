"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { DemoNotice } from "@/components/demo/demo-notice";
import { ScreenHeader } from "@/components/layout/screen-header";
import { MemoryAnswerCard } from "@/components/ask/memory-answer-card";
import { MascotStage } from "@/components/mascot/mascot-stage";
import { RecordButton } from "@/components/record/record-button";
import { Button } from "@/components/ui/button";
import { useLiveTranscript } from "@/hooks/use-live-transcript";
import { useMascot } from "@/hooks/use-mascot";
import { useRecorder } from "@/hooks/use-recorder";
import { PageContainer } from "@/components/shell/page-container";
import { useMuraI18n } from "@/lib/i18n";
import { DEFAULT_AUDIO_LANGUAGE } from "@/lib/language";
import {
  mustafaDemoMemory,
  type DemoMemory,
} from "@/lib/mascot/demo-memory";
import { BUSY_STATES } from "@/lib/mascot/machine";

const EASE = [0.23, 1, 0.32, 1] as const;

/** Short, intentional thinking beat before the scripted demo answer. */
const ANSWER_AT = 1_300;

export function AskView() {
  const { t } = useMuraI18n();
  const [audioLanguage] = useState(DEFAULT_AUDIO_LANGUAGE);
  const {
    start: startAudio,
    finish: finishAudio,
    error: recorderError,
  } = useRecorder();
  const mascot = useMascot();
  const { state, send } = mascot;

  const [listening, setListening] = useState(false);
  const [memory, setMemory] = useState<DemoMemory | null>(null);
  const {
    sentences,
    reset,
    supported,
    error,
    previewMode,
  } = useLiveTranscript({
    listening,
    audioLanguage,
  });
  const timers = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const startListening = useCallback(async () => {
    clearTimers();
    reset();
    setMemory(null);
    await startAudio();
    setListening(true);
    send("LISTEN");
  }, [clearTimers, reset, send, startAudio]);

  const finishListening = useCallback(async () => {
    setListening(false);
    // Thinking starts on the same tick the mic closes — never a dead beat.
    send("PROCESS");
    await finishAudio();
    const found = mustafaDemoMemory();

    timers.current.push(
      window.setTimeout(() => {
        // The answer is shown, not spoken.
        send("SEARCH");
        setMemory(found);
        send("SUCCEED");
      }, ANSWER_AT),
    );
  }, [finishAudio, send]);

  const askAgain = useCallback(() => {
    clearTimers();
    reset();
    setMemory(null);
    send("RESET");
  }, [clearTimers, reset, send]);

  const spoken = sentences.map((sentence) => sentence.text).join(" ").trim();
  const busy = BUSY_STATES.has(state);
  const answering = state === "speaking" || state === "success";

  const status =
    state === "searching"
      ? t("askSearching")
      : busy
        ? t("askThinking")
        : listening
          ? spoken || t("askSpeakNow")
          : null;

  return (
    <div className="flex min-h-dvh flex-col">
      <ScreenHeader title={t("askMemory")} fallbackHref="/home" />

      {/* This screen answers *any* question with the same scripted fixture.
          Without this notice it reads as grounded family intelligence, which
          is the one impression MURA must never give. Real, evidence-grounded
          Ask is a later capability. */}
      <PageContainer>
        <DemoNotice surface="ask" className="mt-1 flex items-start gap-2.5 rounded-surface bg-clay/45 px-4 py-3 text-left" />
      </PageContainer>

      <div className="mx-auto flex w-full max-w-[560px] flex-1 flex-col items-center px-5 pb-[max(env(safe-area-inset-bottom),24px)] sm:px-6">
        <MascotStage state={state} size={300} className="mt-2" />

        <AnimatePresence mode="wait">
          {memory ? (
            <motion.div key="memory" className="w-full" exit={{ opacity: 0 }}>
              <MemoryAnswerCard memory={memory} />
            </motion.div>
          ) : (
            <motion.div
              key="prompt"
              className="w-full text-center"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.4, ease: EASE }}
            >
              <h1 className="text-balance text-title font-bold leading-[1.15] tracking-[-0.03em]">
                {t("askTitle").split("\n").map((line) => (
                  <span key={line} className="block">
                    {line}
                  </span>
                ))}
              </h1>
              <p className="mt-3 text-body leading-relaxed text-ink/70">{t("askHint")}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Reserved height: the status line must never shift the layout. */}
        <div className="flex min-h-[76px] w-full max-w-[330px] items-center justify-center px-2 py-4">
          <AnimatePresence mode="wait">
            {status && (
              <motion.p
                key={status}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.3, ease: EASE }}
                className="text-center text-body font-medium leading-snug text-ink/70"
              >
                {status.split("\n").map((line) => (
                  <span key={line} className="block">
                    {line}
                  </span>
                ))}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <div className="mt-auto flex w-full flex-col items-center gap-4 pt-2">
          {listening ? (
            <Button size="lg" className="w-full max-w-[300px]" onClick={finishListening}>
              {t("askFinish")}
            </Button>
          ) : answering ? (
            <Button
              variant="soft"
              size="lg"
              className="w-full max-w-[300px]"
              onClick={askAgain}
            >
              {t("askAgain")}
            </Button>
          ) : (
            <RecordButton onClick={startListening} size={92} label={t("askMemory")} />
          )}

          {supported === false &&
            previewMode === "explicit_language" &&
            !listening && (
            <p className="max-w-[300px] text-center text-meta leading-relaxed text-ink/65">
              {t("liveTextUnavailable")}
            </p>
          )}
          {(error || recorderError) && listening && (
            <p className="max-w-[300px] text-center text-meta leading-relaxed text-ink/65">
              {t("speechRecognitionError")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
