"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { VoiceToFamily } from "@/components/brand/voice-to-family";
import { Button } from "@/components/ui/button";
import { useMuraI18n, type TranslationKey } from "@/lib/i18n";

const EASE = [0.23, 1, 0.32, 1] as const;

function reveal(delay: number) {
  return {
    initial: { opacity: 0, y: 18 },
    animate: { opacity: 1, y: 0 },
    transition: { delay, duration: 0.7, ease: EASE },
  };
}

/** What actually happens, in three steps, in the order it happens. */
const STEPS: ReadonlyArray<{ title: TranslationKey; body: TranslationKey }> = [
  { title: "landingStepRecord", body: "landingStepRecordBody" },
  { title: "landingStepUnderstand", body: "landingStepUnderstandBody" },
  { title: "landingStepArchive", body: "landingStepArchiveBody" },
];

/**
 * The first thing anyone sees.
 *
 * ## What this replaces
 *
 * A wordmark, one line of tagline and a single «Начать» that walked straight
 * into `/home`. At 1440 it was a narrow strip of type against most of a screen
 * of empty paper, and it never said what the product does or offered the two
 * things a visitor actually arrives wanting: start one, or get back into mine.
 *
 * ## The shape
 *
 * Two columns from `lg`: the words on the left, the generations motif holding
 * the right and running past the edge of the viewport. The motif is the
 * signature — overlapping circles whose shared area is the memory two
 * generations both carry — and it is doing the work the empty half used to do.
 *
 * Below the fold, three steps in the order they happen. Deliberately not
 * numbered: «01 / 02 / 03» would assert a sequence the visitor must complete,
 * and this is a description of what the product does, not a checklist.
 *
 * Stacked on a phone, where the motif sits behind the wordmark at low opacity
 * rather than above it — a full-height decorative panel would push both calls
 * to action off a 667px screen.
 */
export function OnboardingView() {
  const { t } = useMuraI18n();

  return (
    <div className="relative min-h-dvh overflow-hidden">
      <div className="mx-auto w-full max-w-wide px-page pb-[max(env(safe-area-inset-bottom),40px)] pt-chrome 2xl:max-w-wide-2xl">
        {/*
          `items-center` and a min-height, not `min-h-dvh` on the grid itself:
          the second column has to be able to overflow the fold on a short
          laptop without the three steps below becoming unreachable.
        */}
        <div className="grid items-center gap-x-12 gap-y-10 lg:min-h-[70dvh] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] xl:gap-x-16">
          <div className="relative z-10">
            <h1
              aria-label="Mura"
              className="text-[clamp(3.75rem,10vw,6.5rem)] font-bold leading-[0.92] tracking-[-0.045em]"
            >
              {"Mura".split("").map((letter, index) => (
                <motion.span
                  key={index}
                  aria-hidden
                  className="inline-block"
                  initial={{ opacity: 0, y: 24 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.12 + index * 0.06, duration: 0.7, ease: EASE }}
                >
                  {letter}
                </motion.span>
              ))}
            </h1>

            {/* The Kazakh name of the product, under it. Above the wordmark it
                was a kicker repeating the same word in another script. */}
            <motion.p {...reveal(0.4)} className="mt-2 text-item text-muted">
              Мұра
            </motion.p>

            <motion.p
              {...reveal(0.45)}
              className="mt-6 max-w-[16ch] text-[clamp(1.5rem,3.2vw,2.25rem)] font-semibold leading-[1.15] tracking-[-0.02em]"
            >
              {t("tagline")
                .split("\n")
                .map((line) => (
                  <span key={line} className="block">
                    {line}
                  </span>
                ))}
            </motion.p>

            <motion.p
              {...reveal(0.58)}
              className="mt-5 max-w-[46ch] text-reading leading-relaxed text-ink/70"
            >
              {t("landingBody")}
            </motion.p>

            {/*
              Two doors, weighted. Creating an archive is what this page is for;
              signing in is what the returning half of the audience needs and
              must not have to hunt for. Stacked full-width on a phone so both
              clear the touch-target floor without crowding each other.
            */}
            <motion.div
              {...reveal(0.72)}
              className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center"
            >
              <Button asChild size="lg" className="w-full sm:w-auto">
                <Link href="/sign-up">{t("landingCreate")}</Link>
              </Button>
              <Link
                href="/sign-in"
                className="flex h-14 items-center justify-center rounded-full px-6 text-item font-semibold text-ink/70 transition-colors hover:text-ink sm:justify-start focus-ring"
              >
                {t("landingSignIn")}
              </Link>
            </motion.div>

            <motion.p {...reveal(0.82)} className="mt-6 text-meta text-muted">
              {t("landingPrivacyNote")}
            </motion.p>
          </div>

          {/*
            The motif.

            Behind the type and faint on a phone; a column of its own from `lg`,
            where it is allowed to run past the right edge so the composition
            does not feel boxed. `-z-0` keeps it under the words at every size.
          */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-[-18%] -z-0 flex w-[86%] items-center text-ink/45 opacity-45 sm:right-[-6%] sm:w-[62%] lg:relative lg:inset-auto lg:right-auto lg:z-0 lg:w-auto lg:text-ink lg:opacity-100"
          >
            {/* Allowed past the right edge of the container from `lg`: a motif
                that stops politely at the gutter leaves exactly the band of
                dead paper this layout exists to remove. */}
            <VoiceToFamily
              delay={0.25}
              className="size-full lg:h-auto lg:w-[136%] lg:max-w-none lg:translate-x-[12%]"
            />
          </div>
        </div>

        {/* What the product does, once someone has decided to keep reading. */}
        <motion.section
          {...reveal(0.95)}
          className="relative z-10 mt-16 border-t border-ink/[0.08] pt-10 lg:mt-24"
        >
          <ul className="grid gap-8 sm:grid-cols-3 sm:gap-10">
            {STEPS.map((step) => (
              <li key={step.title}>
                <h2 className="text-item font-semibold tracking-[-0.01em]">{t(step.title)}</h2>
                <p className="mt-2 max-w-[34ch] text-body leading-relaxed text-muted">
                  {t(step.body)}
                </p>
              </li>
            ))}
          </ul>
        </motion.section>
      </div>
    </div>
  );
}
