"use client";

import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import type { ArchivePerson } from "@/lib/mura/archive-api";
import { cn } from "@/lib/utils";
import { CARD_HEIGHT, CARD_WIDTH, distanceDelay, type FamilyGraphNode } from "./layout";

interface PersonCardProps {
  node: FamilyGraphNode;
  person: ArchivePerson;
  relationLabel: string;
  onOpen: (id: string) => void;
  onToggleAncestors?: (id: string) => void;
  onToggleDescendants?: (id: string) => void;
}

/**
 * One person on the canvas.
 *
 * The memory count is `story_count` from the archive -- how many stories
 * resolved to this canonical person -- rather than a client-side tally of
 * stories whose text happens to mention a matching name.
 */
export function PersonCard({
  node,
  person,
  relationLabel,
  onOpen,
  onToggleAncestors,
  onToggleDescendants,
}: PersonCardProps) {
  const { t } = useMuraI18n();
  const { role, x, y } = node;
  const isCenter = role === "center";
  const memoryCount = person.story_count;

  return (
    <motion.div
      layout
      className="absolute"
      style={{
        left: x - CARD_WIDTH / 2,
        top: y - CARD_HEIGHT / 2,
        width: CARD_WIDTH,
        height: CARD_HEIGHT,
      }}
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.85, transition: { duration: 0.18 } }}
      transition={{
        type: "spring",
        stiffness: 260,
        damping: 24,
        delay: distanceDelay(x, y),
      }}
    >
      <button
        type="button"
        onClick={() => onOpen(person.person_id)}
        className={cn(
          "flex size-full flex-col justify-between rounded-panel px-4 py-3.5 text-left shadow-soft transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] active:scale-[0.96] focus-ring",
          isCenter ? "bg-ink text-raised" : "bg-raised text-ink",
        )}
      >
        <span className="flex items-center gap-2.5">
          <span className="relative shrink-0">
            <PersonAvatar personId={person.person_id} displayName={person.display_name} size={40} />
            {memoryCount > 0 && (
              <span
                aria-hidden
                className="absolute -right-0.5 -top-0.5 size-[9px] animate-glow rounded-full bg-peach"
              />
            )}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-body font-semibold leading-tight">
              {person.display_name}
            </span>
            {relationLabel && (
              <span
                className={cn(
                  "block truncate text-caption",
                  isCenter ? "text-raised/55" : "text-muted",
                )}
              >
                {relationLabel}
              </span>
            )}
          </span>
        </span>
        <span className={cn("text-caption", isCenter ? "text-raised/45" : "text-muted/80")}>
          {memoryCount === 0
            ? t("noMemoriesYet")
            : memoryCount === 1
              ? t("oneMemory")
              : t("memoriesCount", { count: memoryCount })}
        </span>
      </button>

      {node.canExpandAncestors && (
        <ExpandTab
          side="left"
          expanded={!!node.ancestorsExpanded}
          label={t(node.ancestorsExpanded ? "hideParents" : "showParents", {
            name: person.display_name,
          })}
          onClick={() => onToggleAncestors?.(person.person_id)}
        />
      )}
      {node.canExpandDescendants && (
        <ExpandTab
          side="right"
          expanded={!!node.descendantsExpanded}
          label={t(node.descendantsExpanded ? "hideChildren" : "showChildren", {
            name: person.display_name,
          })}
          onClick={() => onToggleDescendants?.(person.person_id)}
        />
      )}
    </motion.div>
  );
}

function ExpandTab({
  side,
  expanded,
  label,
  onClick,
}: {
  side: "left" | "right";
  expanded: boolean;
  label: string;
  onClick: () => void;
}) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={expanded}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        "absolute top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-full shadow-soft transition-[transform,background-color] duration-200 active:scale-90",
        side === "left" ? "-left-4" : "-right-4",
        expanded ? "bg-peach text-ink" : "bg-paper text-ink/70",
      )}
    >
      <Icon className="size-4" strokeWidth={2.25} />
    </button>
  );
}
