import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function walk(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return walk(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

const FILES = walk(SRC).map((path) => ({
  path: relative(SRC, path).replace(/\\/g, "/"),
  source: readFileSync(path, "utf8"),
}));

const HOSTS = FILES.filter(
  (file) =>
    file.path !== "components/brand/voice-to-family.tsx" && /<VoiceToFamily\b/.test(file.source),
);

/**
 * Whoever draws the signature must also clip it.
 *
 * The motif is placed to bleed past the edge of whatever holds it — that
 * overflow is the composition. Which makes the host responsible for clipping,
 * and a host that forgets simply widens the document: on a 320px phone this
 * pushed the page 60px past the viewport and the whole app scrolled sideways,
 * with nothing failing and no error anywhere.
 */
describe("every surface that draws the signature clips it", () => {
  it("finds the hosts, so this suite cannot pass by matching nothing", () => {
    expect(HOSTS.length).toBeGreaterThan(0);
  });

  it.each(HOSTS.map((file) => file.path))("%s clips its overflow", (path) => {
    const host = HOSTS.find((file) => file.path === path) as (typeof HOSTS)[number];
    expect(host.source).toMatch(/overflow-hidden/);
  });
});

/**
 * The circles are gone and must stay gone.
 *
 * The previous signature was four stacked translucent circles lifted from the
 * mood reference. It meant nothing a viewer could name, and decoration derived
 * from another product's decoration is what "templated" looks like.
 */
describe("the stacked-circle motif does not come back", () => {
  it("has no Generations component left in the tree", () => {
    expect(FILES.filter((file) => file.path.includes("brand/generations"))).toEqual([]);
  });

  it("is imported by nobody", () => {
    for (const file of FILES) {
      expect(file.source, file.path).not.toMatch(/from "@\/components\/brand\/generations"/);
    }
  });
});
