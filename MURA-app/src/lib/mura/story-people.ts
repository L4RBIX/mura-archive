/**
 * Which people a memory card names, and how many it does not.
 *
 * Pure and separate from the card so it can be tested without a DOM. The rules
 * it encodes are the ones that matter for truthfulness, not for layout:
 *
 * - resolution is by canonical `person_id` only. There is deliberately no path
 *   here that takes a name. Two relatives share a name, one relative has
 *   several across Russian and Kazakh spelling, and a string comparison
 *   silently merges people who are not the same person;
 * - an id the archive cannot resolve to a person is dropped, not rendered as a
 *   placeholder. A mention that has not been resolved to anyone is not a
 *   person, and a grey "unknown" chip would invent one;
 * - order follows `person_ids` as Core returned it. Sorting by name here would
 *   impose an order the archive did not assert.
 */

import type { ArchivePerson } from "@/lib/mura/archive-api";

export interface StoryPeople {
  /** Named on the card, in the order Core returned them. */
  shown: ArchivePerson[];
  /** How many resolved people did not fit; 0 when they all did. */
  hidden: number;
}

export function resolveStoryPeople(
  personIds: readonly string[],
  peopleById: ReadonlyMap<string, ArchivePerson> | undefined,
  visible: number,
): StoryPeople {
  if (!peopleById) return { shown: [], hidden: 0 };

  const resolved: ArchivePerson[] = [];
  for (const id of personIds) {
    const person = peopleById.get(id);
    if (person) resolved.push(person);
  }

  return {
    shown: resolved.slice(0, visible),
    hidden: Math.max(0, resolved.length - visible),
  };
}
