"use client";

import { Search } from "lucide-react";
import type { ReactNode } from "react";
import { useArchiveSearch } from "@/components/search/search-provider";
import { useMuraI18n } from "@/lib/i18n";
import { BackButton } from "./back-button";
import {
  PageContainer,
  type ContentWidth,
} from "@/components/shell/page-container";

interface AppHeaderProps {
  /** The screen's name. Centred on mobile, left-aligned on desktop. */
  title?: string;
  /** Where back goes when there is no history, e.g. after a deep link. */
  fallbackHref?: string;
  /** Right-hand slot: page actions, a running timer, search. */
  actions?: ReactNode;
  /**
   * Set when the page already renders its own visible title — a person's name,
   * a story's title. The desktop header then carries only actions, so the
   * screen never shows two competing titles.
   */
  ownTitle?: boolean;
  /**
   * Screens deliberately rendered without the rail (record, processing) have no
   * other way out, so their back button stays at every width.
   */
  standalone?: boolean;
  /** Must match the page's own container, or the title will not line up. */
  width?: ContentWidth;
}

/**
 * The page header, at both densities.
 *
 * What this replaces: a single mobile title bar used on nine screens at every
 * width — a 44px back button, a 16px `text-ink/60` label optically centred, and
 * a spacer. On a phone that is the right pattern. On a 1440px window with a
 * permanent rail it is wrong twice over: the back button offers to return from
 * a screen you navigated to from the rail that is still on screen, and the
 * page's own name is rendered smaller and fainter than the body text beneath
 * it, so the largest thing on a desktop page was whatever came after the title.
 *
 * Below `lg` nothing changes. From `lg` the back button goes, the title becomes
 * an actual page title aligned to the content column, and the freed right-hand
 * side becomes a slot for page actions and search.
 */
export function AppHeader({
  title,
  fallbackHref,
  actions,
  ownTitle = false,
  standalone = false,
  width = "default",
}: AppHeaderProps) {
  const { t } = useMuraI18n();
  const search = useArchiveSearch();

  // One trigger, rendered by the header rather than passed in by all nine
  // screens. Absent on the focus screens and before sign-in, where there is no
  // provider and nothing to search.
  const searchButton = search ? (
    <button
      type="button"
      onClick={search.open}
      aria-keyshortcuts="Control+K Meta+K"
      aria-label={t("searchOpen")}
      className="flex size-11 items-center justify-center rounded-full text-ink/70 transition-colors hover:bg-sand hover:text-ink focus-ring"
    >
      <Search aria-hidden className="size-5" strokeWidth={1.8} />
    </button>
  ) : null;

  const rightSlot =
    actions || searchButton ? (
      <>
        {actions}
        {searchButton}
      </>
    ) : null;

  return (
    <header className="pt-screen">
      {/* Mobile: back, centred title, actions. The three-column grid keeps the
          title optically centred no matter how wide the right slot grows, so a
          running timer can never crowd or clip it. */}
      <div
        className={`grid grid-cols-[minmax(44px,1fr)_auto_minmax(44px,1fr)] items-center gap-2 px-page pb-2 ${
          standalone ? "" : "lg:hidden"
        }`}
      >
        <BackButton fallbackHref={fallbackHref} />
        {title ? (
          <span className="truncate text-center text-body font-semibold text-ink/60">
            {title}
          </span>
        ) : (
          <span aria-hidden />
        )}
        <div className="flex justify-end">
          {rightSlot ?? <span aria-hidden className="size-11" />}
        </div>
      </div>

      {/* Desktop. A standalone screen keeps the bar above and skips this, so it
          does not end up with two headers. */}
      {!standalone && (title || rightSlot) && (
        <PageContainer width={width} className="hidden pb-1 lg:block">
          <div className="flex min-h-11 items-center justify-between gap-4">
            {title && !ownTitle ? (
              <h1 className="truncate text-title font-bold leading-tight tracking-[-0.02em] text-ink">
                {title}
              </h1>
            ) : (
              <span aria-hidden />
            )}
            {rightSlot && <div className="flex shrink-0 items-center gap-2">{rightSlot}</div>}
          </div>
        </PageContainer>
      )}
    </header>
  );
}
