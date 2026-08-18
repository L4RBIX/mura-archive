import { describe, expect, it } from "vitest";
import type { ArchivePerson, ArchiveRelationship } from "@/lib/mura/archive-api";
import { buildFamilyRelations } from "@/lib/mura/family-graph";
import {
  computeFamilyGraph,
  computeIslands,
  connectedComponents,
  drawableFrom,
  graphBounds,
} from "@/components/tree/layout";

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
  type: "parent_child" | "spouse",
  subject: string,
  object: string,
): ArchiveRelationship => ({
  edge_id: id,
  relationship_type: type,
  subject_person_id: subject,
  subject_role: type === "spouse" ? "spouse" : "parent",
  object_person_id: object,
  object_role: type === "spouse" ? "spouse" : "child",
  source_claim_ids: [],
});

/**
 * The shape the real dev archive has: Айсұлу–Марат married, Марат parent of
 * Болат, and a second, unconnected island of Бибігүл–Сабыр.
 */
const PEOPLE = [
  person("p_aisulu", "Айсұлу"),
  person("p_marat", "Марат"),
  person("p_bolat", "Болат"),
  person("p_bibigul", "Бибігүл"),
  person("p_sabyr", "Сабыр"),
];
const EDGES = [
  edge("e1", "spouse", "p_marat", "p_aisulu"),
  edge("e2", "parent_child", "p_marat", "p_bolat"),
  edge("e3", "spouse", "p_bibigul", "p_sabyr"),
];

const relations = buildFamilyRelations(PEOPLE, EDGES);
const NO_EXPANSION = new Set<string>();

describe("tree layout", () => {
  it("never draws more edges than the archive recorded", () => {
    // The invariant that matters: an edge on the canvas must correspond to a
    // relationship Core materialised. Checked for every possible centre, with
    // the islands included, since islands draw edges too.
    for (const p of PEOPLE) {
      const graph = computeFamilyGraph(relations, p.person_id, NO_EXPANSION, NO_EXPANSION);
      const islands = computeIslands(relations, p.person_id, 0);
      const drawn = graph.edges.length + islands.reduce((n, i) => n + i.edges.length, 0);
      expect(drawn).toBeLessThanOrEqual(EDGES.length);
    }
  });

  it("draws no edge at all when the archive recorded none", () => {
    const lonely = buildFamilyRelations(PEOPLE, []);
    for (const p of PEOPLE) {
      const graph = computeFamilyGraph(lonely, p.person_id, NO_EXPANSION, NO_EXPANSION);
      const islands = computeIslands(lonely, p.person_id, 0);
      expect(graph.edges).toHaveLength(0);
      expect(islands.every((i) => i.edges.length === 0)).toBe(true);
    }
  });

  it("finds the archive's real islands", () => {
    const components = connectedComponents(relations).map((c) => c.sort());
    expect(components).toHaveLength(2);
    expect(components).toContainEqual(["p_aisulu", "p_bolat", "p_marat"]);
    expect(components).toContainEqual(["p_bibigul", "p_sabyr"]);
  });

  it("accounts for every person: drawn around the centre, or on an island", () => {
    // The bug this replaced: Болат was reachable by a graph walk but not
    // drawable from Айсұлу, so he appeared in neither place and vanished.
    for (const p of PEOPLE) {
      const graph = computeFamilyGraph(relations, p.person_id, NO_EXPANSION, NO_EXPANSION);
      const islands = computeIslands(relations, p.person_id, 0);
      const shown = new Set([
        ...graph.nodes.map((n) => n.id),
        ...islands.flatMap((i) => i.members),
      ]);
      for (const other of PEOPLE) {
        expect(shown.has(other.person_id)).toBe(true);
      }
    }
  });

  it("puts nobody on an island who is already drawn around the centre", () => {
    for (const p of PEOPLE) {
      const drawable = drawableFrom(relations, p.person_id);
      const islands = computeIslands(relations, p.person_id, 0);
      for (const member of islands.flatMap((i) => i.members)) {
        expect(drawable.has(member)).toBe(false);
      }
    }
  });

  it("places islands clear of the branch in the centre", () => {
    const graph = computeFamilyGraph(relations, "p_aisulu", NO_EXPANSION, NO_EXPANSION);
    const below = graphBounds(graph.nodes).maxY;
    const islands = computeIslands(relations, "p_aisulu", below);
    for (const node of islands.flatMap((i) => i.nodes)) {
      expect(node.y).toBeGreaterThan(below);
    }
  });

  it("grows the bounding box by half a card so nobody is clipped by a fit", () => {
    const graph = computeFamilyGraph(relations, "p_marat", NO_EXPANSION, NO_EXPANSION);
    const bounds = graphBounds(graph.nodes);
    const xs = graph.nodes.map((n) => n.x);
    expect(bounds.minX).toBeLessThan(Math.min(...xs));
    expect(bounds.maxX).toBeGreaterThan(Math.max(...xs));
  });

  it("returns an empty box for an empty graph rather than NaN", () => {
    expect(graphBounds([])).toEqual({ minX: 0, minY: 0, maxX: 0, maxY: 0 });
  });
});

describe("island captions tell the truth about connection", () => {
  it("marks a relative who is connected but undrawable as still on this branch", () => {
    // Болат is Марат's child; Марат is drawn beside Айсұлу. Centred on Айсұлу,
    // Болат cannot be drawn — but captioning him "a separate branch" would
    // claim the archive knows of no connection, which is false.
    const islands = computeIslands(relations, "p_aisulu", 0);
    const bolat = islands.find((i) => i.members.includes("p_bolat"));
    expect(bolat?.connectedToCentre).toBe(true);
  });

  it("marks a genuinely separate component as unconnected", () => {
    const islands = computeIslands(relations, "p_aisulu", 0);
    const other = islands.find((i) => i.members.includes("p_bibigul"));
    expect(other?.connectedToCentre).toBe(false);
  });
});
