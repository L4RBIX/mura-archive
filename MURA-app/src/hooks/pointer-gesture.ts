/**
 * The canvas gesture state machine, extracted from the pan/zoom hook.
 *
 * It lives on its own because the bug it exists to prevent was a state bug, not
 * a rendering one, and the state was previously spread across three refs inside
 * a hook that cannot be driven from a test without a React renderer and
 * framer-motion's frame loop.
 *
 * ## The bug this replaces
 *
 * The tree latched onto the cursor. After clicking any person, moving the mouse
 * — no button held — panned the whole graph, so the family appeared to be glued
 * to the pointer.
 *
 * The cause was a missed release. `PersonCard` stopped `pointerup` from
 * propagating (so a tap on a card would not be read as the end of a pan), which
 * meant the canvas's own `onPointerUp` never ran, so the pointer stayed in the
 * active set with its pan origin intact. Every later `pointermove` then matched
 * "one active pointer, origin set" and panned.
 *
 * ## Why it cannot happen again
 *
 * The machine no longer trusts `pointerup` as its only way to learn that a
 * gesture ended. A pointer that reports no buttons pressed is not dragging —
 * whatever any descendant did with the release event. `buttons === 0` on a move
 * releases that pointer and yields nothing.
 *
 * That single rule is what makes the state machine immune rather than merely
 * fixed: it derives "is the user dragging" from the event that is happening now
 * instead of from bookkeeping about an event that may never arrive.
 *
 * A hovering mouse or pen reports `buttons === 0`, a touch in contact reports
 * `1`, and a touch that is not in contact does not emit `pointermove` at all,
 * so the rule reads correctly for every input type.
 */

/** The parts of a PointerEvent this machine reads. Nothing DOM-specific. */
export interface PointerSample {
  pointerId: number;
  clientX: number;
  clientY: number;
  /** Bitmask of buttons currently held. 0 means nothing is pressed. */
  buttons: number;
}

/** What a move amounts to, in screen pixels. */
export type GestureMove =
  | { kind: "pan"; dx: number; dy: number }
  | { kind: "pinch"; centerX: number; centerY: number; factor: number };

/**
 * Movement, in screen pixels, past which a gesture is a drag rather than a tap.
 *
 * A tap on a touch screen drifts by a pixel or two; a deliberate pan does not
 * stay under four. Below the threshold the canvas still pans — a two-pixel pan
 * is invisible — but the gesture is not *reported* as a drag, so the tap opens
 * the person the user aimed at.
 */
export const DRAG_THRESHOLD_PX = 4;

interface TrackedPointer {
  x: number;
  y: number;
}

export interface PointerGesture {
  down(sample: PointerSample): void;
  /** The movement this sample represents, or null if it is not a gesture. */
  move(sample: PointerSample): GestureMove | null;
  up(pointerId: number): void;
  /** Forget every pointer — used for cancellation and lost capture. */
  clear(): void;
  /** How many pointers are currently down. */
  readonly activeCount: number;
  /**
   * Whether the gesture in progress (or the one that just ended) moved far
   * enough to be a drag. The canvas reads this to decide whether the click that
   * follows should open a person or be swallowed as the end of a pan.
   */
  readonly dragged: boolean;
}

export function createPointerGesture(
  threshold: number = DRAG_THRESHOLD_PX,
): PointerGesture {
  const pointers = new Map<number, TrackedPointer>();
  let panOrigin: { x: number; y: number } | null = null;
  let pinchDistance: number | null = null;
  let travelled = 0;

  /** Drop one pointer and re-seat the pan origin on whichever remains. */
  function release(pointerId: number): void {
    pointers.delete(pointerId);
    pinchDistance = null;
    const remaining = pointers.values().next();
    panOrigin = remaining.done ? null : { x: remaining.value.x, y: remaining.value.y };
  }

  function twoPointers(): [TrackedPointer, TrackedPointer] {
    const [a, b] = Array.from(pointers.values());
    return [a, b];
  }

  return {
    down(sample) {
      pointers.set(sample.pointerId, { x: sample.clientX, y: sample.clientY });
      if (pointers.size === 1) {
        panOrigin = { x: sample.clientX, y: sample.clientY };
        // A new gesture starts as a tap until it proves otherwise.
        travelled = 0;
      } else if (pointers.size === 2) {
        const [a, b] = twoPointers();
        pinchDistance = Math.hypot(a.x - b.x, a.y - b.y);
      }
    },

    move(sample) {
      // The rule that closes the latch. Nothing is pressed, so nothing is being
      // dragged, regardless of whether this pointer's release was ever seen.
      if (sample.buttons === 0) {
        if (pointers.has(sample.pointerId)) release(sample.pointerId);
        return null;
      }

      // A move from a pointer that never went down here — the press landed
      // outside the canvas, or arrived before mount. Not our gesture.
      if (!pointers.has(sample.pointerId)) return null;

      const previous = pointers.get(sample.pointerId) as TrackedPointer;
      pointers.set(sample.pointerId, { x: sample.clientX, y: sample.clientY });

      if (pointers.size >= 2) {
        const [a, b] = twoPointers();
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        const previousDistance = pinchDistance;
        pinchDistance = distance;
        // The first move after the second finger lands has no previous
        // distance to compare against, and a zero distance would divide by it.
        if (!previousDistance || distance === 0) return null;
        travelled = Infinity; // A pinch is never a tap.
        return {
          kind: "pinch",
          centerX: (a.x + b.x) / 2,
          centerY: (a.y + b.y) / 2,
          factor: distance / previousDistance,
        };
      }

      if (!panOrigin) return null;
      const dx = sample.clientX - panOrigin.x;
      const dy = sample.clientY - panOrigin.y;
      panOrigin = { x: sample.clientX, y: sample.clientY };
      travelled += Math.hypot(dx, dy);
      // Only the previous position is used, so a pointer that moved while a
      // sibling was also down still pans by its own delta and nothing jumps.
      void previous;
      return { kind: "pan", dx, dy };
    },

    up(pointerId) {
      release(pointerId);
    },

    clear() {
      pointers.clear();
      panOrigin = null;
      pinchDistance = null;
      // Deliberately not resetting `travelled`: the click that follows a drag
      // arrives after the release, and must still be recognised as the tail of
      // that drag rather than as a fresh tap.
    },

    get activeCount() {
      return pointers.size;
    },

    get dragged() {
      return travelled > threshold;
    },
  };
}
