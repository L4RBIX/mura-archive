/**
 * Matching rules for archive search, separated from the dialog so they can be
 * tested without a DOM — and so the one rule that matters is pinned:
 *
 * a person is *found* by name, because a name is what someone types, but a
 * person is *returned* as a canonical `person_id`. Stories are matched on their
 * own text and never joined to a person by comparing strings. Two relatives
 * share a name, one relative has several across Russian and Kazakh spelling,
 * and a name-based join silently merges people who are not the same person.
 */

import type { ArchivePerson, ArchiveStorySummary } from "@/lib/mura/archive-api";

export interface SearchBundle {
  people: ArchivePerson[];
  stories: ArchiveStorySummary[];
  /** How many memories the archive holds, so the reach can be stated exactly. */
  totalStories: number;
}

export type SearchResult =
  | { kind: "person"; id: string; person: ArchivePerson }
  | { kind: "story"; id: string; story: ArchiveStorySummary };

/** Case- and diacritic-insensitive contains, for Russian and Kazakh alike. */
function normalize(value: string): string {
  return value.toLocaleLowerCase("ru").replace(/ё/g, "е").trim();
}

export function searchArchive(
  bundle: SearchBundle,
  rawQuery: string,
  filters: { personId?: string | null; year?: string | null },
): SearchResult[] {
  const query = normalize(rawQuery);
  const results: SearchResult[] = [];

  const matchesFilters = (story: ArchiveStorySummary) => {
    if (filters.personId && !story.person_ids.includes(filters.personId)) return false;
    if (filters.year && !story.recorded_at.startsWith(filters.year)) return false;
    return true;
  };

  if (query.length > 0) {
    for (const person of bundle.people) {
      const haystack = [person.display_name, ...person.aliases].map(normalize);
      if (haystack.some((value) => value.includes(query))) {
        results.push({ kind: "person", id: person.person_id, person });
      }
    }
  }

  for (const story of bundle.stories) {
    if (!matchesFilters(story)) continue;
    if (query.length > 0) {
      const haystack = normalize(`${story.title ?? ""} ${story.excerpt ?? ""}`);
      if (!haystack.includes(query)) continue;
    }
    results.push({ kind: "story", id: story.story_id, story });
  }

  return results;
}

