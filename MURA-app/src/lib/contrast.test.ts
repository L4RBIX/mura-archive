/**
 * Text contrast, computed from the palette rather than trusted.
 *
 * `--color-muted` once measured 3.01:1 on paper while carrying almost every
 * date, byline and section label in the product — "premium" had quietly become
 * "hard to read" for an archive whose readers are often grandparents. The
 * numbers in the `globals.css` comments are load-bearing claims, so they are
 * checked here instead of being asserted in prose.
 *
 * WCAG 2.2 SC 1.4.3 (AA): 4.5:1 for normal text, 3:1 for large text.
 *
 * Colours are read out of `globals.css`, so editing a token without re-checking
 * its contrast fails the suite rather than shipping.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");

function token(name: string): string {
  const match = CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`token --color-${name} not found in globals.css`);
  return match[1];
}

/** Relative luminance, per WCAG 2.x. */
function luminance(hex: string): number {
  const channel = (value: number) => {
    const srgb = value / 255;
    return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  };
  const r = channel(parseInt(hex.slice(1, 3), 16));
  const g = channel(parseInt(hex.slice(3, 5), 16));
  const b = channel(parseInt(hex.slice(5, 7), 16));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** Ink at an alpha, composited over a surface — how `text-ink/70` renders. */
function inkAt(alpha: number, surface: string): string {
  const ink = token("ink");
  const mix = (i: number) => {
    const fg = parseInt(ink.slice(i, i + 2), 16);
    const bg = parseInt(surface.slice(i, i + 2), 16);
    return Math.round(fg * alpha + bg * (1 - alpha));
  };
  return `#${[1, 3, 5].map((i) => mix(i).toString(16).padStart(2, "0")).join("")}`;
}

const PAPER = () => token("paper");
const RAISED = () => token("raised");

describe("body and secondary text meet AA on both surfaces", () => {
  const surfaces: [string, () => string][] = [
    ["paper", PAPER],
    ["raised", RAISED],
  ];

  it.each(surfaces)("ink is comfortably readable on %s", (_name, surface) => {
    expect(contrast(token("ink"), surface())).toBeGreaterThanOrEqual(4.5);
  });

  it.each(surfaces)("muted meets AA for normal text on %s", (_name, surface) => {
    // This is the regression that matters: muted carries the metadata.
    expect(contrast(token("muted"), surface())).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps muted clearly secondary to ink", () => {
    // Passing AA by making everything black would satisfy the threshold and
    // destroy the hierarchy.
    expect(contrast(token("muted"), PAPER())).toBeLessThan(
      contrast(token("ink"), PAPER()),
    );
  });
});

describe("state colours are legible where they are used", () => {
  it("danger meets AA on paper and on its own surface", () => {
    expect(contrast(token("danger"), PAPER())).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("danger"), RAISED())).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("danger"), token("danger-surface"))).toBeGreaterThanOrEqual(4.5);
  });

  it("warning meets AA on paper and on its own surface", () => {
    expect(contrast(token("warning"), PAPER())).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("warning"), RAISED())).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("warning"), token("warning-surface"))).toBeGreaterThanOrEqual(4.5);
  });

  it("success meets AA on paper and raised", () => {
    expect(contrast(token("success"), PAPER())).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("success"), RAISED())).toBeGreaterThanOrEqual(4.5);
  });
});

describe("the ink alphas the product actually uses", () => {
  // `text-ink/70` and `text-ink/75` carry real body copy in several places.
  it.each([70, 75, 80])("ink/%i meets AA for normal text on paper", (alpha) => {
    expect(contrast(inkAt(alpha / 100, PAPER()), PAPER())).toBeGreaterThanOrEqual(4.5);
  });

  it("ink/55, used for inactive nav icons, clears the 3:1 non-text floor", () => {
    expect(contrast(inkAt(0.55, RAISED()), RAISED())).toBeGreaterThanOrEqual(3);
  });
});

describe("the numbers written in globals.css are the real ones", () => {
  it("muted is the value the comment claims, to one decimal", () => {
    expect(contrast(token("muted"), PAPER())).toBeCloseTo(5.11, 1);
    expect(contrast(token("muted"), RAISED())).toBeCloseTo(5.58, 1);
  });

  it("the state colours match their documented ratios", () => {
    expect(contrast(token("danger"), PAPER())).toBeCloseTo(7.04, 1);
    expect(contrast(token("warning"), PAPER())).toBeCloseTo(5.89, 1);
    expect(contrast(token("success"), PAPER())).toBeCloseTo(5.55, 1);
  });
});
