"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useRef } from "react";
import type { LiveSentence } from "@/hooks/use-live-transcript";
import { useMuraI18n } from "@/lib/i18n";
import { toneBg } from "@/lib/tones";
import { cn } from "@/lib/utils";

interface LiveTranscriptProps {
  sentences: LiveSentence[];
  listening: boolean;
  supported: boolean | null;
  recognitionError: string | null;
  className?: string;
}

const sentenceClass =
  "mb-4 text-title font-semibold leading-[1.3] tracking-[-0.02em]";

/** Word entrance: opacity 0→1, translateY 8→0, ~220ms, ease-out. */
const WORD_IN = { duration: 0.22, ease: [0.23, 1, 0.32, 1] as const };

/**
 * Only the newest phrases keep motion nodes. Older ones settle into plain
 * spans with an identical box model, so a long dictation never accumulates
 * hundreds of animated elements — and nothing reflows when they swap.
 */
const ANIMATED_TAIL = 2;

/** Follow the tail only while the reader is already near the bottom. */
const FOLLOW_THRESHOLD = 160;

/**
 * Spacing is padding, not margin, so a highlighted word's tint runs into its
 * neighbour and the row reads as one continuous highlighter stroke rather than
 * a string of separate chips. It also means the tint belongs to the word
 * itself — so it fades in *with* the word instead of the mark racing ahead of
 * text that has not appeared yet. Only the true ends of the phrase are
 * rounded; a stroke that runs to the margin is what a real highlighter does.
 */
const wordClass = "inline-block pe-[0.26em] py-[0.06em]";
const wordTint = "transition-colors duration-[420ms] ease-[cubic-bezier(0.23,1,0.32,1)]";

function Word({
  text,
  animate,
  highlight,
  first,
  last,
  caret,
}: {
  text: string;
  animate: boolean;
  highlight: boolean;
  first: boolean;
  last: boolean;
  caret: boolean;
}) {
  const className = cn(
    wordClass,
    wordTint,
    highlight && toneBg.peach,
    // The negative inline-start margin cancels the lead-in padding, so the
    // highlighted line still aligns with the paragraphs above it.
    highlight && first && "rounded-s-[0.3em] ps-[0.14em] -ms-[0.14em]",
    highlight && last && "rounded-e-[0.3em] pe-[0.14em]",
  );
  // The caret lives inside the last word so it can never wrap onto a line of
  // its own, stranded below the text.
  const content = (
    <>
      {text}
      {caret && <Caret />}
    </>
  );
  if (!animate) return <span className={className}>{content}</span>;
  return (
    <motion.span
      className={className}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={WORD_IN}
    >
      {content}
    </motion.span>
  );
}

function Caret() {
  return (
    <span
      aria-hidden
      className="ml-0.5 inline-block h-[0.9em] w-[3px] translate-y-[0.14em] animate-caret rounded-full bg-ink"
    />
  );
}

/**
 * The hero of the recording screen.
 *
 * Words are keyed by position, so recognition updates append rather than
 * replace: a word that has already appeared keeps its element and never
 * re-animates, even when the recognizer revises the phrase around it or
 * promotes the whole thing from interim to final. The highlighter just fades
 * off the phrase as it settles.
 */
export function LiveTranscript({
  sentences,
  listening,
  supported,
  recognitionError,
  className,
}: LiveTranscriptProps) {
  const { t } = useMuraI18n();
  const reduced = useReducedMotion() ?? false;
  const scrollRef = useRef<HTMLDivElement>(null);

  // The sentences array is rebuilt on every render, so depend on its shape.
  const signature = useMemo(
    () => sentences.map((sentence) => sentence.text.length).join(","),
    [sentences],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance < FOLLOW_THRESHOLD) {
      el.scrollTo({ top: el.scrollHeight, behavior: reduced ? "auto" : "smooth" });
    }
  }, [signature, reduced]);

  const lastComplete = sentences.filter((sentence) => sentence.complete).length - 1;
  const placeholder =
    sentences.length > 0
      ? null
      : supported === false
        ? t("liveTextUnavailable")
        : recognitionError
          ? t("speechRecognitionError")
          : t("listening");

  return (
    <div
      ref={scrollRef}
      className={cn("overflow-y-auto", className)}
      aria-live="polite"
      style={{
        maskImage: "linear-gradient(to bottom, transparent 0, black 56px)",
        WebkitMaskImage: "linear-gradient(to bottom, transparent 0, black 56px)",
      }}
    >
      <div className="pb-2 pt-16">
        {placeholder && (
          <p className={cn(sentenceClass, "text-ink/40")}>
            {placeholder}
            {listening && supported !== false && !recognitionError && <Caret />}
          </p>
        )}

        {sentences.map((sentence, index) => {
          const animated = !reduced && index >= sentences.length - ANIMATED_TAIL;
          const words = sentence.text.split(/\s+/).filter(Boolean);
          // Older phrases recede rather than vanish.
          const opacity = sentence.complete
            ? Math.max(0.32, 0.88 - (lastComplete - index) * 0.17)
            : 1;

          return (
            <p
              key={index}
              className={sentenceClass}
              style={{ opacity, transition: "opacity 420ms var(--ease-swift)" }}
            >
              {/* Structure is identical across interim → final, so the words
                  are never remounted; the highlighter simply lifts off them. */}
              {words.map((word, wordIndex) => (
                <Word
                  key={wordIndex}
                  text={word}
                  animate={animated}
                  highlight={!sentence.complete}
                  first={wordIndex === 0}
                  last={wordIndex === words.length - 1}
                  caret={
                    !sentence.complete &&
                    listening &&
                    wordIndex === words.length - 1
                  }
                />
              ))}
            </p>
          );
        })}
      </div>
    </div>
  );
}
