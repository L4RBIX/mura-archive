import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

function source(relativePath: string) {
  return readFileSync(resolve(process.cwd(), relativePath), "utf8");
}

/**
 * The same file with comments removed.
 *
 * These assertions are about what the code does, and this codebase explains its
 * reasoning at length — including naming the very calls being forbidden. Without
 * this, documenting why a call is wrong would fail the test that forbids it.
 */
function code(relativePath: string) {
  return source(relativePath)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

/**
 * The canvas latched onto the cursor because a child swallowed `pointerup`.
 *
 * The state machine is now immune to that on its own (see
 * `pointer-gesture.test.ts`), so these are not the primary defence — they stop
 * the *cause* from creeping back in, because a card that swallows releases will
 * keep working here and then break some future gesture that does trust them.
 */
describe("nothing on the canvas swallows a pointer release", () => {
  it("keeps pointerup propagating out of the person card", () => {
    const card = code("src/components/tree/person-card.tsx");
    expect(card).not.toMatch(/onPointerUp/);
    expect(card).not.toMatch(/onPointerCancel/);
  });

  it("keeps pointerup propagating out of the organic edge and person sheet", () => {
    expect(code("src/components/tree/organic-edge.tsx")).not.toMatch(/onPointerUp/);
    expect(code("src/components/tree/person-sheet.tsx")).not.toMatch(/onPointerUp/);
  });
});

describe("the canvas does not capture the pointer on press", () => {
  const hook = code("src/hooks/use-pan-zoom.ts");

  it("never captures on the press target", () => {
    // `e.target` is a person card; capturing there ties the gesture to an
    // element the graph unmounts mid-drag.
    expect(hook).not.toMatch(/\(e\.target as Element\)\.setPointerCapture/);
  });

  it("takes capture only from the move handler, once a drag is established", () => {
    const [, downBody = ""] = hook.split("const onPointerDown");
    const downHandler = downBody.slice(0, downBody.indexOf("const onPointerMove"));
    // Capturing on press retargets the click a tap produces, so the card the
    // user tapped may never receive it and the person never opens.
    expect(downHandler).not.toMatch(/setPointerCapture/);
    expect(hook).toMatch(/dragged && !e\.currentTarget\.hasPointerCapture/);
  });

  it("treats lost capture as the end of the gesture", () => {
    expect(hook).toMatch(/onLostPointerCapture/);
  });
});

describe("the gesture machine owns the canvas state", () => {
  const hook = code("src/hooks/use-pan-zoom.ts");

  it("keeps no parallel pointer bookkeeping in the hook", () => {
    // Three refs that could disagree is what the bug was made of.
    expect(hook).not.toMatch(/panOrigin\.current/);
    expect(hook).not.toMatch(/pinchOrigin\.current/);
    expect(hook).not.toMatch(/pointers\.current/);
  });
});
