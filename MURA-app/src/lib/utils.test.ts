import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

/**
 * `cn` must never silently delete a colour.
 *
 * This is a regression test for invisible button text. tailwind-merge resolves
 * conflicts by prefix, and it only knows Tailwind's own scales — so this
 * project's custom `text-item` looked like a colour, collided with
 * `text-raised`, and won. Every large button in the product rendered ink on
 * ink: a black label on a black pill, with a perfectly valid class list and a
 * green test suite.
 *
 * The whole failure lives in the string that reaches the DOM, which is why
 * these assertions read the merged output rather than testing a component.
 */

describe("a size and a colour can coexist", () => {
  it("keeps the text colour when a custom size follows it", () => {
    // The exact composition the Button produces: variant first, size second.
    const merged = cn("bg-ink text-raised", "h-14 px-8 text-item");

    expect(merged).toContain("text-raised");
    expect(merged).toContain("text-item");
  });

  it.each([
    ["text-caption"],
    ["text-meta"],
    ["text-body"],
    ["text-item"],
    ["text-reading"],
    ["text-section"],
    ["text-title"],
    ["text-display"],
  ])("keeps a colour beside %s", (size) => {
    // Every step of the scale, because one missing name reintroduces the bug
    // for exactly the components that use that step.
    expect(cn("text-muted", size)).toContain("text-muted");
    expect(cn("text-muted", size)).toContain(size);
  });

  it("keeps the colour regardless of which order they arrive in", () => {
    expect(cn("text-body", "text-danger")).toContain("text-body");
    expect(cn("text-body", "text-danger")).toContain("text-danger");
  });
});

describe("genuine conflicts are still resolved", () => {
  it("keeps only the last of two sizes", () => {
    const merged = cn("text-body", "text-title");
    expect(merged).toContain("text-title");
    expect(merged).not.toContain("text-body");
  });

  it("keeps only the last of two colours", () => {
    const merged = cn("text-muted", "text-ink");
    expect(merged).toContain("text-ink");
    expect(merged).not.toContain("text-muted");
  });

  it("keeps only the last of two custom radii", () => {
    const merged = cn("rounded-control", "rounded-panel");
    expect(merged).toContain("rounded-panel");
    expect(merged).not.toContain("rounded-control");
  });

  it("lets a custom radius override a Tailwind one, and the reverse", () => {
    expect(cn("rounded-full", "rounded-surface")).toBe("rounded-surface");
    expect(cn("rounded-surface", "rounded-full")).toBe("rounded-full");
  });

  it("still merges ordinary Tailwind conflicts", () => {
    expect(cn("px-4", "px-8")).toBe("px-8");
  });
});

describe("the scale here matches the scale in globals.css", () => {
  it("declares every --text-* token the stylesheet defines", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

    const declared = [...css.matchAll(/^\s*--text-([a-z0-9-]+):/gm)].map((m) => m[1]);
    expect(declared.length).toBeGreaterThan(5);

    // A size added to the stylesheet but not to `cn` starts eating colours
    // again, silently, only on the components that use it.
    for (const size of declared) {
      const merged = cn("text-muted", `text-${size}`);
      expect(merged, `text-${size} is not declared as a font size in cn()`).toContain(
        "text-muted",
      );
    }
  });
});
