/**
 * Direction is the whole point of these tests.
 *
 * Core records a relationship once, with a subject and an object in named
 * roles. Every inline flip of that edge is a chance to turn a mother into a
 * daughter, so the conversion lives in one place and is pinned here.
 */

import { describe, expect, it } from "vitest";
import { buildFamilyRelations } from "./family-graph";
import type { ArchivePerson, ArchiveRelationship } from "./archive-api";

const person = (id: string, name: string): ArchivePerson => ({
  person_id: id,
  display_name: name,
  aliases: [],
  category: "family_member",
  relation_to_speaker: null,
  story_count: 0,
  recording_count: 0,
});

const edge = (
  id: string,
  type: string,
  subject: string,
  subjectRole: string,
  object: string,
  objectRole: string,
): ArchiveRelationship => ({
  edge_id: id,
  relationship_type: type,
  subject_person_id: subject,
  subject_role: subjectRole,
  object_person_id: object,
  object_role: objectRole,
  source_claim_ids: ["claim_1"],
});

const MOTHER = person("person_m", "Бибігүл");
const CHILD = person("person_c", "Айсұлу");
const SIBLING = person("person_s", "Болат");
const SPOUSE = person("person_p", "Марат");

describe("parent and child direction", () => {
  it("reads a parent-subject edge in the stated direction", () => {
    const relations = buildFamilyRelations(
      [MOTHER, CHILD],
      [edge("e1", "parent_child", "person_m", "parent", "person_c", "child")],
    );

    expect(relations.parentsOf("person_c")).toEqual(["person_m"]);
    expect(relations.childrenOf("person_m")).toEqual(["person_c"]);
    // The reverse must be empty, or the tree draws the family upside down.
    expect(relations.parentsOf("person_m")).toEqual([]);
    expect(relations.childrenOf("person_c")).toEqual([]);
  });

  it("reads a child-subject edge the same way", () => {
    // Same relationship, recorded from the other end. It must produce an
    // identical graph.
    const relations = buildFamilyRelations(
      [MOTHER, CHILD],
      [edge("e1", "parent_child", "person_c", "child", "person_m", "parent")],
    );

    expect(relations.parentsOf("person_c")).toEqual(["person_m"]);
    expect(relations.childrenOf("person_m")).toEqual(["person_c"]);
  });
});

describe("spouse", () => {
  it("is symmetric from one recorded edge", () => {
    const relations = buildFamilyRelations(
      [CHILD, SPOUSE],
      [edge("e1", "spouse", "person_c", "spouse", "person_p", "spouse")],
    );

    expect(relations.spouseOf("person_c")).toBe("person_p");
    expect(relations.spouseOf("person_p")).toBe("person_c");
  });
});

describe("siblings", () => {
  it("is symmetric and accepts ordered roles", () => {
    const relations = buildFamilyRelations(
      [CHILD, SIBLING],
      [edge("e1", "sibling", "person_c", "older_sibling", "person_s", "younger_sibling")],
    );

    expect(relations.siblingsOf("person_c")).toContain("person_s");
    expect(relations.siblingsOf("person_s")).toContain("person_c");
  });

  it("derives siblings from a shared parent", () => {
    // Both parent links are evidence-backed edges, so this is derivation from
    // what was recorded rather than a guess about the family.
    const relations = buildFamilyRelations(
      [MOTHER, CHILD, SIBLING],
      [
        edge("e1", "parent_child", "person_m", "parent", "person_c", "child"),
        edge("e2", "parent_child", "person_m", "parent", "person_s", "child"),
      ],
    );

    expect(relations.siblingsOf("person_c")).toEqual(["person_s"]);
    expect(relations.siblingsOf("person_s")).toEqual(["person_c"]);
  });

  it("never makes someone their own sibling", () => {
    const relations = buildFamilyRelations(
      [MOTHER, CHILD],
      [edge("e1", "parent_child", "person_m", "parent", "person_c", "child")],
    );

    expect(relations.siblingsOf("person_c")).not.toContain("person_c");
  });
});

describe("edges the tree must refuse", () => {
  it("drops an edge to somebody who is not a canonical person", () => {
    // The endpoint filters these already; the client does not assume it.
    const relations = buildFamilyRelations(
      [CHILD],
      [edge("e1", "parent_child", "person_ghost", "parent", "person_c", "child")],
    );

    expect(relations.parentsOf("person_c")).toEqual([]);
  });

  it("drops a self-edge", () => {
    const relations = buildFamilyRelations(
      [CHILD],
      [edge("e1", "spouse", "person_c", "spouse", "person_c", "spouse")],
    );

    expect(relations.spouseOf("person_c")).toBeUndefined();
  });

  it("ignores a relationship type it does not understand", () => {
    // A new vocabulary term must not be guessed into a lineage line.
    const relations = buildFamilyRelations(
      [MOTHER, CHILD],
      [edge("e1", "godparent", "person_m", "parent", "person_c", "child")],
    );

    expect(relations.parentsOf("person_c")).toEqual([]);
    expect(relations.childrenOf("person_m")).toEqual([]);
  });

  it("invents nothing when there are no relationships at all", () => {
    const relations = buildFamilyRelations([MOTHER, CHILD], []);

    expect(relations.parentsOf("person_c")).toEqual([]);
    expect(relations.spouseOf("person_c")).toBeUndefined();
    expect(relations.siblingsOf("person_c")).toEqual([]);
    // A person with no edges is still a real person in the archive.
    expect(relations.people).toHaveLength(2);
  });
});

describe("identity", () => {
  it("addresses people by canonical id, never by name", () => {
    const twin = person("person_other", "Айсұлу");
    const relations = buildFamilyRelations([CHILD, twin], []);

    // Two relatives share a display name and remain two different people.
    expect(relations.personById("person_c")?.person_id).toBe("person_c");
    expect(relations.personById("person_other")?.person_id).toBe("person_other");
    expect(relations.personById("Айсұлу")).toBeUndefined();
  });
});
