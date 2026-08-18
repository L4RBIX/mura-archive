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
import { SearchProvider } from "@/components/search/search-provider";
import { FamilyContext } from "@/components/shell/family-context";
import { hasAppChrome, isActive, isPreProduct, NAV_ITEMS } from "@/components/shell/navigation";
import { LanguageSwitcher, useMuraI18n } from "@/lib/i18n";

function DesktopRail() {
  const { t } = useMuraI18n();
  const pathname = usePathname();

  return (
    <nav
      aria-label={t("navPrimary")}
      className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-ink/[0.06] bg-raised/60 px-4 py-6 lg:flex"
    >
      <Link
        href="/home"
        className="mb-7 block rounded-control px-2 focus-ring"
      >
        <span className="block text-caption font-semibold uppercase tracking-[0.28em] text-muted">
          мұра
        </span>
        <span className="block text-title font-bold leading-none tracking-[-0.03em]">
          Mura
        </span>
      </Link>

      <div className="mb-6 rounded-surface bg-paper/70 px-3 py-2.5">
        <FamilyContext />
      </div>

      <ul className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-control px-3 py-2.5 text-body font-medium transition-colors focus-ring ${
                  active
                    ? "bg-ink text-raised"
                    : item.primary
                      ? "bg-clay/60 text-ink hover:bg-clay"
                      : "text-ink/70 hover:bg-sand"
                }`}
              >
                <Icon aria-hidden className="size-[18px] shrink-0" strokeWidth={2} />
                <span className="truncate">{t(item.labelKey)}</span>
              </Link>
            </li>
          );
        })}
      </ul>

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
                        ? "bg-clay text-ink"
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
        className="relative min-h-dvh pb-[calc(72px+max(env(safe-area-inset-bottom),8px))] lg:pb-0 lg:pl-[248px]"
      >
        {children}
      </main>

      <MobileTabBar />
    </SearchProvider>
  );
}
