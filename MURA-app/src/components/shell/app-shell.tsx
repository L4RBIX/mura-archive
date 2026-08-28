"use client";

/**
 * The responsive product shell.
 *
 * What this replaces: a single `max-w-[430px]` column that every screen lived
 * inside, at every window size. On a phone that was right; on a laptop it was
 * a phone app stranded in the middle of a grey field, with no navigation and
 * no indication of which family you were even looking at.
 *
 * The fix is not "remove the cap and let everything stretch" — long lines of
 * Russian prose across 1440px are worse than a narrow column. Each surface
 * declares the width it actually wants (see PageContainer), and the shell
 * supplies the spatial architecture around it:
 *
 *   < 1024px   content column + fixed bottom tab bar
 *   >= 1024px  persistent left rail + content, no bottom bar
 *
 * Same product, same brand, different spatial strategy. Deliberately not a
 * separate desktop app.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ChevronsUpDown } from "lucide-react";
import { SearchProvider } from "@/components/search/search-provider";
import {
  ArchiveOverviewProvider,
  useArchiveOverview,
} from "@/lib/mura/use-archive-overview";
import { hasAppChrome, isActive, isPreProduct, NAV_ITEMS } from "@/components/shell/navigation";
import { useMuraSession } from "@/lib/mura/session-provider";
import { LanguageSwitcher, useMuraI18n } from "@/lib/i18n";

/**
 * The rail.
 *
 * What it stops being: a workspace sidebar. The previous one was a wordmark, a
 * boxed "workspace picker", and five identically-weighted rows — the shape of
 * Notion or a CRM, on a product that is neither.
 *
 * Three changes carry it:
 *
 *   Recording is not navigation. Going somewhere and doing the one thing the
 *   product exists for are different acts, so the recorder is a filled control
 *   above the list rather than a fifth tab tinted peach to look important.
 *
 *   The family is a masthead at the foot of the rail, with its own counts, the
 *   way a publication's name and volume sit on a page. It is the answer to
 *   "whose archive is this" and it belongs with the identity, not floating in a
 *   rounded box near the top.
 *
 *   No uppercase eyebrows anywhere. «Мұра» sits *under* the wordmark as its
 *   Kazakh name, which is information, rather than above it as a label.
 */
function RailFamily() {
  const { t } = useMuraI18n();
  const { auth, family, phase, selectFamily } = useMuraSession();
  const archive = useArchiveOverview();

  if (phase === "booting" || phase === "families_loading") {
    return (
      <div aria-hidden className="min-w-0">
        <div className="h-4 w-28 animate-pulse rounded-full bg-sand" />
        <div className="mt-2 h-3 w-36 animate-pulse rounded-full bg-sand/70" />
      </div>
    );
  }
  if (auth.status !== "authenticated" || !family.selectedFamily) return null;

  const counts = archive
    ? [
        `${archive.people_count} ${t(archive.people_count === 1 ? "homePeopleOne" : "homePeopleMany")}`,
        `${archive.story_count} ${t(archive.story_count === 1 ? "homeStoriesOne" : "homeStoriesMany")}`,
      ].join(" · ")
    : null;

  return (
    <div className="min-w-0">
      {family.families.length < 2 ? (
        <p className="truncate text-body font-semibold" title={family.selectedFamily.name}>
          {family.selectedFamily.name}
        </p>
      ) : (
        <>
          <label htmlFor="rail-family" className="sr-only">
            {t("switchFamily")}
          </label>
          <div className="relative flex items-center">
            <select
              id="rail-family"
              value={family.selectedFamilyId ?? ""}
              onChange={(event) => selectFamily(event.target.value)}
              className="w-full cursor-pointer appearance-none truncate rounded-control bg-transparent pr-6 text-body font-semibold text-ink outline-none focus-ring"
            >
              {family.families.map((entry) => (
                <option key={entry.family_id} value={entry.family_id}>
                  {entry.name}
                </option>
              ))}
            </select>
            <ChevronsUpDown aria-hidden className="pointer-events-none absolute right-0 size-3.5 text-muted" />
          </div>
        </>
      )}
      {counts && <p className="mt-1 truncate text-caption text-muted">{counts}</p>}
    </div>
  );
}

function DesktopRail() {
  const { t } = useMuraI18n();
  const pathname = usePathname();
  const secondary = NAV_ITEMS.filter((item) => !item.primary);
  const record = NAV_ITEMS.find((item) => item.primary);

  return (
    <nav
      aria-label={t("navPrimary")}
      className="fixed inset-y-0 left-0 z-40 hidden w-[260px] flex-col border-r border-ink/[0.07] bg-raised px-5 py-7 lg:flex"
    >
      <Link href="/home" className="block rounded-control focus-ring">
        <span className="block text-[1.6rem] font-bold leading-none tracking-[-0.045em]">
          Mura
        </span>
        <span className="mt-1 block text-caption text-muted">Мұра</span>
      </Link>

      {record && (
        <Link
          href={record.href}
          className="mt-7 flex min-h-12 items-center gap-2.5 rounded-full bg-ink-deep px-4 text-body font-semibold text-raised transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] active:scale-[0.98] focus-ring"
        >
          <record.icon aria-hidden className="size-[18px] shrink-0" strokeWidth={2} />
          <span className="truncate">{t(record.labelKey)}</span>
        </Link>
      )}

      <ul className="mt-7 flex flex-col gap-0.5">
        {secondary.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 items-center gap-3 rounded-control px-3 text-body transition-colors focus-ring ${
                  active
                    ? "bg-sand font-semibold text-ink"
                    : "font-medium text-ink/65 hover:bg-sand/60 hover:text-ink"
                }`}
              >
                <Icon aria-hidden className="size-[18px] shrink-0" strokeWidth={active ? 2.2 : 1.9} />
                <span className="truncate">{t(item.labelKey)}</span>
              </Link>
            </li>
          );
        })}
      </ul>

      {/* The masthead sits at the foot, under a rule, the way a publication's
          name and volume do. `mt-auto` rather than a fixed gap so it holds the
          bottom of the rail at any height. */}
      <div className="mt-auto border-t border-ink/[0.08] pt-4">
        <RailFamily />
      </div>
    </nav>
  );
}

function MobileTabBar() {
  const { t } = useMuraI18n();
  const pathname = usePathname();

  return (
    <nav
      aria-label={t("navPrimary")}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-ink/[0.06] bg-raised/95 backdrop-blur lg:hidden"
    >
      <ul className="mx-auto flex max-w-form items-stretch justify-around px-1 pb-[max(env(safe-area-inset-bottom),8px)] pt-1.5">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                // 56px tall: comfortably past the 44px touch-target floor
                // without eating the screen on a small phone.
                className="flex min-h-[56px] flex-col items-center justify-center gap-1 rounded-control px-1 focus-ring"
              >
                <span
                  className={`flex size-8 items-center justify-center rounded-full transition-colors ${
                    active
                      ? "bg-ink text-raised"
                      : item.primary
                        ? "bg-peach text-ink"
                        : "text-ink/55"
                  }`}
                >
                  <Icon aria-hidden className="size-[18px]" strokeWidth={2} />
                </span>
                <span
                  className={`text-caption leading-none ${active ? "font-semibold text-ink" : "text-muted"}`}
                >
                  {t(item.labelKey)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useMuraI18n();
  const pathname = usePathname();
  const chrome = hasAppChrome(pathname);

  if (!chrome) {
    // Landing, auth and the two focus screens.
    //
    // The switcher floats only before the product starts, where there is no
    // rail and no Settings to reach: someone arriving in Kazakh has to be able
    // to change the language before signing in. Record and processing are
    // deliberately excluded — the user is mid-task, often sitting opposite the
    // person whose story they are capturing, and interface language is not a
    // decision to put in front of them at that moment.
    return (
      <>
        {isPreProduct(pathname) && <LanguageSwitcher variant="floating" />}
        <main id="mura-content" className="relative">
          {children}
        </main>
      </>
    );
  }

  // Search is mounted only inside the product chrome: the pre-product screens
  // have no archive to search.
  return (
    <ArchiveOverviewProvider>
    <SearchProvider>
      <a
        href="#mura-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[80] focus:rounded-full focus:bg-ink focus:px-4 focus:py-2 focus:text-meta focus:font-semibold focus:text-raised"
      >
        {t("skipToContent")}
      </a>

      <DesktopRail />

      <main
        id="mura-content"
        // Left gutter matches the rail; bottom gutter clears the tab bar so no
        // screen has to know either exists.
        className="relative min-h-dvh pb-[calc(72px+max(env(safe-area-inset-bottom),8px))] lg:pb-0 lg:pl-[260px]"
      >
        {children}
      </main>

      <MobileTabBar />
    </SearchProvider>
    </ArchiveOverviewProvider>
  );
}
