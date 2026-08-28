"use client";

import { motion } from "framer-motion";

/**
 * The signature.
 *
 * ## What it replaces, and why
 *
 * Four translucent circles stacked vertically. They were a design exercise:
 * they came from the mood reference rather than from MURA, they meant nothing
 * a viewer could name, and on the ink panel they rendered as a grey smudge.
 * Decoration derived from another product's decoration is the definition of
 * templated.
 *
 * ## What this draws
 *
 * The product's one sentence, as a picture: **a voice becomes a family.**
 *
 * On the left, a waveform — somebody talking. Moving right, the bars lose
 * height and settle into points; the points become people; the people connect
 * into generations. Left to right is also the direction the pipeline runs, so
 * the image is the process, not an ornament beside it.
 *
 * Every part of it is a thing this product actually holds — an utterance, a
 * person, a relationship — which is what earns it a place on the screens where
 * a family is deciding whether to trust MURA with twenty years of recordings.
 *
 * Drawn in `currentColor` with the accents layered on top, so it sits on ink
 * and on paper without a second copy.
 */

/** Bar heights, hand-set to read as speech rather than as a chart. */
const BARS = [
  6, 13, 9, 20, 28, 17, 34, 24, 40, 30, 21, 33, 18, 25, 12, 16, 8, 10, 6, 5,
];

/**
 * The family, drawn the way a family tree is actually drawn.
 *
 * Three generations in rows, joined by orthogonal stems: a couple bar, a drop
 * to a sibling bar, then a drop to each child. The first attempt used diagonal
 * spokes from one central node, which renders as a starburst — a network
 * diagram, not a lineage. Right angles are what make generations legible.
 */
const NODES = [
  // Generation one: a couple.
  { x: 176, y: 26, r: 7, accent: "var(--color-peach)" },
  { x: 220, y: 26, r: 7, accent: "var(--color-periwinkle)" },
  // Generation two: their children. The middle one carries the line on.
  { x: 154, y: 82, r: 6, accent: "var(--color-periwinkle)" },
  { x: 198, y: 82, r: 8.5, accent: "var(--color-peach)" },
  { x: 242, y: 82, r: 6, accent: "var(--color-sage)" },
  // Generation three.
  { x: 176, y: 132, r: 5.5, accent: "var(--color-peach)" },
  { x: 220, y: 132, r: 5.5, accent: "var(--color-periwinkle)" },
];

/**
 * The connectors, as orthogonal segments in viewBox units.
 * Each entry is [x1, y1, x2, y2].
 */
const STEMS: ReadonlyArray<[number, number, number, number]> = [
  [176, 26, 220, 26], // the couple bar
  [198, 26, 198, 52], // drop from the couple
  [154, 52, 242, 52], // sibling bar
  [154, 52, 154, 82], // down to each child
  [198, 52, 198, 82],
  [242, 52, 242, 82],
  [198, 82, 198, 108], // the middle child carries the line on
  [176, 108, 220, 108], // the next sibling bar
  [176, 108, 176, 132],
  [220, 108, 220, 132],
];

const EASE = [0.23, 1, 0.32, 1] as const;

export function VoiceToFamily({
  className,
  /** Slow ambient movement in the waveform. Off where it sits behind text. */
  animate = true,
  delay = 0,
}: {
  className?: string;
  animate?: boolean;
  delay?: number;
}) {
  return (
    <svg
      // Decorative: the words beside it carry the meaning, and a screen reader
      // announcing twenty bars and seven circles would be noise.
      aria-hidden
      focusable="false"
      viewBox="0 0 258 158"
      preserveAspectRatio="xMidYMid meet"
      className={className}
    >
      {/* The utterance. Rounded caps so it reads as sound, not as a bar chart. */}
      <g>
        {BARS.map((height, index) => {
          const x = 4 + index * 5.4;
          return (
            <motion.line
              key={index}
              x1={x}
              x2={x}
              y1={79 - height / 2}
              y2={79 + height / 2}
              stroke="currentColor"
              // Fading out to the right is the hand-off: the sound stops being
              // sound and starts being structure.
              strokeOpacity={0.5 - index * 0.017}
              strokeWidth={2.4}
              strokeLinecap="round"
              initial={{ scaleY: 0.25, opacity: 0 }}
              animate={
                animate
                  ? { scaleY: [1, 0.62, 1], opacity: 1 }
                  : { scaleY: 1, opacity: 1 }
              }
              style={{ transformOrigin: `${x}px 79px` }}
              transition={{
                opacity: { duration: 0.5, delay: delay + index * 0.022, ease: EASE },
                scaleY: animate
                  ? {
                      duration: 3.4 + (index % 5) * 0.55,
                      repeat: Infinity,
                      ease: "easeInOut",
                      delay: delay + index * 0.07,
                    }
                  : { duration: 0.5, delay: delay + index * 0.022, ease: EASE },
              }}
            />
          );
        })}
      </g>

      {/* The relationships, drawn before the people so the stems run under. */}
      <g stroke="currentColor" strokeOpacity={0.3} strokeWidth={1.15} strokeLinecap="round">
        {STEMS.map(([x1, y1, x2, y2], index) => (
          <motion.line
            key={index}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.55, delay: delay + 0.45 + index * 0.05, ease: EASE }}
          />
        ))}
      </g>

      {/* The people. */}
      <g>
        {NODES.map((node, index) => (
          <motion.circle
            key={index}
            cx={node.x}
            cy={node.y}
            r={node.r}
            fill={node.accent}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            style={{ transformOrigin: `${node.x}px ${node.y}px` }}
            transition={{
              type: "spring",
              stiffness: 260,
              damping: 20,
              delay: delay + 0.55 + index * 0.06,
            }}
          />
        ))}
      </g>
    </svg>
  );
}
