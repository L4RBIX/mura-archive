/**
 * The demo/real boundary, enforced statically.
 *
 * After the archive cutover the boundary moved rather than disappeared. Tree,
 * Person, Story and Home read the family archive; the only demonstration left
 * is Ask, which answers any question with the same scripted fixture and must
 * keep saying so.
 *
 * The rules below are what stops that from drifting back:
 *
 *   1. No screen that renders a real family's data may import a fixture.
 *   2. Ask, which is still a demonstration, must render the boundary.
 *   3. Nothing may address a person by name where an id belongs.
 *
 * Source-level assertions on purpose. The failure being guarded against is an
 * import added to the wrong screen, which no isolated render test would see.
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function read(relative: string): string {
  return readFileSync(join(SRC, relative), "utf8");
}

/** Imports that would pull invented family content into a screen. */
function importsFixtures(source: string): boolean {
  return (
    /from\s+"@\/data/.test(source) || /from\s+"@\/lib\/mascot\/demo-memory"/.test(source)
  );
}

/** Screens that render a real family's archive. */
const REAL_SURFACES = [
  "components/tree/tree-view.tsx",
  "components/tree/tree-canvas.tsx",
  "components/tree/person-card.tsx",
  "components/tree/person-sheet.tsx",
  "components/person/person-view.tsx",
  "components/story/story-view.tsx",
  "components/story/stories-view.tsx",
  "components/story/story-link.tsx",
  "components/story/local-story-view.tsx",
  "components/story/transcript-reader.tsx",
  "components/review/review-view.tsx",
  "components/home/home-view.tsx",
  "components/home/archive-doorways.tsx",
  "components/record/record-view.tsx",
  "components/processing/processing-view.tsx",
  "components/settings/settings-view.tsx",
];

describe("real surfaces never import fixtures", () => {
  it.each(REAL_SURFACES)("%s", (file) => {
    expect(importsFixtures(read(file))).toBe(false);
  });
});

describe("the demonstration that remains says so", () => {
  it("Ask renders the demo boundary", () => {
    const source = read("components/ask/ask-view.tsx");
    // It answers any question with the same fixture, which reads as grounded
    // family intelligence unless it is labelled.
    expect(importsFixtures(source)).toBe(true);
    expect(/<DemoNotice/.test(source)).toBe(true);
  });

  it("the scripted answer card carries its own marker", () => {
    // The card travels into other layouts, where a page banner would not.
    expect(/<DemoBadge/.test(read("components/ask/memory-answer-card.tsx"))).toBe(true);
  });
});

describe("the fixture family is gone", () => {
  it("no longer exists in the source tree", () => {
    // Nine invented relatives with parent ids and spouse links. Keeping them
    // around after the cutover is how a fallback quietly reappears.
    expect(existsSync(join(SRC, "data"))).toBe(false);
  });

  it("localisation no longer provides family data", () => {
    const source = read("lib/i18n.tsx");
    // The language switcher and the family data source were once the same
    // object, so a screen could reach an invented relative through what looked
    // like a translation hook.
    expect(importsFixtures(source)).toBe(false);
    // The deleted fixture accessors, matched as identifiers rather than as
    // substrings. `i18n.tsx` is now a three-language dictionary, and a bare
    // /narrator/ also forbids the English word in a translated sentence —
    // which says nothing about whether fixture data has crept back in.
    expect(source).not.toMatch(/\b(getPerson|storiesForPerson|narrator)\s*[(:=]/);
  });
});

describe("identity is an id, never a name", () => {
  it("the tree addresses people by canonical id", () => {
    const source = read("components/tree/person-card.tsx");
    expect(source).toMatch(/person\.person_id/);
  });

  it("the person profile is keyed by person id", () => {
    const source = read("components/person/person-view.tsx");
    expect(source).toMatch(/personId/);
    // The name-matching join this milestone removed.
    expect(source).not.toMatch(/toLocaleLowerCase|normalizedNames/);
  });

  it("stories attach to people by resolved id", () => {
    const source = read("components/person/person-view.tsx");
    expect(source).toMatch(/story\.person_ids\.includes\(personId\)/);
  });
});

describe("no mock playback survives on a real recording", () => {
  it("the mock player is gone", () => {
    // A waveform and a play button over audio that was never retrievable is a
    // claim that a recording exists.
    expect(existsSync(join(SRC, "hooks/use-mock-playback.ts"))).toBe(false);
    expect(existsSync(join(SRC, "components/story/audio-player.tsx"))).toBe(false);
  });

  it("story playback is offered only when Core says the audio is there", () => {
    const source = read("components/story/recording-player.tsx");
    expect(source).toMatch(/available/);
    expect(source).toMatch(/storyAudioUnavailable/);
  });
});
