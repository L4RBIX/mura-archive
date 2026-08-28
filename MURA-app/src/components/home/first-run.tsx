"use client";

import Link from "next/link";
import { VoiceToFamily } from "@/components/brand/voice-to-family";
import { useMuraI18n } from "@/lib/i18n";
import { promptsForRole, useNarratorRole } from "@/lib/mura/narrator-role";

/**
 * Home, before there is an archive.
 *
 * An empty archive is the state every family starts in, and it was being served
 * by one grey sentence under a heading — on a 1440px window that left most of
 * the screen blank at the exact moment the user has the least idea what to do.
 *
 * So this is not an "empty state" in the apologetic sense. It is the first-run
 * screen: it says what the next five minutes look like, and it hands over four
 * questions, because "press record and talk to your grandmother" is a much
 * harder instruction to follow than it sounds. The questions are the same ones
 * the recorder offers, so nothing here is invented for the empty case.
 *
 * Nothing on it counts anything. There is no archive to summarise yet, and a
 * row of zeroes is how a family archive starts looking like a dashboard.
 */

/** Four openings. Which four depends on who said they were holding the phone. */
const PROMPT_COUNT = 4;

export function FirstRun() {
  const { t } = useMuraI18n();
  /*
   * The one thing the role question actually changes.
   *
   * Someone recording their own life is offered their own childhood first;
   * someone sitting opposite an elder is offered the questions that open that
   * person up. Before anyone has answered — and for «другое» — this is the
   * neutral order, so the panel is complete either way and the question is
   * never a prerequisite for anything.
   */
  const { role } = useNarratorRole();
  const prompts = promptsForRole(role, PROMPT_COUNT);

  return (
    <section className="relative overflow-hidden rounded-panel bg-raised/70 px-6 py-7 sm:px-8 sm:py-9">
      {/* The motif, quiet and corner-anchored: this panel is mostly words, and
          the circles are here to keep the surface from reading as a form. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-10 top-2 w-56 text-ink/35 sm:-right-4 sm:w-64 lg:w-72"
      >
        <VoiceToFamily className="size-full" delay={0.15} />
      </div>

      <div className="relative max-w-[46ch]">
        <h2 className="text-section font-bold leading-snug tracking-[-0.02em]">
          {t("homeFirstRunTitle")}
        </h2>
        <p className="mt-2.5 text-body leading-relaxed text-ink/70">{t("homeFirstRunBody")}</p>
      </div>

      <div className="relative mt-7">
        <h3 className="text-meta font-semibold tracking-[-0.005em] text-ink/70">
          {t("homeFirstRunPromptsTitle")}
        </h3>
        {/*
          Each question is a link into the recorder rather than a static
          example. Somebody who reads one and thinks "yes, that one" should be
          one tap from asking it, not left to remember it on the way.
        */}
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {prompts.map((prompt) => (
            <li key={prompt}>
              <Link
                href="/record"
                className="flex min-h-11 items-center rounded-control bg-paper/80 px-3.5 py-2.5 text-meta leading-snug text-ink/80 transition-colors hover:bg-paper focus-ring"
              >
                {t(prompt)}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
