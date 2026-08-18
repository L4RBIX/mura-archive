"use client";

import { animate, useMotionValue } from "framer-motion";
import { useCallback, useMemo, useRef } from "react";

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

  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const panOrigin = useRef<{ x: number; y: number } | null>(null);
  const pinchOrigin = useRef<number | null>(null);

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
    (e.target as Element).setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 1) {
      panOrigin.current = { x: e.clientX, y: e.clientY };
    } else if (pointers.current.size === 2) {
      const [a, b] = Array.from(pointers.current.values());
      pinchOrigin.current = Math.hypot(a.x - b.x, a.y - b.y);
    }
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!pointers.current.has(e.pointerId)) return;
      pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pointers.current.size === 2) {
        const [a, b] = Array.from(pointers.current.values());
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinchOrigin.current) {
          const factor = dist / pinchOrigin.current;
          zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, scale.get() * factor);
        }
        pinchOrigin.current = dist;
      } else if (pointers.current.size === 1 && panOrigin.current) {
        x.set(x.get() + (e.clientX - panOrigin.current.x));
        y.set(y.get() + (e.clientY - panOrigin.current.y));
        panOrigin.current = { x: e.clientX, y: e.clientY };
      }
    },
    [scale, x, y, zoomAt],
  );

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId);
    pinchOrigin.current = null;
    const remaining = Array.from(pointers.current.values())[0];
    panOrigin.current = remaining ?? null;
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
    () => ({ onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp, onWheel }),
    [onPointerDown, onPointerMove, onPointerUp, onWheel],
  );

  return { containerRef, x, y, scale, recenter, fitToContent, zoomBy, panBy, handlers };
}
