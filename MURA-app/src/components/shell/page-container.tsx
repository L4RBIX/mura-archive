/**
 * How wide a surface is allowed to be, stated by the surface itself.
 *
 * The old shell answered this once, globally, with 430px. The right answer is
 * per-screen: a memoir paragraph wants a short measure at any window size,
 * settings want a form column, and a family tree wants everything it can get.
 * Removing the cap without replacing it would have traded a phone-sized app
 * for 1440px lines of Russian prose, which is worse.
 *
 * `reading` is deliberately in `ch`: the constraint is characters per line,
 * not pixels, so it holds when the type scale changes.
 */

import type { ReactNode } from "react";

export type ContentWidth = "reading" | "default" | "wide" | "full";

/**
 * Exported so a screen that lays out its own article element still reads the
 * measure from here rather than restating it.
 */
export const READING_WIDTH = "max-w-[70ch]";

const WIDTH: Record<ContentWidth, string> = {
  /*
   * The long-reading measure.
   *
   * `ch` resolves against *this* element's font, which is the 16px body — but
   * the prose inside is 18px, so `62ch` was buying a column that measured only
   * ~54 Cyrillic characters per line once the padding came off. Short of the
   * 60-70 that long prose actually wants, and Russian and Kazakh words are
   * longer than the English these rules are usually quoted for.
   *
   * 70ch here measures ~63 characters of real story text at 18px. Checked
   * against «Мамин хлеб по утрам» rather than derived on paper.
   */
  reading: READING_WIDTH,
  // Cards, forms and lists. Wide enough for two columns, narrow enough to scan.
  default: "max-w-[720px]",
  // Dense surfaces that benefit from room but still need a margin.
  wide: "max-w-[1100px]",
  // Canvases that own the viewport.
  full: "max-w-none",
};

export function PageContainer({
  width = "default",
  className,
  children,
}: {
  width?: ContentWidth;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`mx-auto w-full px-5 sm:px-6 lg:px-8 ${WIDTH[width]} ${className ?? ""}`}>
      {children}
    </div>
  );
}
