"use client";

import { Mic } from "lucide-react";
import Link from "next/link";
import { useMuraI18n, type TranslationKey } from "@/lib/i18n";
import { pluralForm } from "@/lib/plural";

/**
 * The one thing this product is for, given the weight of it.
 *
 * ## What it replaces
 *
 * A black circle floating in beige with two lines of grey text under it, and a
 * separate list of counts somewhere off to the right. Nothing on the page was
 * dominant, nothing was asked of the user, and the archive's own size — the
 * fact that a family has *nine people and three generations* in here — was a
 * detail in a sidebar.
 *
 * ## Why it is filled
 *
 * The palette's strongest move is near-black on warm ivory, and this is the
 * screen's one place to spend it. A filled block does three things a card
 * cannot: it makes the page have a subject, it gives the record control a
 * ground that is not the same colour as everything else, and it stops the
 * archive's counts from reading as dashboard statistics — set on ink, under a
 * question, they read as the size of what the family has built.
 *
 * The question matters more than the button. «Что вы хотите сохранить сегодня?»
 * is a prompt to a person; «Записать воспоминание» is a label on a control.
 */

interface Snapshot {
  people: number;
  stories: number;
  generations: number;
}

export function RecordHero({ snapshot }: { snapshot: Snapshot | null }) {
  const { t, locale } = useMuraI18n();

  const count = (value: number, base: string) => {
    const form = pluralForm(value, locale);
    const suffix = form === "one" ? "One" : form === "few" ? "Few" : "Many";
    return `${value} ${t(`${base}${suffix}` as TranslationKey)}`;
  };

  return (
    <section className="overflow-hidden rounded-panel bg-ink-deep text-raised">
      <div className="flex flex-col gap-8 p-7 sm:p-9 lg:flex-row lg:items-center lg:justify-between lg:gap-12 lg:p-10">
        <div className="min-w-0">
          <h2 className="max-w-[18ch] text-balance text-[clamp(1.6rem,2.9vw,2.3rem)] font-semibold leading-[1.12] tracking-[-0.03em]">
            {t("homeHeroQuestion")}
          </h2>
          <p className="mt-3 max-w-[34ch] text-body leading-relaxed text-raised/60">
            {t("homeHeroHint")}
          </p>

          <Link
            href="/record"
            className="mt-7 inline-flex min-h-[56px] items-center gap-3 rounded-full bg-raised px-6 text-item font-semibold text-ink transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] hover:scale-[1.015] active:scale-[0.98] [--focus-ring-offset:4px] focus-ring"
          >
            <Mic aria-hidden className="size-5" strokeWidth={2} />
            {t("recordMemory")}
          </Link>
        </div>

        {/*
          The archive's own size, as a dateline rather than a stat row.
          Deliberately not three boxes: numbers in boxes are a dashboard, and
          numbers in a line under a rule are a masthead.
        */}
        {snapshot && snapshot.people > 0 && (
          <dl className="flex shrink-0 flex-wrap gap-x-7 gap-y-3 border-t border-raised/15 pt-6 lg:flex-col lg:gap-5 lg:border-l lg:border-t-0 lg:pl-12 lg:pt-0">
            {[
              { value: count(snapshot.people, "homePeople"), key: "people" },
              { value: count(snapshot.stories, "homeStories"), key: "stories" },
              ...(snapshot.generations > 1
                ? [{ value: count(snapshot.generations, "homeGenerations"), key: "gen" }]
                : []),
            ].map((entry) => (
              <div key={entry.key}>
                {/* One element, not a number over a label: «9 человек» is a
                    phrase, and splitting it into a figure and a caption is how
                    it turns into a metric tile. */}
                {/* Never broken across lines: «9 человек» is one phrase, and wrapping
                    it turns a sentence into a figure with a caption under it —
                    which is the metric tile this deliberately is not. */}
                <dd className="whitespace-nowrap text-item font-medium tabular-nums text-raised/85">
                  {entry.value}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  );
}
