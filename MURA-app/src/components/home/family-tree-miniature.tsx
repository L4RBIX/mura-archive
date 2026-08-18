"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * A three-generation family tree, drawn small.
 *
 * Read as a diagram rather than an icon: generation is encoded in vertical
 * band, seniority in node size, and the branching is deliberately uneven —
 * two children on one side, one on the other — because a real family is not
 * symmetrical. Everything is in one 64-unit viewBox so it stays sharp at any
 * rendered size and can be animated later without re-authoring.
 */

interface Node {
  id: string;
  x: number;
  y: number;
  r: number;
  fill: string;
  /** Order of appearance, in generations. */
  gen: 0 | 1 | 2;
}

const NODES: Node[] = [
  // Elder generation: one root, largest, charcoal — the anchor of the family.
  { id: "elder", x: 34, y: 15.5, r: 7, fill: "var(--color-ink)", gen: 0 },
  // Middle generation.
  { id: "parent-l", x: 19.5, y: 35, r: 5.6, fill: "var(--color-clay)", gen: 1 },
  { id: "parent-r", x: 48.5, y: 35, r: 5.6, fill: "var(--color-periwinkle)", gen: 1 },
  // Youngest generation, unevenly distributed.
  { id: "child-a", x: 11.5, y: 54.5, r: 4.4, fill: "var(--color-periwinkle)", gen: 2 },
  { id: "child-b", x: 27, y: 54.5, r: 4.4, fill: "var(--color-clay)", gen: 2 },
  { id: "child-c", x: 51, y: 54.5, r: 4.4, fill: "var(--color-clay)", gen: 2 },
];

const byId = (id: string) => NODES.find((node) => node.id === id)!;

const EDGES: Array<[string, string]> = [
  ["elder", "parent-l"],
  ["elder", "parent-r"],
  ["parent-l", "child-a"],
  ["parent-l", "child-b"],
  ["parent-r", "child-c"],
];

/**
 * A soft S-curve from the underside of the parent to the crown of the child,
 * so a line never crosses a node and the join always looks intentional.
 */
function edgePath(fromId: string, toId: string): string {
  const from = byId(fromId);
  const to = byId(toId);
  const start = from.y + from.r;
  const end = to.y - to.r;
  const waist = start + (end - start) * 0.55;
  return `M${from.x},${start} C${from.x},${waist} ${to.x},${end - (end - start) * 0.45} ${to.x},${end}`;
}

/** Under 700ms end to end, sequenced by generation. */
const TIMING = {
  node: (gen: number, index: number) => ({
    delay: gen === 0 ? 0 : gen === 1 ? 0.22 + index * 0.04 : 0.4 + index * 0.04,
    duration: gen === 0 ? 0.2 : 0.18,
  }),
  edge: (gen: number, index: number) => ({
    delay: (gen === 0 ? 0.12 : 0.3) + index * 0.03,
    duration: 0.22,
  }),
} as const;

const EASE = [0.23, 1, 0.32, 1] as const;

export interface FamilyTreeMiniatureProps {
  /** Rendered square size in px. Legible from about 44 up. */
  size?: number;
  /** Opt into the entrance. Static otherwise. */
  animate?: boolean;
  className?: string;
}

export function FamilyTreeMiniature({
  size = 64,
  animate = false,
  className,
}: FamilyTreeMiniatureProps) {
  const reduced = useReducedMotion() ?? false;
  const uid = useId().replace(/:/g, "");
  const shadowId = `ftm-shadow-${uid}`;
  const haloId = `ftm-halo-${uid}`;
  // Opt-in, and never against the user's motion preference. Left off, every
  // element renders in its final state with no transition to wait on.
  const moving = animate && !reduced;

  return (
    <svg
      aria-hidden
      focusable="false"
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={cn("shrink-0 overflow-visible", className)}
    >
      <defs>
        <radialGradient id={haloId}>
          <stop offset="45%" stopColor="var(--color-ink)" stopOpacity={0.07} />
          <stop offset="100%" stopColor="var(--color-ink)" stopOpacity={0} />
        </radialGradient>
        <filter id={shadowId} x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow
            dx="0"
            dy="0.8"
            stdDeviation="1"
            floodColor="#0b0b0b"
            floodOpacity="0.16"
          />
        </filter>
      </defs>

      {/* Translucent halo behind the root: depth, faded out so it reads as air
          rather than a second disc. */}
      <motion.circle
        cx={34}
        cy={15.5}
        r={13}
        fill={`url(#${haloId})`}
        initial={moving ? { opacity: 0, scale: 0.7 } : false}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, ease: EASE }}
        style={{ transformOrigin: "34px 15.5px" }}
      />

      <g
        fill="none"
        stroke="var(--color-ink)"
        strokeOpacity={0.17}
        strokeWidth={1.35}
        strokeLinecap="round"
      >
        {EDGES.map(([from, to], index) => {
          const gen = byId(from).gen;
          const { delay, duration } = TIMING.edge(gen, gen === 0 ? index : index - 2);
          return (
            <motion.path
              key={`${from}-${to}`}
              d={edgePath(from, to)}
              initial={moving ? { pathLength: 0, opacity: 0 } : false}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ delay, duration, ease: EASE }}
            />
          );
        })}
      </g>

      <g filter={`url(#${shadowId})`}>
        {NODES.map((node, index) => {
          const withinGen = NODES.filter(
            (other, i) => other.gen === node.gen && i < index,
          ).length;
          const { delay, duration } = TIMING.node(node.gen, withinGen);
          return (
            <motion.circle
              key={node.id}
              cx={node.x}
              cy={node.y}
              r={node.r}
              fill={node.fill}
              fillOpacity={node.gen === 0 ? 0.74 : node.gen === 1 ? 1 : 0.92}
              initial={moving ? { opacity: 0, scale: 0.55 } : false}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay, duration, ease: EASE }}
              style={{ transformOrigin: `${node.x}px ${node.y}px` }}
            />
          );
        })}
      </g>
    </svg>
  );
}
