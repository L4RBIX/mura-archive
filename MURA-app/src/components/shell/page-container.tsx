/**
 * How wide a surface is allowed to be, stated by the surface itself.
 *
 * The old shell answered this once, globally, with 430px. The right answer is
 * per-screen: a memoir paragraph wants a short measure at any window size,
 * settings want a form column, and a family tree wants everything it can get.
 * Removing the cap without replacing it would have traded a phone-sized app
 * for 1440px lines of Russian prose, which is worse.
 *
 * Replacing it per component was the second mistake. Settings declared its own
 * `max-w-[560px]`, home used `wide`, lists used `default` — three widths, no
 * way to tell which was deliberate, and nothing stopping a fourth. The widths
 * now live in `@theme` as `--container-*`; this file only names *which* one a
 * surface gets, and every page is expected to come through here.
 *
 * `reading` and `measure` are deliberately in `ch`: the constraint is
 * characters per line, not pixels, so they survive a change to the type scale.
 */

import type { ReactNode } from "react";

export type ContentWidth =
  | "reading"
  | "form"
  | "default"
  | "focus"
  | "wide"
  | "full";

/**
 * Exported so a screen that lays out its own `article` element still reads the
 * measure from here rather than restating it.
 *
 * 70ch measures ~63 characters of real story text at 18px — checked against
 * «Мамин хлеб по утрам», not derived on paper. `ch` resolves against the 16px
 * container font while the prose is 18px, which is why the previous 62ch bought
 * only ~54 characters and read as a narrow column.
 */
export const READING_WIDTH = "max-w-reading";

const WIDTH: Record<ContentWidth, string> = {
  reading: READING_WIDTH,
  // Settings, auth and anything that is a single column of controls.
  form: "max-w-form",
  // Cards and lists. Wide enough for two columns, narrow enough to scan.
  default: "max-w-default",
  // One task and nothing beside it: record, processing.
  focus: "max-w-focus",
  // Dense surfaces that benefit from room but still need a margin. This is the
  // one width that grows past `xl`: prose must not, but a grid of cards and a
  // side panel genuinely have more to show when the window is 1536 or wider.
  wide: "max-w-wide 2xl:max-w-wide-2xl",
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
    <div className={`mx-auto w-full px-page ${WIDTH[width]} ${className ?? ""}`}>
      {children}
    </div>
  );
}
