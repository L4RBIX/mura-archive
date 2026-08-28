"use client";

import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
  type MotionValue,
} from "framer-motion";
import Image from "next/image";
import { memo, useEffect } from "react";
import type { MascotState } from "@/lib/mascot/types";
import { cn } from "@/lib/utils";

/**
 * Ласточка, rigged.
 *
 * The artwork is untouched: `scripts` sliced the original PNG into parts on one
 * shared canvas, so every layer is `absolute inset-0` and only its
 * transform-origin differs. Nothing here knows why the mascot is in a state —
 * it just knows how that state looks.
 */

/** Pivots, as a share of the source canvas. Resolution independent. */
const ORIGIN = {
  body: "44.9% 64.8%", // where the feet meet the ground
  wing: "42.7% 50.4%", // shoulder
  head: "51.1% 45.7%", // base of the neck
  jaw: "36.5% 40.5%", // mandible hinge
  throat: "39.1% 39.3%", // top of the yellow patch
  eye: "41.9% 38.0%",
} as const;

interface Pose {
  headRotate: number;
  headY: number;
  bodyRotate: number;
  bodyY: number;
  wingRotate: number;
  /** Seconds for one breath in / out. */
  breath: number;
  /** Pixels of vertical drift, at the source canvas's scale. */
  float: number;
  blinkEvery: [number, number];
}

/**
 * Every state's resting pose. Negative head rotation lifts the beak, because
 * the beak sits left of the neck pivot.
 */
const POSES: Record<MascotState, Pose> = {
  idle: { headRotate: 0, headY: 0, bodyRotate: 0, bodyY: 0, wingRotate: 0, breath: 3.6, float: 3, blinkEvery: [2600, 6400] },
  greeting: { headRotate: -1.6, headY: -2, bodyRotate: -0.5, bodyY: -3, wingRotate: -0.7, breath: 3.0, float: 4, blinkEvery: [2400, 4800] },
  listening: { headRotate: -0.8, headY: -1, bodyRotate: -1.1, bodyY: -2, wingRotate: 0.5, breath: 2.5, float: 2, blinkEvery: [1900, 4200] },
  processing: { headRotate: -2.6, headY: -3, bodyRotate: 0.3, bodyY: 0, wingRotate: 1.0, breath: 4.2, float: 3, blinkEvery: [3200, 7000] },
  thinking: { headRotate: -3.4, headY: -4, bodyRotate: 0.5, bodyY: 1, wingRotate: 1.3, breath: 4.6, float: 3, blinkEvery: [3400, 7400] },
  searching: { headRotate: -2.0, headY: -2, bodyRotate: -0.4, bodyY: 0, wingRotate: 0.8, breath: 3.4, float: 4, blinkEvery: [2200, 4600] },
  speaking: { headRotate: -0.9, headY: -1, bodyRotate: -0.3, bodyY: -1, wingRotate: -0.4, breath: 3.1, float: 3, blinkEvery: [2400, 5600] },
  success: { headRotate: -2.2, headY: -4, bodyRotate: -0.8, bodyY: -5, wingRotate: -1.2, breath: 3.2, float: 4, blinkEvery: [2600, 5200] },
  error: { headRotate: 2.4, headY: 2, bodyRotate: 0.9, bodyY: 2, wingRotate: 1.4, breath: 4.4, float: 2, blinkEvery: [3000, 6000] },
};

const POSE_SPRING = { type: "spring", stiffness: 62, damping: 18, mass: 1.1 } as const;

/**
 * One part of the swallow.
 *
 * Every layer loads with `priority`, not just the base and the head.
 *
 * The eight parts are one illustration: a bird drawn without its beak or its
 * eye does not read as a slightly incomplete bird, it reads as a broken image.
 * Marking only two of them meant the other six raced, and whichever lost became
 * the Largest Contentful Paint — Next reported exactly that for `part-mouth`
 * and `part-throat`, which is the browser saying the visible bird finished late.
 *
 * The whole set is 200 KB and appears above the fold on the screen the product
 * is built around, so there is nothing here worth deferring.
 */
function Layer({ src }: { src: string }) {
  return (
    <Image
      src={src}
      alt=""
      width={640}
      height={640}
      priority
      unoptimized
      draggable={false}
      className="pointer-events-none absolute inset-0 h-full w-full select-none"
    />
  );
}

function useBlink(range: [number, number], enabled: boolean): MotionValue<number> {
  const lid = useMotionValue(1);
  useEffect(() => {
    if (!enabled) {
      lid.set(1);
      return;
    }
    let cancelled = false;
    let timer = 0;
    const [min, max] = range;

    const run = async () => {
      if (cancelled) return;
      await animate(lid, 0.06, { duration: 0.07, ease: "easeIn" });
      if (cancelled) return;
      await animate(lid, 1, { duration: 0.12, ease: "easeOut" });
      // Birds often blink twice. Rarely enough that it reads as alive.
      if (!cancelled && Math.random() < 0.22) {
        await animate(lid, 0.08, { duration: 0.06, ease: "easeIn" });
        if (cancelled) return;
        await animate(lid, 1, { duration: 0.1, ease: "easeOut" });
      }
      schedule();
    };

    const schedule = () => {
      if (cancelled) return;
      timer = window.setTimeout(run, min + Math.random() * (max - min));
    };

    schedule();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [lid, enabled, range]);
  return lid;
}

/** Slow, irregular gaze drift. Never a pattern the eye can learn. */
function useGaze(enabled: boolean) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  useEffect(() => {
    if (!enabled) {
      x.set(0);
      y.set(0);
      return;
    }
    let cancelled = false;
    let timer = 0;
    const step = () => {
      if (cancelled) return;
      const settle = { duration: 0.5, ease: [0.23, 1, 0.32, 1] as const };
      animate(x, (Math.random() - 0.5) * 1.6, settle);
      animate(y, (Math.random() - 0.5) * 1.2, settle);
      timer = window.setTimeout(step, 2400 + Math.random() * 4200);
    };
    timer = window.setTimeout(step, 1600);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [x, y, enabled]);
  return { x, y };
}

export interface LastochkaProps {
  state: MascotState;
  /** Drives the mouth. Omit and the mascot simply never speaks. */
  /** Rendered size in px. The rig is resolution independent. */
  size?: number;
  className?: string;
}

function LastochkaImpl({ state, size = 260, className }: LastochkaProps) {
  const reduced = useReducedMotion() ?? false;
  const pose = POSES[state];
  const alive = !reduced;

  const lid = useBlink(pose.blinkEvery, alive);
  const gaze = useGaze(alive);

  // Speech. A silent MotionValue when there is no audio, so the transforms
  // below stay identical either way.
  const idle = useMotionValue(0);
  const energy = idle;

  // Quiet speech still has to move the beak, hence the gamma: it lifts the low
  // end of the envelope so unstressed syllables read, while loud vowels still
  // saturate at a believable maximum gape.
  const shaped = useTransform(energy, (value) => (alive ? Math.pow(value, 0.62) : 0));
  const jawRotate = useTransform(shaped, [0, 1], [0, 11]);
  const throatScale = useTransform(shaped, [0, 1], [1, 1.075]);
  const speechBob = useTransform(shaped, [0, 1], [0, -4.6]);

  // Scale the source-canvas offsets to the rendered size.
  const k = size / 640;
  const speechBobPx = useTransform(speechBob, (v) => v * k);
  const gazeXPx = useTransform(gaze.x, (v) => v * k);
  const gazeYPx = useTransform(gaze.y, (v) => v * k);

  // `size` is the intent; the viewport caps it. A 288px mascot stays 288px on
  // a tall phone and scales down on a short or narrow one, so the page never
  // overflows and no breakpoint or resize listener is needed.
  const box = `min(${size}px, 66vw, 37dvh)`;

  return (
    <div
      className={cn("relative shrink-0", className)}
      style={{ width: box, height: box }}
      role="img"
      aria-label="Ласточка"
    >
      {/* Contact shadow: stays on the ground while the body drifts above it. */}
      <motion.div
        aria-hidden
        className="absolute inset-0"
        animate={
          alive
            ? { scale: [1, 0.955, 1], opacity: [0.9, 0.66, 0.9] }
            : { scale: 1, opacity: 0.9 }
        }
        transition={
          alive
            ? { duration: pose.breath, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0 }
        }
        style={{ transformOrigin: ORIGIN.body }}
      >
        <Layer src="/mascot/part-shadow.png" />
      </motion.div>

      {/* Breathing + float. One loop for the whole body. */}
      <motion.div
        className="absolute inset-0"
        style={{ transformOrigin: ORIGIN.body }}
        animate={
          alive
            ? { scaleY: [1, 1.022, 1], scaleX: [1, 0.994, 1], y: [0, -pose.float * k, 0] }
            : { scaleY: 1, scaleX: 1, y: 0 }
        }
        transition={
          alive
            ? { duration: pose.breath, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0 }
        }
      >
        {/* Posture: the state's resting lean. */}
        <motion.div
          className="absolute inset-0"
          style={{ transformOrigin: ORIGIN.body }}
          animate={{ rotate: pose.bodyRotate, y: pose.bodyY * k }}
          transition={POSE_SPRING}
        >
          <Layer src="/mascot/part-base.png" />

          <motion.div
            className="absolute inset-0"
            style={{ transformOrigin: ORIGIN.wing }}
            animate={{ rotate: pose.wingRotate }}
            transition={POSE_SPRING}
          >
            <Layer src="/mascot/part-wing.png" />
          </motion.div>

          {/* Head group: everything that follows the neck. */}
          <motion.div
            className="absolute inset-0"
            style={{ transformOrigin: ORIGIN.head }}
            animate={{ rotate: pose.headRotate, y: pose.headY * k }}
            transition={POSE_SPRING}
          >
            {/*
              Micro-sway. Always on, in every state, on a period deliberately
              coprime with the breath so the two never lock into a visible
              rhythm. This is what keeps her from ever reading as a paused
              image, including while she is speaking.
            */}
            <motion.div
              className="absolute inset-0"
              style={{ transformOrigin: ORIGIN.head }}
              animate={alive ? { rotate: [-0.32, 0.34, -0.32] } : { rotate: 0 }}
              transition={
                alive
                  ? { duration: 7.3, repeat: Infinity, ease: "easeInOut" }
                  : { duration: 0 }
              }
            >
              {/* Speech bob rides on top of the pose, never fighting it. */}
              <motion.div
                className="absolute inset-0"
                style={{ y: speechBobPx, transformOrigin: ORIGIN.head }}
              >
                <Layer src="/mascot/part-mouth.png" />

                <motion.div
                  className="absolute inset-0"
                  style={{ rotate: jawRotate, transformOrigin: ORIGIN.jaw }}
                >
                  <Layer src="/mascot/part-beak-lower.png" />
                </motion.div>

                <Layer src="/mascot/part-head.png" />

                <motion.div
                  className="absolute inset-0"
                  style={{ scaleY: throatScale, transformOrigin: ORIGIN.throat }}
                >
                  <Layer src="/mascot/part-throat.png" />
                </motion.div>

                <motion.div
                  className="absolute inset-0"
                  style={{
                    scaleY: lid,
                    x: gazeXPx,
                    y: gazeYPx,
                    transformOrigin: ORIGIN.eye,
                  }}
                >
                  <Layer src="/mascot/part-eye.png" />
                </motion.div>
              </motion.div>
            </motion.div>
          </motion.div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/**
 * Memoised on purpose. `/record` re-renders on every mic-level frame; without
 * this the whole rig would re-render with it.
 */
export const Lastochka = memo(LastochkaImpl);
