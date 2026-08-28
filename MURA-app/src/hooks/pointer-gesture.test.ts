import { describe, expect, it } from "vitest";
import { createPointerGesture, DRAG_THRESHOLD_PX } from "@/hooks/pointer-gesture";

/** A mouse with the primary button held. */
const held = (id: number, x: number, y: number) => ({
  pointerId: id,
  clientX: x,
  clientY: y,
  buttons: 1,
});

/** A mouse merely moving across the canvas, nothing pressed. */
const hover = (id: number, x: number, y: number) => ({
  pointerId: id,
  clientX: x,
  clientY: y,
  buttons: 0,
});

describe("the cursor-latch regression", () => {
  /**
   * The reported bug, reproduced exactly.
   *
   * `PersonCard` stops `pointerup` from propagating, so the canvas never sees
   * the release. Before the fix the pointer stayed in the active set with its
   * pan origin intact, and every subsequent hover panned the graph — the tree
   * followed the cursor with no button held.
   */
  it("does not pan on hover after a release the canvas never saw", () => {
    const gesture = createPointerGesture();

    // Press on a person card, and release it — the card swallows the pointerup,
    // so `up()` is deliberately never called here.
    gesture.down(held(1, 500, 300));

    // The user now moves the mouse away with nothing pressed.
    expect(gesture.move(hover(1, 520, 300))).toBeNull();
    expect(gesture.move(hover(1, 640, 380))).toBeNull();
    expect(gesture.move(hover(1, 900, 500))).toBeNull();

    // And the machine has forgotten the pointer rather than holding it forever.
    expect(gesture.activeCount).toBe(0);
  });

  it("recovers for the next real drag instead of staying stuck", () => {
    const gesture = createPointerGesture();

    gesture.down(held(1, 500, 300));
    gesture.move(hover(1, 700, 300)); // missed release, latch cleared

    // A genuine press-and-drag afterwards still works normally.
    gesture.down(held(1, 700, 300));
    expect(gesture.move(held(1, 740, 330))).toEqual({ kind: "pan", dx: 40, dy: 30 });
  });

  it("ignores a move from a pointer that never pressed on the canvas", () => {
    const gesture = createPointerGesture();
    expect(gesture.move(held(7, 100, 100))).toBeNull();
  });
});

describe("panning", () => {
  it("reports the delta since the previous position, not since the press", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 100, 100));

    expect(gesture.move(held(1, 110, 105))).toEqual({ kind: "pan", dx: 10, dy: 5 });
    // Relative, so the canvas can add each delta without accumulating drift.
    expect(gesture.move(held(1, 130, 105))).toEqual({ kind: "pan", dx: 20, dy: 0 });
  });

  it("pans while the button stays held", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    expect(gesture.move(held(1, -40, 20))).toEqual({ kind: "pan", dx: -40, dy: 20 });
  });

  it("stops panning once the pointer is released", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    gesture.move(held(1, 10, 10));
    gesture.up(1);

    expect(gesture.activeCount).toBe(0);
    expect(gesture.move(held(1, 200, 200))).toBeNull();
  });
});

describe("tap versus drag", () => {
  it("treats a press and release that barely moved as a tap", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 300, 300));
    gesture.move(held(1, 301, 301));
    gesture.up(1);

    // So the click that follows opens the person the user aimed at.
    expect(gesture.dragged).toBe(false);
  });

  it("treats a press that travelled past the threshold as a drag", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 300, 300));
    gesture.move(held(1, 300 + DRAG_THRESHOLD_PX + 6, 300));
    gesture.up(1);

    // So the click that follows is swallowed instead of opening a person the
    // user only dragged across.
    expect(gesture.dragged).toBe(true);
  });

  it("accumulates travel, so a slow drag is still a drag", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    for (let step = 1; step <= 8; step += 1) gesture.move(held(1, step, 0));
    expect(gesture.dragged).toBe(true);
  });

  it("starts each new press as a tap again", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    gesture.move(held(1, 80, 0));
    gesture.up(1);
    expect(gesture.dragged).toBe(true);

    gesture.down(held(1, 400, 400));
    expect(gesture.dragged).toBe(false);
  });
});

describe("pinch", () => {
  it("reports the scale factor between two fingers", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    gesture.down(held(2, 100, 0));

    // First move establishes nothing to compare against yet.
    expect(gesture.move(held(2, 200, 0))).toEqual({
      kind: "pinch",
      centerX: 100,
      centerY: 0,
      factor: 2,
    });
  });

  it("reports the midpoint so the zoom anchors between the fingers", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 100, 100));
    gesture.down(held(2, 300, 300));
    const move = gesture.move(held(2, 400, 400));

    expect(move).toMatchObject({ kind: "pinch", centerX: 250, centerY: 250 });
  });

  it("never divides by a zero distance", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 50, 50));
    gesture.down(held(2, 50, 50)); // both fingers on the same point
    expect(gesture.move(held(2, 50, 50))).toBeNull();
  });

  it("is never mistaken for a tap", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    gesture.down(held(2, 100, 0));
    gesture.move(held(2, 140, 0));
    expect(gesture.dragged).toBe(true);
  });

  it("falls back to panning with the finger that stays down", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    gesture.down(held(2, 100, 0));
    gesture.move(held(2, 200, 0));

    // Lifting one finger must not make the remaining one jump: the pan origin
    // re-seats on where that finger actually is.
    gesture.up(2);
    expect(gesture.move(held(1, 10, 0))).toEqual({ kind: "pan", dx: 10, dy: 0 });
  });
});

describe("cancellation", () => {
  it("forgets every pointer when the gesture is cancelled", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    gesture.down(held(2, 50, 0));
    gesture.clear();

    expect(gesture.activeCount).toBe(0);
    expect(gesture.move(held(1, 100, 100))).toBeNull();
  });

  it("keeps the drag verdict across the release, for the click that follows", () => {
    const gesture = createPointerGesture();
    gesture.down(held(1, 0, 0));
    gesture.move(held(1, 90, 0));
    // The click arrives after pointerup and lost capture, and must still know
    // it is the tail of a drag rather than a fresh tap on a person.
    gesture.clear();
    expect(gesture.dragged).toBe(true);
  });
});
