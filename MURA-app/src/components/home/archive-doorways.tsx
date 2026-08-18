"use client";

import { ChevronRight, HelpCircle, Scale, Trees } from "lucide-react";
import Link from "next/link";
import { useMuraI18n, type TranslationKey } from "@/lib/i18n";
import { pluralForm } from "@/lib/plural";
import type { ArchiveOverview } from "@/lib/mura/archive-api";

/**
 * Quiet ways further into the archive.
 *
 * These used to be four cards the same size and weight as everything else on
 * the page, which left Home with no dominant action and the eye nowhere to
 * land. They are a plain list now: still tappable, still labelled with real
 * counts, but visibly secondary to recording a memory.
 *
 * «Все воспоминания» is gone from here — the memories themselves are on the
 * page, and a link to a list of what is already visible is a doorway to
 * nowhere new.
 */
export function ArchiveDoorways({ overview }: { overview: ArchiveOverview }) {
  const { t, locale } = useMuraI18n();

  const count = (n: number, base: string): string => {
    const form = pluralForm(n, locale);
    const suffix = form === "one" ? "One" : form === "few" ? "Few" : "Many";
    return `${n} ${t(`${base}${suffix}` as TranslationKey)}`;
  };

  return (
    <nav className="divide-y divide-ink/[0.06] border-y border-ink/[0.06]">
      <Doorway
        href="/tree"
        icon={Trees}
        title={t("homeOpenTree")}
        detail={count(overview.people_count, "homePeople")}
      />
      {overview.review_count > 0 && (
        <Doorway
          href="/review"
          icon={HelpCircle}
          title={t("homeOpenReview")}
          // The count is the detail. Repeating the title underneath it, as
          // «Нужно уточнить: 2» did, says nothing the row has not said.
          detail={count(overview.review_count, "reviewCount")}
        />
      )}
      {/*
        Preserved conflicts are one of the things that make this an archive
        rather than a transcription service — the product keeps two versions of
        a memory instead of overwriting one — and `open_conflict_count` was
        arriving from Core with nothing in the interface reading it.

        Shown only when there is genuinely something to look at, like the review
        row above: a permanent «0 расхождений» would turn a doorway into a
        statistic, and Home is not a dashboard.
      */}
      {overview.open_conflict_count > 0 && (
        <Doorway
          href="/review"
          icon={Scale}
          title={t("homeOpenConflicts")}
          detail={count(overview.open_conflict_count, "conflictCount")}
        />
      )}
    </nav>
  );
}

function Doorway({
  href,
  icon: Icon,
  title,
  detail,
}: {
  href: string;
  icon: typeof Trees;
  title: string;
  detail: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-3.5 py-3.5 transition-colors focus-ring"
    >
      <Icon aria-hidden className="size-5 shrink-0 text-ink/45" strokeWidth={1.8} />
      <span className="min-w-0 flex-1">
        <span className="block text-body font-medium leading-tight">{title}</span>
        <span className="block text-meta text-muted">{detail}</span>
      </span>
      <ChevronRight
        aria-hidden
        className="size-4 shrink-0 text-muted transition-transform group-hover:translate-x-0.5"
        strokeWidth={2}
      />
    </Link>
  );
}
