import type { FamilyRelations } from "@/lib/mura/family-graph";

export const CARD_WIDTH = 176;
export const CARD_HEIGHT = 108;
const COLUMN_WIDTH = 256;
const ROW = 136;
const PAIR_GAP = 200;

export type NodeRole =
  | "center"
  | "spouse"
  | "sibling"
  | "parent"
  | "grandparent"
  | "child"
  | "grandchild";

export interface FamilyGraphNode {
  /** Canonical archive person id. Never a display name. */
  id: string;
  x: number;
  y: number;
  role: NodeRole;
  canExpandAncestors?: boolean;
  ancestorsExpanded?: boolean;
  canExpandDescendants?: boolean;
  descendantsExpanded?: boolean;
}

export interface FamilyGraphEdge {
  id: string;
  d: string;
  kind: "lineage" | "marriage";
  /** When this edge should start drawing, so outer branches grow last. */
  delay: number;
}

export interface FamilyGraph {
  nodes: FamilyGraphNode[];
  edges: FamilyGraphEdge[];
}

/** Spreads ids evenly across `rowGap`, centered on y = 0. */
function stackColumn(ids: string[], rowGap: number): Record<string, number> {
  const n = ids.length;
  const y: Record<string, number> = {};
  ids.forEach((id, i) => {
    y[id] = -((n - 1) / 2) * rowGap + i * rowGap;
  });
  return y;
}

/** Same spread, shifted so `anchorId` lands exactly on y = 0. */
function stackCentered(
  ids: string[],
  anchorId: string,
  rowGap: number,
): Record<string, number> {
  const raw = stackColumn(ids, rowGap);
  const offset = raw[anchorId] ?? 0;
  const y: Record<string, number> = {};
  for (const id of ids) y[id] = raw[id] - offset;
  return y;
}

const rightEdge = (x: number) => x + CARD_WIDTH / 2;
const leftEdge = (x: number) => x - CARD_WIDTH / 2;

interface Anchor {
  id: string;
  x: number;
  y: number;
}

/** An organic root-like curve between two card edges. */
function lineageEdge(from: Anchor, to: Anchor): FamilyGraphEdge {
  const fromX = rightEdge(from.x);
  const fromY = from.y;
  const toX = leftEdge(to.x);
  const toY = to.y;
  const pull = Math.max(Math.abs(toX - fromX) * 0.55, 64);
  const outer = Math.abs(from.x) > Math.abs(to.x) ? from : to;
  return {
    id: `${from.id}-${to.id}`,
    kind: "lineage",
    d: `M ${fromX} ${fromY} C ${fromX + pull} ${fromY}, ${toX - pull} ${toY}, ${toX} ${toY}`,
    delay: distanceDelay(outer.x, outer.y),
  };
}

/** A short, near-straight bond between two side-by-side cards. */
function marriageEdge(centerX: number, spouseX: number): FamilyGraphEdge {
  const fromX = rightEdge(centerX);
  const toX = leftEdge(spouseX);
  const midY = -10;
  return {
    id: "marriage",
    kind: "marriage",
    d: `M ${fromX} 0 Q ${(fromX + toX) / 2} ${midY}, ${toX} 0`,
    delay: 0.18,
  };
}

/**
 * Builds the whole visible graph for a person-centric family tree: the
 * center stays pinned to (0, 0), parents/grandparents grow left, children/
 * grandchildren grow right, spouse sits beside, siblings stack around the
 * center. Grandparents and grandchildren only appear once their connecting
 * parent/child has been expanded.
 */
export function computeFamilyGraph(
  relations: FamilyRelations,
  centerId: string,
  expandedAncestors: ReadonlySet<string>,
  expandedDescendants: ReadonlySet<string>,
): FamilyGraph {
  const { parentsOf, childrenOf, siblingsOf, spouseOf, personById } = relations;
  if (!personById(centerId)) return { nodes: [], edges: [] };

  // Stable ordering without inventing chronology. The archive rarely knows a
  // birth year, and sorting by one it does not have would impose a made-up
  // order on a family; display name is arbitrary but honest and stable.
  const byName = (a: string, b: string) =>
    (personById(a)?.display_name ?? "").localeCompare(personById(b)?.display_name ?? "");

  const nodes: FamilyGraphNode[] = [];
  const edges: FamilyGraphEdge[] = [];

  // Column 0 — center, siblings stacked around it (center pinned to y = 0).
  const col0Ids = [...siblingsOf(centerId), centerId].sort(byName);
  const col0Y = stackCentered(col0Ids, centerId, ROW);
  for (const id of col0Ids) {
    nodes.push({
      id,
      x: 0,
      y: col0Y[id],
      role: id === centerId ? "center" : "sibling",
    });
  }

  const spouse = spouseOf(centerId);
  if (spouse) {
    nodes.push({ id: spouse, x: PAIR_GAP, y: 0, role: "spouse" });
    edges.push(marriageEdge(0, PAIR_GAP));
  }

  // Columns -1 / -2 — parents, then grandparents of any expanded parent.
  const parents = parentsOf(centerId).slice().sort(byName);
  if (parents.length > 0) {
    const parentY = stackColumn(parents, ROW);

    for (const parent of parents) {
      nodes.push({
        id: parent,
        x: -COLUMN_WIDTH,
        y: parentY[parent],
        role: "parent",
        canExpandAncestors: parentsOf(parent).length > 0,
        ancestorsExpanded: expandedAncestors.has(parent),
      });
      for (const id of col0Ids) {
        edges.push(
          lineageEdge(
            { id: parent, x: -COLUMN_WIDTH, y: parentY[parent] },
            { id, x: 0, y: col0Y[id] },
          ),
        );
      }
    }

    const grandparents: { id: string; viaId: string; viaY: number }[] = [];
    for (const parent of parents) {
      if (!expandedAncestors.has(parent)) continue;
      for (const gp of parentsOf(parent).slice().sort(byName)) {
        grandparents.push({ id: gp, viaId: parent, viaY: parentY[parent] });
      }
    }
    if (grandparents.length > 0) {
      const gpY = stackColumn(grandparents.map((g) => g.id), ROW);
      for (const gp of grandparents) {
        nodes.push({
          id: gp.id,
          x: -2 * COLUMN_WIDTH,
          y: gpY[gp.id],
          role: "grandparent",
        });
        edges.push(
          lineageEdge(
            { id: gp.id, x: -2 * COLUMN_WIDTH, y: gpY[gp.id] },
            { id: gp.viaId, x: -COLUMN_WIDTH, y: gp.viaY },
          ),
        );
      }
    }
  }

  // Columns +1 / +2 — children, then grandchildren of any expanded child.
  const childrenX = (spouse ? PAIR_GAP : 0) + COLUMN_WIDTH;
  const children = childrenOf(centerId).slice().sort(byName);
  if (children.length > 0) {
    const childY = stackColumn(children, ROW);

    for (const child of children) {
      nodes.push({
        id: child,
        x: childrenX,
        y: childY[child],
        role: "child",
        canExpandDescendants: childrenOf(child).length > 0,
        descendantsExpanded: expandedDescendants.has(child),
      });
      edges.push(
        lineageEdge(
          { id: centerId, x: 0, y: 0 },
          { id: child, x: childrenX, y: childY[child] },
        ),
      );
    }

    const grandchildren: { id: string; viaId: string; viaY: number }[] = [];
    for (const child of children) {
      if (!expandedDescendants.has(child)) continue;
      for (const gc of childrenOf(child).slice().sort(byName)) {
        grandchildren.push({ id: gc, viaId: child, viaY: childY[child] });
      }
    }
    if (grandchildren.length > 0) {
      const gcY = stackColumn(grandchildren.map((g) => g.id), ROW);
      for (const gc of grandchildren) {
        nodes.push({
          id: gc.id,
          x: childrenX + COLUMN_WIDTH,
          y: gcY[gc.id],
          role: "grandchild",
        });
        edges.push(
          lineageEdge(
            { id: gc.viaId, x: childrenX, y: gc.viaY },
            { id: gc.id, x: childrenX + COLUMN_WIDTH, y: gcY[gc.id] },
          ),
        );
      }
    }
  }

  return { nodes, edges };
}

/**
 * Everyone `computeFamilyGraph` is capable of placing around `centerId`, with
 * every branch expanded.
 *
 * This exists because "who is drawn" and "who is reachable" are different
 * questions, and answering the second one instead of the first made people
 * vanish. The canvas is person-centric: it draws the centre's own parents,
 * children, siblings and spouse, plus one further ring once expanded. A walk
 * over the whole relationship graph, by contrast, reaches anyone connected by
 * any chain — so a spouse's child from another edge counted as "reachable",
 * was therefore left out of the «not on this branch» strip, and was never
 * drawn either. They were simply absent from the family screen.
 *
 * Anyone outside this set genuinely cannot appear on this canvas and must be
 * named in the strip instead.
 */
export function drawableFrom(
  relations: FamilyRelations,
  centerId: string,
): Set<string> {
  const { parentsOf, childrenOf, siblingsOf, spouseOf } = relations;
  const drawable = new Set<string>([centerId, ...siblingsOf(centerId)]);

  const spouse = spouseOf(centerId);
  if (spouse) drawable.add(spouse);

  for (const parent of parentsOf(centerId)) {
    drawable.add(parent);
    for (const grandparent of parentsOf(parent)) drawable.add(grandparent);
  }

  for (const child of childrenOf(centerId)) {
    drawable.add(child);
    for (const grandchild of childrenOf(child)) drawable.add(grandchild);
  }

  return drawable;
}

/** Stagger delay based on distance from the center, so the tree grows outward. */
export function distanceDelay(x: number, y: number): number {
  const columns = Math.abs(x) / COLUMN_WIDTH;
  const rows = Math.abs(y) / ROW;
  return 0.1 + columns * 0.12 + rows * 0.03;
}
