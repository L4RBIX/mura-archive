"use client";

import { animate, useMotionValue } from "framer-motion";
import { useCallback, useMemo, useRef } from "react";
import { createPointerGesture } from "@/hooks/pointer-gesture";

/**
 * 0.55 was chosen for a phone showing a handful of cards. Measured against a
 * synthetic 40-person family, the graph is roughly 1300x5400 world units, which
 * needs about 0.16 to fit a laptop canvas — at 0.55 a large family simply could
 * not be seen whole, and the only way to find anyone was to pan blind.
 *
 * 0.15 is the floor. Cards are unreadable there, deliberately: that zoom is for
 * seeing the shape of a family and choosing where to go, not for reading names.
 */
const MIN_SCALE = 0.15;
const MAX_SCALE = 1.5;
const SPRING = { type: "spring" as const, stiffness: 190, damping: 28 };

const clampScale = (s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

/** Bounds of the drawn graph in world units. */
export interface GraphBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * The transform that frames `bounds` inside a viewport.
 *
 * Pure, and separate from the hook, because it is the one piece of arithmetic
 * here that is worth pinning: it decides whether a family is visible at all.
 * Verifying it through the component would mean driving framer's frame loop,
 * which is exactly the part a test cannot rely on.
 */
export function computeFit(
  bounds: GraphBounds,
  viewport: { width: number; height: number },
  options: { padding?: number; insetRight?: number } = {},
): { x: number; y: number; scale: number } {
  const padding = options.padding ?? 64;
  const insetRight = options.insetRight ?? 0;

  const available = {
    width: Math.max(1, viewport.width - insetRight - padding * 2),
    height: Math.max(1, viewport.height - padding * 2),
  };
  const content = {
    width: Math.max(1, bounds.maxX - bounds.minX),
    height: Math.max(1, bounds.maxY - bounds.minY),
  };

  // Never zoom *in* past 1 to fill the canvas: a lone person blown up to 150%
  // looks like a bug, not like a family tree.
  const scale = clampScale(
    Math.min(1, available.width / content.width, available.height / content.height),
  );

  const centreX = (bounds.minX + bounds.maxX) / 2;
  const centreY = (bounds.minY + bounds.maxY) / 2;
  return {
    x: (viewport.width - insetRight) / 2 - centreX * scale,
    y: viewport.height / 2 - centreY * scale,
    scale,
  };
}

/**
 * A minimal hand-rolled pan/zoom canvas: one-finger drag to pan, two-finger
 * pinch or wheel to zoom (both anchored under the pointer), and a spring
 * `recenter` to glide to any point in world space. Built on Pointer Events so
 * touch, mouse and trackpad all go through the same code path.
 */
export function usePanZoom() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const scale = useMotionValue(1);

  /*
   * All gesture state lives in one machine rather than three refs, because the
   * bug it replaces was a disagreement between those refs: a release the canvas
   * never saw left the pointer set populated and the pan origin set, so hover
   * panned the graph. See `pointer-gesture.ts`.
   */
  const gesture = useRef(createPointerGesture());

  const zoomAt = useCallback(
    (clientX: number, clientY: number, nextScale: number) => {
      const rect = containerRef.current?.getBoundingClientRect();
      const clamped = clampScale(nextScale);
      if (!rect) {
        scale.set(clamped);
        return;
      }
      const localX = clientX - rect.left;
      const localY = clientY - rect.top;
      const ratio = clamped / scale.get();
      x.set(localX - (localX - x.get()) * ratio);
      y.set(localY - (localY - y.get()) * ratio);
      scale.set(clamped);
    },
    [scale, x, y],
  );

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    /*
     * Deliberately no `setPointerCapture` here.
     *
     * The old code captured on `e.target` — whatever sat deepest under the
     * pointer, usually a person card. That is wrong twice over. The card can
     * unmount mid-gesture (opening a person re-lays the tree) and a captured
     * element that leaves the DOM never delivers its `pointerup`, which is half
     * of how the canvas came to latch onto the cursor.
     *
     * Capturing on press at all is the other half: capture retargets the
     * `click` a tap produces, so the card the user actually tapped may never
     * receive it and the person never opens. Capture is taken in `move`, once
     * the gesture has proved it is a drag — a tap therefore never involves
     * capture, and a drag gets the out-of-bounds tracking it needs.
     */
    gesture.current.down(e);
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const move = gesture.current.move(e);
      if (!move) return;

      // Past the threshold this is a drag, so follow the pointer even when it
      // leaves the canvas. Without this a pan dies at the window edge.
      if (gesture.current.dragged && !e.currentTarget.hasPointerCapture?.(e.pointerId)) {
        e.currentTarget.setPointerCapture?.(e.pointerId);
      }

      if (move.kind === "pinch") {
        zoomAt(move.centerX, move.centerY, scale.get() * move.factor);
        return;
      }
      x.set(x.get() + move.dx);
      y.set(y.get() + move.dy);
    },
    [scale, x, y, zoomAt],
  );

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    gesture.current.up(e.pointerId);
  }, []);

  /**
   * Capture was taken away — the element left the DOM, or the browser handed
   * the pointer to a system gesture. Either way the drag is over, and treating
   * it as still running is precisely the latch this hook had.
   */
  const onLostPointerCapture = useCallback(() => {
    gesture.current.clear();
  }, []);

  /**
   * Swallow the click that ends a drag.
   *
   * Panning that starts on a person card still fires `click` on release, which
   * would open whoever the drag happened to begin on. Run in the capture phase
   * so the card's own handler never sees it.
   */
  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (!gesture.current.dragged) return;
    e.stopPropagation();
    e.preventDefault();
  }, []);

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const factor = Math.exp(-e.deltaY * 0.001);
      zoomAt(e.clientX, e.clientY, scale.get() * factor);
    },
    [scale, zoomAt],
  );

  /** Move a motion value, instantly when the user asked for less motion. */
  const glide = useCallback((value: ReturnType<typeof useMotionValue<number>>, to: number) => {
    if (prefersReducedMotion()) value.set(to);
    else animate(value, to, SPRING);
  }, []);

  /** Glide the given world-space point to the center of the viewport. */
  const recenter = useCallback(
    (worldX = 0, worldY = 0, targetScale = 1) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      glide(x, rect.width / 2 - worldX * targetScale);
      glide(y, rect.height / 2 - worldY * targetScale);
      glide(scale, targetScale);
    },
    [glide, scale, x, y],
  );

  /**
   * Frame the whole graph.
   *
   * The canvas only ever had `recenter(0, 0, 1)`, which puts the centre person
   * at the middle of the viewport at 100% and ignores everyone else — so a
   * two-person family filled about 5% of a laptop canvas, and a large one ran
   * off every edge with no way to see its shape.
   *
   * `inset` reserves space that is part of the canvas but covered by something
   * else, which is how the desktop person panel avoids making the graph jump.
   */
  const fitToContent = useCallback(
    (
      bounds: GraphBounds,
      options: { padding?: number; inset?: { right?: number } } = {},
    ) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const next = computeFit(
        bounds,
        { width: rect.width, height: rect.height },
        { padding: options.padding, insetRight: options.inset?.right },
      );
      glide(x, next.x);
      glide(y, next.y);
      glide(scale, next.scale);
    },
    [glide, scale, x, y],
  );

  /** Zoom about the middle of the canvas — what the +/- buttons and keys use. */
  const zoomBy = useCallback(
    (factor: number) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, scale.get() * factor);
    },
    [scale, zoomAt],
  );

  /** Pan by a screen-space delta — what the arrow keys use. */
  const panBy = useCallback(
    (dx: number, dy: number) => {
      x.set(x.get() + dx);
      y.set(y.get() + dy);
    },
    [x, y],
  );

  const handlers = useMemo(
    () => ({
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
      onLostPointerCapture,
      onClickCapture,
      onWheel,
    }),
    [onPointerDown, onPointerMove, onPointerUp, onLostPointerCapture, onClickCapture, onWheel],
  );

  return { containerRef, x, y, scale, recenter, fitToContent, zoomBy, panBy, handlers };
}
