/**
 * Canonical edges to the relations a family tree draws.
 *
 * Core stores a relationship once, with a direction: a `parent_child` edge has
 * a subject in the parent role and an object in the child role. A tree needs
 * to ask the opposite question just as often ("who are this person's
 * parents?"), and the way that goes wrong is a screen flipping an edge inline
 * and getting it backwards — quietly turning a mother into a daughter.
 *
 * So the conversion happens exactly once, here, and is tested. No component
 * reads `subject_role` directly.
 *
 * Only edges Core materialized are present. A relationship that did not clear
 * the evidence bar never became an edge, and this module has no way to invent
 * one: it can only read what it is given.
 */

import type { ArchivePerson, ArchiveRelationship } from "@/lib/mura/archive-api";

export interface FamilyRelations {
  parentsOf: (personId: string) => string[];
  childrenOf: (personId: string) => string[];
  siblingsOf: (personId: string) => string[];
  spouseOf: (personId: string) => string | undefined;
  personById: (personId: string) => ArchivePerson | undefined;
  /** Everyone in the archive, in display order. */
  people: ArchivePerson[];
}

const PARENT_CHILD = "parent_child";
const SPOUSE = "spouse";
const SIBLING = "sibling";

/** Roles Core uses for a sibling, including the ordered variants. */
const SIBLING_ROLES = new Set(["sibling", "older_sibling", "younger_sibling"]);

function push(map: Map<string, string[]>, key: string, value: string) {
  const existing = map.get(key);
  if (existing) {
    if (!existing.includes(value)) existing.push(value);
    return;
  }
  map.set(key, [value]);
}

export function buildFamilyRelations(
  people: ArchivePerson[],
  relationships: ArchiveRelationship[],
): FamilyRelations {
  const byId = new Map(people.map((person) => [person.person_id, person]));

  const parents = new Map<string, string[]>();
  const children = new Map<string, string[]>();
  const siblings = new Map<string, string[]>();
  const spouses = new Map<string, string>();

  for (const edge of relationships) {
    const { subject_person_id: subject, object_person_id: object } = edge;
    // An edge to somebody who is not a canonical person cannot be drawn.
    if (!byId.has(subject) || !byId.has(object)) continue;
    if (subject === object) continue;

    if (edge.relationship_type === PARENT_CHILD) {
      // The only place direction is interpreted. `subject_role` says which end
      // the subject occupies; everything downstream asks by relation, not by
      // position in the row.
      const subjectIsParent = edge.subject_role === "parent";
      const parent = subjectIsParent ? subject : object;
      const child = subjectIsParent ? object : subject;
      push(parents, child, parent);
      push(children, parent, child);
      continue;
    }

    if (edge.relationship_type === SPOUSE) {
      // Symmetric, and recorded once. Both directions are derived so either
      // person can be centred on the canvas.
      if (!spouses.has(subject)) spouses.set(subject, object);
      if (!spouses.has(object)) spouses.set(object, subject);
      continue;
    }

    if (edge.relationship_type === SIBLING) {
      if (!SIBLING_ROLES.has(edge.subject_role) || !SIBLING_ROLES.has(edge.object_role)) continue;
      push(siblings, subject, object);
      push(siblings, object, subject);
    }
  }

  const listFrom = (map: Map<string, string[]>) => (personId: string) => map.get(personId) ?? [];

  return {
    people,
    personById: (personId) => byId.get(personId),
    parentsOf: listFrom(parents),
    childrenOf: listFrom(children),
    spouseOf: (personId) => spouses.get(personId),
    siblingsOf: (personId) => {
      const explicit = siblings.get(personId) ?? [];
      // A shared parent makes two people siblings whether or not extraction
      // ever stated it, and this is derivation from recorded edges rather
      // than a guess: both parent links are themselves evidence-backed.
      const derived = new Set<string>(explicit);
      for (const parent of parents.get(personId) ?? []) {
        for (const child of children.get(parent) ?? []) {
          if (child !== personId) derived.add(child);
        }
      }
      return [...derived];
    },
  };
}

/**
 * Whether the archive has enough to draw anything at all.
 *
 * A single person with no relationships is a real archive state, not an empty
 * one: the tree shows them alone rather than claiming the family is empty.
 */
export function hasGraph(people: ArchivePerson[]): boolean {
  return people.length > 0;
}
