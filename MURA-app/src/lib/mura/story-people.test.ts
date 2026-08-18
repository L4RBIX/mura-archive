import { describe, expect, it } from "vitest";
import type { ArchivePerson } from "@/lib/mura/archive-api";
import { resolveStoryPeople } from "@/lib/mura/story-people";

const person = (id: string, name: string): ArchivePerson => ({
  person_id: id,
  display_name: name,
  aliases: [],
  category: "family_member",
  relation_to_speaker: null,
  story_count: 1,
  recording_count: 1,
});

const AISULU = person("person_aaa", "Айсұлу");
const MARAT = person("person_bbb", "Марат");
const BOLAT = person("person_ccc", "Болат");
const BIBIGUL = person("person_ddd", "Бибігүл Шаймарданова");

const archive = new Map([AISULU, MARAT, BOLAT, BIBIGUL].map((p) => [p.person_id, p]));

describe("resolveStoryPeople", () => {
  it("names nobody when the story mentions nobody", () => {
    expect(resolveStoryPeople([], archive, 3)).toEqual({ shown: [], hidden: 0 });
  });

  it("names nobody when the caller has not loaded the family's people", () => {
    // A card without the people map shows no chips rather than guessing.
    expect(resolveStoryPeople([AISULU.person_id], undefined, 3)).toEqual({
      shown: [],
      hidden: 0,
    });
  });

  it("drops an id the archive cannot resolve rather than inventing a chip", () => {
    const result = resolveStoryPeople(
      [AISULU.person_id, "person_not_in_this_archive", MARAT.person_id],
      archive,
      3,
    );
    expect(result.shown).toEqual([AISULU, MARAT]);
    expect(result.hidden).toBe(0);
  });

  it("returns nobody when none of the ids resolve", () => {
    expect(resolveStoryPeople(["person_x", "person_y"], archive, 3)).toEqual({
      shown: [],
      hidden: 0,
    });
  });

  it("counts the overflow instead of truncating the list silently", () => {
    const result = resolveStoryPeople(
      [AISULU, MARAT, BOLAT, BIBIGUL].map((p) => p.person_id),
      archive,
      3,
    );
    expect(result.shown).toEqual([AISULU, MARAT, BOLAT]);
    expect(result.hidden).toBe(1);
  });

  it("keeps Core's order rather than sorting by name", () => {
    // Sorting would assert an ordering the archive never expressed.
    const result = resolveStoryPeople(
      [BIBIGUL.person_id, AISULU.person_id, MARAT.person_id],
      archive,
      3,
    );
    expect(result.shown.map((p) => p.display_name)).toEqual([
      "Бибігүл Шаймарданова",
      "Айсұлу",
      "Марат",
    ]);
  });

  it("never resolves a person by display name", () => {
    // The map is keyed by canonical id; a name must not be a way in.
    const byName = new Map([["Айсұлу", AISULU]]);
    expect(resolveStoryPeople(["Айсұлу"], archive, 3).shown).toEqual([]);
    // And when a name *is* used as a key, that is the caller's bug, not a
    // supported path — pinned so nobody "fixes" the component to accept names.
    expect(resolveStoryPeople([AISULU.person_id], byName, 3).shown).toEqual([]);
  });

  it("hides nothing when everyone fits exactly", () => {
    const result = resolveStoryPeople(
      [AISULU.person_id, MARAT.person_id, BOLAT.person_id],
      archive,
      3,
    );
    expect(result.hidden).toBe(0);
  });
});
