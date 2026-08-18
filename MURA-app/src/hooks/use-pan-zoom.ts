"use client";

import { animate, useMotionValue } from "framer-motion";
import { useCallback, useMemo, useRef } from "react";

const MIN_SCALE = 0.55;
const MAX_SCALE = 1.5;
const SPRING = { type: "spring" as const, stiffness: 190, damping: 28 };

const clampScale = (s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

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

  /** Glide the given world-space point to the center of the viewport. */
  const recenter = useCallback(
    (worldX = 0, worldY = 0, targetScale = 1) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      animate(x, rect.width / 2 - worldX * targetScale, SPRING);
      animate(y, rect.height / 2 - worldY * targetScale, SPRING);
      animate(scale, targetScale, SPRING);
    },
    [scale, x, y],
  );

  const handlers = useMemo(
    () => ({ onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp, onWheel }),
    [onPointerDown, onPointerMove, onPointerUp, onWheel],
  );

  return { containerRef, x, y, scale, recenter, handlers };
}
