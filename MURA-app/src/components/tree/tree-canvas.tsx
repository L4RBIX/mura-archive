"use client";

import { AnimatePresence, motion } from "framer-motion";
import { LocateFixed } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { usePanZoom } from "@/hooks/use-pan-zoom";
import { useMuraI18n, type TranslationKey } from "@/lib/i18n";
import type { FamilyRelations } from "@/lib/mura/family-graph";
import { computeFamilyGraph } from "./layout";
import { OrganicEdge } from "./organic-edge";
import { PersonCard } from "./person-card";
import { PersonSheet } from "./person-sheet";

interface TreeCanvasProps {
  relations: FamilyRelations;
  centerId: string;
  onCenterChange: (id: string) => void;
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

export function TreeCanvas({ relations, centerId, onCenterChange }: TreeCanvasProps) {
  const { t } = useMuraI18n();
  const { containerRef, x, y, scale, recenter, handlers } = usePanZoom();
  const [expandedAncestors, setExpandedAncestors] = useState<Set<string>>(new Set());
  const [expandedDescendants, setExpandedDescendants] = useState<Set<string>>(new Set());
  const [openPersonId, setOpenPersonId] = useState<string | null>(null);

  // Every time the focused person changes, the graph rebuilds around them —
  // fold any open branches back in and glide the viewport home.
  useEffect(() => {
    setExpandedAncestors(new Set());
    setExpandedDescendants(new Set());
    recenter(0, 0, 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centerId]);

  const { nodes, edges } = useMemo(
    () => computeFamilyGraph(relations, centerId, expandedAncestors, expandedDescendants),
    [relations, centerId, expandedAncestors, expandedDescendants],
  );

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        className="absolute inset-0 touch-none select-none overflow-hidden [-webkit-tap-highlight-color:transparent]"
        onDoubleClick={() => recenter(0, 0, 1)}
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
            </AnimatePresence>
          </svg>

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

      <button
        type="button"
        onClick={() => recenter(0, 0, 1)}
        aria-label={t("centerTree")}
        className="absolute bottom-5 right-5 z-10 flex size-12 items-center justify-center rounded-full bg-raised text-ink shadow-card transition-transform duration-200 active:scale-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink/40"
      >
        <LocateFixed className="size-5" strokeWidth={1.8} />
      </button>

      <PersonSheet
        relations={relations}
        personId={openPersonId}
        onClose={() => setOpenPersonId(null)}
        onCenter={onCenterChange}
      />
    </div>
  );
}
