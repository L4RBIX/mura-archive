"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Maximize2, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePanZoom } from "@/hooks/use-pan-zoom";
import { useMuraI18n, type TranslationKey } from "@/lib/i18n";
import type { FamilyRelations } from "@/lib/mura/family-graph";
import { computeFamilyGraph, computeIslands, graphBounds } from "./layout";
import { OrganicEdge } from "./organic-edge";
import { PersonCard } from "./person-card";
import { PERSON_PANEL_WIDTH, PersonSheet, useIsDesktop } from "./person-sheet";

interface TreeCanvasProps {
  relations: FamilyRelations;
  centerId: string;
  onCenterChange: (id: string) => void;
  insetRight?: number;
}

/**
 * Sentence case for a label built partly from archive data.
 *
 * `relation_to_speaker` arrives lowercase («бабушка», «муж бабушки») while every
 * other card label comes from the dictionary capitalised, so the two sat side by
 * side as «бабушка рассказчика» next to «В браке» and read as a rendering bug.
 * Only the first character is touched: «муж бабушки» must not become
 * «Муж Бабушки».
 */
function sentenceCase(value: string): string {
  return value ? value[0].toLocaleUpperCase("ru") + value.slice(1) : value;
}

function toggle(set: Set<string>, id: string): Set<string> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * How the person at `targetId` relates to the person in the centre.
 *
 * Derived from the same canonical edges the canvas is drawn from, so the label
 * can never disagree with the line. Deliberately unmarked for gender: the
 * archive records a relationship type, not a gender, and guessing "Отец"
 * versus "Мать" from a name is the kind of small invention this product does
 * not make. Where the archive has nothing to say, the label is empty rather
 * than filled with something plausible.
 */
function relationKey(
  relations: FamilyRelations,
  centerId: string,
  targetId: string,
): TranslationKey | null {
  if (relations.parentsOf(centerId).includes(targetId)) return "relParent";
  if (relations.childrenOf(centerId).includes(targetId)) return "relChild";
  if (relations.spouseOf(centerId) === targetId) return "relSpouse";
  if (relations.siblingsOf(centerId).includes(targetId)) return "relSibling";
  for (const parent of relations.parentsOf(centerId)) {
    if (relations.parentsOf(parent).includes(targetId)) return "relGrandparent";
  }
  for (const child of relations.childrenOf(centerId)) {
    if (relations.childrenOf(child).includes(targetId)) return "relGrandchild";
  }
  return null;
}

/** How far one arrow-key press moves the canvas, in screen pixels. */
const PAN_STEP = 64;
const ZOOM_STEP = 1.2;

export function TreeCanvas({
  relations,
  centerId,
  onCenterChange,
  /** Width covered by the desktop person panel, so the fit accounts for it. */
  insetRight = 0,
}: TreeCanvasProps) {
  const { t } = useMuraI18n();
  const { containerRef, x, y, scale, fitToContent, zoomBy, panBy, handlers } = usePanZoom();
  const [expandedAncestors, setExpandedAncestors] = useState<Set<string>>(new Set());
  const [expandedDescendants, setExpandedDescendants] = useState<Set<string>>(new Set());
  const [openPersonId, setOpenPersonId] = useState<string | null>(null);
  const isDesktop = useIsDesktop();

  const { nodes, edges } = useMemo(
    () => computeFamilyGraph(relations, centerId, expandedAncestors, expandedDescendants),
    [relations, centerId, expandedAncestors, expandedDescendants],
  );

  // Islands are placed relative to the bottom of the branch in the centre, so
  // they never overlap it however many people it holds.
  const islands = useMemo(
    () => computeIslands(relations, centerId, graphBounds(nodes).maxY),
    [relations, centerId, nodes],
  );
  const allNodes = useMemo(
    () => [...nodes, ...islands.flatMap((island) => island.nodes)],
    [nodes, islands],
  );
  const bounds = useMemo(() => graphBounds(allNodes), [allNodes]);
  // Reserve the panel's width while it is open, so opening a person reframes
  // the graph into the space that is left instead of leaving it half-covered.
  const reserved = insetRight + (openPersonId && isDesktop ? PERSON_PANEL_WIDTH : 0);
  const fit = useCallback(
    () => fitToContent(bounds, { inset: { right: reserved } }),
    [bounds, fitToContent, reserved],
  );

  // Every time the focused person changes, the graph rebuilds around them —
  // fold any open branches back in and frame whatever is now drawn.
  useEffect(() => {
    setExpandedAncestors(new Set());
    setExpandedDescendants(new Set());
  }, [centerId]);

  // Frame on every change to what is drawn, and on resize. Without the resize
  // half of the point is lost: the canvas is sized by the window, so a graph
  // framed at 1024 is wrong the moment the window becomes 1920, and it was the
  // desktop case that was broken to begin with.
  useEffect(() => {
    fit();
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => fit());
    observer.observe(element);
    return () => observer.disconnect();
  }, [fit, containerRef]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    // Only when the canvas itself has focus — a card inside it handles its own
    // keys, and stealing arrows from a focused button would break Tab order.
    if (event.target !== event.currentTarget) return;
    const step = event.shiftKey ? PAN_STEP * 3 : PAN_STEP;
    switch (event.key) {
      case "ArrowLeft": event.preventDefault(); panBy(step, 0); break;
      case "ArrowRight": event.preventDefault(); panBy(-step, 0); break;
      case "ArrowUp": event.preventDefault(); panBy(0, step); break;
      case "ArrowDown": event.preventDefault(); panBy(0, -step); break;
      case "+": case "=": event.preventDefault(); zoomBy(ZOOM_STEP); break;
      case "-": case "_": event.preventDefault(); zoomBy(1 / ZOOM_STEP); break;
      case "0": event.preventDefault(); fit(); break;
      default: break;
    }
  };

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        // Focusable and labelled: the canvas was mouse-only, which made the
        // family tree — the most desktop surface in the product — unreachable
        // for anyone navigating by keyboard.
        tabIndex={0}
        role="application"
        aria-label={t("treeCanvasLabel")}
        aria-describedby="tree-canvas-help"
        onKeyDown={onKeyDown}
        className="absolute inset-0 touch-none select-none overflow-hidden [-webkit-tap-highlight-color:transparent] focus-ring"
        onDoubleClick={fit}
        {...handlers}
      >
        <motion.div
          className="absolute left-0 top-0"
          style={{ x, y, scale, transformOrigin: "0 0" }}
        >
          <svg className="absolute overflow-visible" width={1} height={1} aria-hidden>
            <AnimatePresence>
              {edges.map((edge) => (
                <OrganicEdge key={`${centerId}:${edge.id}`} edge={edge} />
              ))}
              {islands.flatMap((island) =>
                island.edges.map((edge) => (
                  <OrganicEdge key={`${centerId}:${edge.id}`} edge={edge} />
                )),
              )}
            </AnimatePresence>
          </svg>

          {/*
            The other islands of the archive, on the same canvas.

            Nothing is drawn *between* islands. A dashed "not yet confirmed"
            line would assert that a connection exists and is merely unverified,
            which is a family fact the archive has not recorded. Separation is
            shown by distance and a caption instead.
          */}
          {islands.map((island, index) => (
            <div
              key={`${centerId}:island-${index}`}
              className="pointer-events-none absolute whitespace-nowrap text-caption font-semibold uppercase tracking-[0.16em] text-muted"
              style={{ left: island.label.x, top: island.label.y }}
            >
              {t(island.connectedToCentre ? "treeFurtherLabel" : "treeIslandLabel")}
            </div>
          ))}

          {islands.flatMap((island) =>
            island.nodes.map((node) => {
              const person = relations.personById(node.id);
              if (!person) return null;
              return (
                <PersonCard
                  key={`${centerId}:island:${node.id}`}
                  node={node}
                  person={person}
                  // No relation label: these people have no recorded relation
                  // to the person in the centre, and printing one would be the
                  // invention this whole arrangement exists to avoid.
                  relationLabel=""
                  onOpen={setOpenPersonId}
                />
              );
            }),
          )}

          <AnimatePresence>
            {nodes.map((node) => {
              const person = relations.personById(node.id);
              // A node without a canonical person cannot be drawn. The graph
              // builder already excludes these; not assuming it costs nothing.
              if (!person) return null;
              const key = node.role === "center" ? null : relationKey(relations, centerId, node.id);
              return (
                <PersonCard
                  key={`${centerId}:${node.id}`}
                  node={node}
                  person={person}
                  /*
                   * Two different questions used to share this one slot, which
                   * is why a card could read «бабушка» next to one reading
                   * «Супруг(а)»: the first is who that person is to the
                   * narrator, the second is who they are to the person in the
                   * centre. Same styling, same position, different frame of
                   * reference — and the lowercase/capitalised split made it
                   * look like a rendering bug rather than a distinction.
                   *
                   * The slot now means one thing only: relation to the centre.
                   * The centre has no relation to itself, so it states its
                   * narrator-relation explicitly instead, naming the frame.
                   */
                  relationLabel={
                    node.role === "center"
                      ? person.relation_to_speaker
                        ? sentenceCase(
                            t("relToNarrator", { relation: person.relation_to_speaker }),
                          )
                        : ""
                      : key
                        ? t(key)
                        : ""
                  }
                  onOpen={setOpenPersonId}
                  onToggleAncestors={(id) => setExpandedAncestors((prev) => toggle(prev, id))}
                  onToggleDescendants={(id) => setExpandedDescendants((prev) => toggle(prev, id))}
                />
              );
            })}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Zoom lived only as a pinch gesture and one recentre button, which on a
          laptop with no touchpad pinch left no way to zoom at all. */}
      <div className="absolute bottom-5 right-5 z-10 flex flex-col gap-2">
        <CanvasButton label={t("treeZoomIn")} onClick={() => zoomBy(ZOOM_STEP)}>
          <Plus className="size-5" strokeWidth={1.8} />
        </CanvasButton>
        <CanvasButton label={t("treeZoomOut")} onClick={() => zoomBy(1 / ZOOM_STEP)}>
          <Minus className="size-5" strokeWidth={1.8} />
        </CanvasButton>
        <CanvasButton label={t("treeFit")} onClick={fit}>
          <Maximize2 className="size-5" strokeWidth={1.8} />
        </CanvasButton>
      </div>

      <p id="tree-canvas-help" className="sr-only">
        {t("treeKeyboardHelp")}
      </p>

      <PersonSheet
        relations={relations}
        personId={openPersonId}
        onClose={() => setOpenPersonId(null)}
        onCenter={onCenterChange}
      />
    </div>
  );
}

/** One canvas control. Same size and shape for all three. */
function CanvasButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex size-11 items-center justify-center rounded-full bg-raised text-ink shadow-card transition-transform duration-200 active:scale-90 focus-ring"
    >
      {children}
    </button>
  );
}
