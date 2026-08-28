/**
 * The layout system, enforced statically.
 *
 * Before step 1 the design system stopped at colour, type and radius. There was
 * no shared answer to "how wide is a page", so three screens invented three
 * answers and nothing failed. These tests exist because that is exactly the
 * kind of drift no render test catches: nothing breaks, the product simply
 * stops being one product.
 *
 * Source-level assertions on purpose — the failure being guarded against is a
 * class name added to the wrong file.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full);
    return full.endsWith(".tsx") || full.endsWith(".ts") ? [full] : [];
  });
}

const FILES = walk(SRC)
  .filter((file) => !file.endsWith(".test.ts") && !file.endsWith(".test.tsx"))
  .map((file) => ({ path: relative(SRC, file).replace(/\\/g, "/"), source: readFileSync(file, "utf8") }));

/**
 * Width overrides that are deliberately not container widths.
 *
 * Each entry is a *justified* exception, not a backlog. A `ch` value caps a line
 * length inside an already-bounded parent, which is a measure and not a page
 * width; the rest size a control or a non-product surface. Anything new has to
 * be argued for here, in writing, rather than added quietly.
 */
const ALLOWED_WIDTH_OVERRIDES: Record<string, string> = {
  "components/shell/page-container.tsx": "declares the widths",
  "components/archive/archive-state.tsx": "ch measure inside a bounded notice",
  "components/auth/auth-frame.tsx": "ch measure on a pre-product tagline",
  "components/auth/dev-auth-panel.tsx": "ch measure on the sign-in lead, inside the form column",
  "components/record/record-view.tsx": "ch measure on the recorder hint, inside the focus column",
  "components/family/auth-strip.tsx": "ch measure on a hint",
  "components/home/first-run.tsx": "ch measures on the first-run copy, inside a bounded panel",
  "components/home/home-view.tsx": "ch measure on the masthead title, inside the page container",
  "components/home/record-hero.tsx": "ch measures on the hero question and hint, inside a filled block",
  "components/story/story-link.tsx": "ch measure on a memory excerpt, inside an already-bounded list",
  "components/onboarding/onboarding-view.tsx": "pre-product hero, outside the app container system",
  "components/onboarding/role-step.tsx": "ch measure on the role question, inside a bounded step",
  "components/processing/processing-view.tsx": "width of a status pill, not of content",
  "components/review/review-view.tsx": "ch measures on a list and an empty state",
  "components/settings/settings-view.tsx": "width of the segmented language control, plus ch measures on hints",
  "components/story/local-story-view.tsx": "ch measure on a not-found line",
  "components/story/stories-view.tsx": "ch measure on an empty state",
  "components/tree/person-sheet.tsx": "width of the mobile bottom sheet",
  "components/tree/tree-view.tsx": "ch measure on an empty state",
};

/**
 * Source with comments removed.
 *
 * These files explain *why* a rule exists, and those explanations quote the
 * very class names the rules forbid — `app/layout.tsx` records that the global
 * `max-w-[430px]` is gone. Scanning raw text would make the codebase unable to
 * document its own history.
 */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/** `max-w-[...]` occurrences that are real class names. */
function widthOverrides(source: string): string[] {
  return code(source).match(/max-w-\[[^\]]+\]/g) ?? [];
}

describe("content width is decided in one place", () => {
  it("has no width override outside the container, except those argued for", () => {
    const offenders = FILES.filter(
      (file) =>
        widthOverrides(file.source).length > 0 &&
        !(file.path in ALLOWED_WIDTH_OVERRIDES),
    ).map((file) => `${file.path}: ${widthOverrides(file.source).join(", ")}`);

    expect(offenders).toEqual([]);
  });

  it("keeps every exception justified in writing", () => {
    for (const reason of Object.values(ALLOWED_WIDTH_OVERRIDES)) {
      expect(reason.length).toBeGreaterThan(10);
    }
  });

  it("exposes the widths as tokens rather than pixel literals", () => {
    const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
    for (const token of [
      "--container-reading",
      "--container-form",
      "--container-default",
      "--container-focus",
      "--container-wide",
      "--container-measure",
    ]) {
      expect(css).toContain(token);
    }
  });
});

describe("the mobile-only header is gone", () => {
  it("has no ScreenHeader component left to import", () => {
    const survivors = FILES.filter((file) => file.path.includes("screen-header"));
    expect(survivors).toEqual([]);
  });

  it("has no reference to ScreenHeader anywhere", () => {
    const referrers = FILES.filter((file) => /\bScreenHeader\b/.test(code(file.source))).map(
      (file) => file.path,
    );
    expect(referrers).toEqual([]);
  });
});

describe("every product screen goes through the container", () => {
  // Tree and record own the whole viewport by design: a canvas and a focus
  // screen. Both still use `px-page`, so their gutter is the shared one.
  const OWNS_ITS_VIEWPORT = ["components/tree/tree-view.tsx", "components/record/record-view.tsx"];

  const SCREENS = [
    "components/home/home-view.tsx",
    "components/story/stories-view.tsx",
    "components/story/story-view.tsx",
    "components/story/local-story-view.tsx",
    "components/person/person-view.tsx",
    "components/review/review-view.tsx",
    "components/settings/settings-view.tsx",
    "components/ask/ask-view.tsx",
  ];

  it.each(SCREENS)("%s uses PageContainer or the reading measure", (path) => {
    const file = FILES.find((entry) => entry.path === path);
    expect(file, `${path} not found`).toBeDefined();
    expect(
      /PageContainer|READING_WIDTH/.test(file!.source),
      `${path} lays out its own column`,
    ).toBe(true);
  });

  it.each(OWNS_ITS_VIEWPORT)("%s still uses the shared gutter", (path) => {
    const file = FILES.find((entry) => entry.path === path);
    expect(file!.source).toMatch(/px-page/);
  });
});

describe("focus is a shared utility, not a copied string", () => {
  it("has no hand-written focus ring left", () => {
    const offenders = FILES.filter((file) =>
      /focus-visible:outline-\d/.test(code(file.source)),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });

  it("defines the utility once", () => {
    const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
    expect(css).toContain("@utility focus-ring");
  });
});

describe("state colours come from the palette", () => {
  it("uses no raw Tailwind status colour", () => {
    // `text-red-700` was the only saturated colour in an earth-toned product,
    // and the only way the UI could say "this failed".
    const offenders = FILES.filter((file) =>
      /\b(text|bg|border)-(red|green|amber|yellow|orange)-\d{3}\b/.test(code(file.source)),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });
});

describe("the desktop breakpoints are real", () => {
  const all = FILES.map((file) => code(file.source)).join("\n");

  it("uses xl and 2xl, not just lg", () => {
    // Between 1024 and 2560 the layout was identical before step 1.
    expect((all.match(/\bxl:/g) ?? []).length).toBeGreaterThan(0);
    expect((all.match(/\b2xl:/g) ?? []).length).toBeGreaterThan(0);
  });
});
