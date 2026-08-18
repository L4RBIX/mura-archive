import { describe, expect, it } from "vitest";
import type { ArchivePerson, ArchiveStorySummary } from "@/lib/mura/archive-api";
import { searchArchive, type SearchBundle } from "@/lib/mura/archive-search";

const person = (
  id: string,
  name: string,
  aliases: string[] = [],
): ArchivePerson => ({
  person_id: id,
  display_name: name,
  aliases,
  category: "family_member",
  relation_to_speaker: null,
  story_count: 1,
  recording_count: 1,
});

const story = (
  id: string,
  title: string,
  excerpt: string,
  personIds: string[],
  recordedAt: string,
): ArchiveStorySummary => ({
  story_id: id,
  title,
  excerpt,
  recording_id: `rec_${id}`,
  speaker_name: "Айсұлу",
  recorded_at: recordedAt,
  person_ids: personIds,
});

// Two different people who share a name — the case a name-based join breaks on.
const MARAT_ONE = person("person_marat_1", "Марат");
const MARAT_TWO = person("person_marat_2", "Марат");
const AISULU = person("person_aisulu", "Айсұлу", ["Айсулу"]);

const BREAD = story(
  "story_bread",
  "Мамин хлеб по утрам",
  "Мама всегда говорила, что дом начинается с запаха хлеба.",
  ["person_aisulu"],
  "2026-08-18T10:00:00+05:00",
);
const BICYCLE = story(
  "story_bicycle",
  "Синий велосипед Марата",
  "Марат чинил во дворе синий велосипед.",
  ["person_marat_1"],
  "2025-03-02T10:00:00+05:00",
);

const bundle: SearchBundle = {
  people: [MARAT_ONE, MARAT_TWO, AISULU],
  stories: [BREAD, BICYCLE],
  totalStories: 2,
};

const ids = (results: ReturnType<typeof searchArchive>) => results.map((r) => r.id);

describe("searchArchive", () => {
  it("finds a person by the name someone would type", () => {
    const results = searchArchive(bundle, "айсұлу", {});
    expect(results.some((r) => r.kind === "person" && r.id === "person_aisulu")).toBe(true);
  });

  it("finds a person by an alias, not only the display name", () => {
    const results = searchArchive(bundle, "Айсулу", {});
    expect(results.some((r) => r.kind === "person" && r.id === "person_aisulu")).toBe(true);
  });

  it("returns two distinct people who share a name, never one merged result", () => {
    // The whole reason identity is an id: «Марат» is two people here.
    const people = searchArchive(bundle, "Марат", {}).filter((r) => r.kind === "person");
    expect(people.map((r) => r.id).sort()).toEqual(["person_marat_1", "person_marat_2"]);
  });

  it("never attaches a story to a person by matching a name", () => {
    // «Марат» appears in this story's text, and the story lists person_marat_1
    // only. Filtering by the *other* Марат must return nothing, even though his
    // name occurs in the prose.
    const results = searchArchive(bundle, "", { personId: "person_marat_2" });
    expect(ids(results)).toEqual([]);
  });

  it("filters stories by canonical person id", () => {
    const results = searchArchive(bundle, "", { personId: "person_marat_1" });
    expect(ids(results)).toEqual(["story_bicycle"]);
  });

  it("filters stories by the year they were recorded", () => {
    expect(ids(searchArchive(bundle, "", { year: "2026" }))).toEqual(["story_bread"]);
    expect(ids(searchArchive(bundle, "", { year: "2025" }))).toEqual(["story_bicycle"]);
  });

  it("combines a person filter with a year filter", () => {
    expect(ids(searchArchive(bundle, "", { personId: "person_marat_1", year: "2026" })))
      .toEqual([]);
  });

  it("matches story text case-insensitively and treats ё as е", () => {
    expect(ids(searchArchive(bundle, "ХЛЕБА", {}))).toContain("story_bread");
    // «всё»/«все» must not decide whether a memory is findable.
    const yo: SearchBundle = {
      ...bundle,
      stories: [story("s_yo", "Всё о доме", "Всё было просто.", [], "2026-01-01T00:00:00+05:00")],
    };
    expect(ids(searchArchive(yo, "все", {}))).toEqual(["s_yo"]);
  });

  it("returns no people for an empty query, only the (unfiltered) stories", () => {
    const results = searchArchive(bundle, "", {});
    expect(results.every((r) => r.kind === "story")).toBe(true);
    expect(ids(results)).toEqual(["story_bread", "story_bicycle"]);
  });

  it("returns nothing when the query matches neither a person nor a memory", () => {
    expect(searchArchive(bundle, "трактор", {})).toEqual([]);
  });
});
