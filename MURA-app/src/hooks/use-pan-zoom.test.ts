import { describe, expect, it } from "vitest";
import { computeFit } from "@/hooks/use-pan-zoom";

const VIEWPORT = { width: 1100, height: 700 };

/** Where the centre of `bounds` lands on screen under a fit. */
const centreOnScreen = (
  bounds: Parameters<typeof computeFit>[0],
  viewport: { width: number; height: number },
  options?: Parameters<typeof computeFit>[2],
) => {
  const fit = computeFit(bounds, viewport, options);
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  return { x: fit.x + cx * fit.scale, y: fit.y + cy * fit.scale, scale: fit.scale };
};

describe("computeFit", () => {
  it("centres the graph in the viewport", () => {
    const placed = centreOnScreen(
      { minX: -400, maxX: 400, minY: -200, maxY: 200 },
      VIEWPORT,
    );
    expect(placed.x).toBeCloseTo(VIEWPORT.width / 2, 6);
    expect(placed.y).toBeCloseTo(VIEWPORT.height / 2, 6);
  });

  it("centres a graph that is not symmetric about the origin", () => {
    // Islands hang below the branch, so the drawn graph is usually lopsided.
    const placed = centreOnScreen(
      { minX: -100, maxX: 900, minY: 0, maxY: 1800 },
      VIEWPORT,
    );
    expect(placed.x).toBeCloseTo(VIEWPORT.width / 2, 6);
    expect(placed.y).toBeCloseTo(VIEWPORT.height / 2, 6);
  });

  it("never magnifies a small family past 1", () => {
    // Two people used to sit at scale 1 filling ~5% of the canvas. Fitting must
    // not overcorrect into blowing them up to 150%.
    const fit = computeFit({ minX: -180, maxX: 180, minY: -54, maxY: 54 }, VIEWPORT);
    expect(fit.scale).toBe(1);
  });

  it("shrinks a large family enough to see its shape", () => {
    // Roughly the measured 40-person case: one parent, 39 children stacked.
    const fit = computeFit({ minX: -140, maxX: 1200, minY: -2700, maxY: 2700 }, VIEWPORT);
    expect(fit.scale).toBeGreaterThan(0.1);
    expect(fit.scale).toBeLessThan(0.2);
  });

  it("stops at the floor instead of scaling to nothing", () => {
    const fit = computeFit({ minX: -50000, maxX: 50000, minY: -50000, maxY: 50000 }, VIEWPORT);
    expect(fit.scale).toBe(0.15);
  });

  it("keeps the graph inside the viewport, padding included", () => {
    const bounds = { minX: -400, maxX: 400, minY: -900, maxY: 900 };
    const fit = computeFit(bounds, VIEWPORT, { padding: 64 });
    const left = fit.x + bounds.minX * fit.scale;
    const right = fit.x + bounds.maxX * fit.scale;
    const top = fit.y + bounds.minY * fit.scale;
    const bottom = fit.y + bounds.maxY * fit.scale;
    expect(left).toBeGreaterThanOrEqual(64 - 0.001);
    expect(right).toBeLessThanOrEqual(VIEWPORT.width - 64 + 0.001);
    expect(top).toBeGreaterThanOrEqual(64 - 0.001);
    expect(bottom).toBeLessThanOrEqual(VIEWPORT.height - 64 + 0.001);
  });

  it("centres in the space left by the person panel, not the whole canvas", () => {
    // Otherwise opening a person leaves the graph half under the panel.
    const bounds = { minX: -400, maxX: 400, minY: -200, maxY: 200 };
    const placed = centreOnScreen(bounds, VIEWPORT, { insetRight: 340 });
    expect(placed.x).toBeCloseTo((VIEWPORT.width - 340) / 2, 6);
  });

  it("survives a zero-sized graph without dividing by zero", () => {
    const fit = computeFit({ minX: 0, maxX: 0, minY: 0, maxY: 0 }, VIEWPORT);
    expect(Number.isFinite(fit.x)).toBe(true);
    expect(Number.isFinite(fit.y)).toBe(true);
    expect(fit.scale).toBe(1);
  });

  it("survives a zero-sized viewport", () => {
    const fit = computeFit({ minX: -100, maxX: 100, minY: -100, maxY: 100 }, { width: 0, height: 0 });
    expect(Number.isFinite(fit.scale)).toBe(true);
    expect(fit.scale).toBe(0.15);
  });
});
