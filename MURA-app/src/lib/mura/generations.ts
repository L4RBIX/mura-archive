import type { FamilyRelations } from "@/lib/mura/family-graph";

/**
 * How many generations the archive actually reaches across.
 *
 * "3 поколения" is the single most emotionally accurate number this product
 * can put on a screen: it is the whole promise of a family archive, stated as
 * a fact. So it has to be derived, never estimated — a wrong generation count
 * on the home screen of a memory product is worse than no count at all.
 *
 * Computed by walking `parent_child` edges: everyone with no recorded parent
 * inside the archive is depth 0, and each child sits one below the deepest
 * parent it has. The answer is the number of distinct depths that are actually
 * occupied.
 *
 * Deliberately ignores spouses and siblings. Marrying into a family does not
 * add a generation to it, and neither does having a brother.
 *
 * Cycles cannot crash it: every person is assigned a depth exactly once, and a
 * person already being resolved is treated as resolved. The archive should not
 * contain a cycle, but a family graph built from what people said out loud is
 * not a place to assume that.
 */
export function generationCount(relations: FamilyRelations): number {
  const depth = new Map<string, number>();
  const resolving = new Set<string>();

  const depthOf = (personId: string): number => {
    const known = depth.get(personId);
    if (known !== undefined) return known;
    // Already on the stack: a cycle. Treat it as a root rather than recursing.
    if (resolving.has(personId)) return 0;

    resolving.add(personId);
    const parents = relations.parentsOf(personId);
    const value =
      parents.length === 0 ? 0 : Math.max(...parents.map((parent) => depthOf(parent) + 1));
    resolving.delete(personId);

    depth.set(personId, value);
    return value;
  };

  const occupied = new Set<number>();
  for (const person of relations.people) occupied.add(depthOf(person.person_id));
  return occupied.size;
}
