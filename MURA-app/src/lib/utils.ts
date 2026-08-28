import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * The project's custom type scale, named for tailwind-merge.
 *
 * ## The bug this fixes
 *
 * Every large button in the product rendered its label in ink on an ink pill —
 * black text on a black background, invisible. The primary call to action on
 * the landing page was an empty black lozenge.
 *
 * `cn()` merges classes with tailwind-merge, which resolves conflicts by
 * grouping class names by prefix. Out of the box it knows Tailwind's own
 * `text-*` scale, so it can tell `text-lg` (a size) from `text-white` (a
 * colour) and let one of each survive. It knows nothing about this project's
 * scale, so `text-item` looked like a colour — and in
 *
 *     cn("bg-ink text-raised", "h-14 px-8 text-item")
 *
 * the later "colour" won and `text-raised` was deleted from the output. Nothing
 * failed: TypeScript is happy, the tests pass, the class list is valid. The
 * text was simply the same colour as what it sat on.
 *
 * Declaring the scale is what makes the two groups distinguishable again, and
 * it fixes every `text-<size>` + `text-<colour>` pair in the app at once rather
 * than one component at a time.
 *
 * Keep this in step with the `--text-*` tokens in `globals.css`. A size added
 * there and not here silently starts eating colours again.
 */
const FONT_SIZES = [
  "caption",
  "meta",
  "body",
  "item",
  "reading",
  "section",
  "title",
  "display",
] as const;

/**
 * The radius scale, for the same reason.
 *
 * `rounded-panel` and `rounded-full` are both radii and genuinely conflict, so
 * this group only needs the custom names to be recognised at all — but without
 * them tailwind-merge cannot tell that `rounded-control` and `rounded-surface`
 * are the same kind of thing, and would let both survive on one element.
 */
const RADII = ["control", "surface", "panel"] as const;

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": FONT_SIZES.map((size) => `text-${size}`),
      rounded: RADII.map((radius) => `rounded-${radius}`),
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
