import { describe, expect, it } from "vitest";
import { buildFamilyRelations } from "@/lib/mura/family-graph";
import { generationCount } from "@/lib/mura/generations";
import type { ArchivePerson, ArchiveRelationship } from "@/lib/mura/archive-api";

const person = (id: string): ArchivePerson => ({
  person_id: id,
  display_name: id,
  aliases: [],
  category: "family_member",
  relation_to_speaker: null,
  story_count: 0,
  recording_count: 0,
});

let edgeId = 0;
const parentOf = (parent: string, child: string): ArchiveRelationship => ({
  edge_id: `edge_${(edgeId += 1)}`,
  relationship_type: "parent_child",
  subject_person_id: parent,
  subject_role: "parent",
  object_person_id: child,
  object_role: "child",
  source_claim_ids: [],
});

const marriedTo = (a: string, b: string): ArchiveRelationship => ({
  edge_id: `edge_${(edgeId += 1)}`,
  relationship_type: "spouse",
  subject_person_id: a,
  subject_role: "spouse",
  object_person_id: b,
  object_role: "spouse",
  source_claim_ids: [],
});

const siblingOf = (a: string, b: string): ArchiveRelationship => ({
  edge_id: `edge_${(edgeId += 1)}`,
  relationship_type: "sibling",
  subject_person_id: a,
  subject_role: "sibling",
  object_person_id: b,
  object_role: "sibling",
  source_claim_ids: [],
});

const count = (ids: string[], edges: ArchiveRelationship[]) =>
  generationCount(buildFamilyRelations(ids.map(person), edges));

describe("generationCount", () => {
  it("counts one generation when nobody has a recorded parent", () => {
    expect(count(["a", "b", "c"], [])).toBe(1);
  });

  it("counts a parent and a child as two", () => {
    expect(count(["a", "b"], [parentOf("a", "b")])).toBe(2);
  });

  it("counts three across grandparent, parent and child", () => {
    expect(count(["a", "b", "c"], [parentOf("a", "b"), parentOf("b", "c")])).toBe(3);
  });

  it("does not count a spouse as a generation of their own", () => {
    // Marrying into a family does not make the family deeper.
    expect(count(["a", "b"], [marriedTo("a", "b")])).toBe(1);
  });

  it("does not count a sibling as a generation of their own", () => {
    expect(count(["a", "b"], [siblingOf("a", "b")])).toBe(1);
  });

  it("places a child below its deepest parent", () => {
    // One parent is a root and the other is already a child; their child
    // belongs under the deeper of the two, not the shallower.
    const edges = [parentOf("gran", "mum"), parentOf("mum", "kid"), parentOf("dad", "kid")];
    expect(count(["gran", "mum", "dad", "kid"], edges)).toBe(3);
  });

  it("counts only the depths that are occupied", () => {
    // Two separate couples with children: two depths, four people.
    const edges = [parentOf("a", "b"), parentOf("c", "d")];
    expect(count(["a", "b", "c", "d"], edges)).toBe(2);
  });

  it("survives a cycle instead of recursing forever", () => {
    // Not a family that can exist, but a graph built from what people said can
    // still contain one, and the home screen must not crash on it.
    const edges = [parentOf("a", "b"), parentOf("b", "a")];
    expect(() => count(["a", "b"], edges)).not.toThrow();
    expect(count(["a", "b"], edges)).toBeGreaterThan(0);
  });

  it("returns zero for an empty archive", () => {
    expect(count([], [])).toBe(0);
  });
});
