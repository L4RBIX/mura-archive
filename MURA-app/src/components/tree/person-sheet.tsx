"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import type { ArchivePerson } from "@/lib/mura/archive-api";
import type { FamilyRelations } from "@/lib/mura/family-graph";

/** Width of the desktop panel. The canvas reserves the same number. */
export const PERSON_PANEL_WIDTH = 340;

interface PersonSheetProps {
  relations: FamilyRelations;
  personId: string | null;
  onClose: () => void;
  onCenter: (id: string) => void;
}

/** True from `lg`, tracked live so a resize switches presentation. */
export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 64rem)");
    const sync = () => setIsDesktop(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  return isDesktop;
}

/**
 * A quick look at one person, from the archive.
 *
 * Everything shown is something Core recorded. There is no biography, because
 * the archive does not write one. An absent field is simply absent: a profile
 * that always looks complete is a profile that is partly invented. The memory
 * count is `story_count` — stories that resolved to this canonical person — and
 * not a client-side match on names.
 *
 * Two presentations of one component, because the right answer differs by
 * device rather than by taste. On a phone it is a bottom sheet you dismiss by
 * swiping down, and it is genuinely modal: it covers the graph. On a desktop
 * that same sheet was a phone control stranded at the bottom of a 1440px
 * window, dismissed by a gesture a mouse cannot make. There it becomes a side
 * panel that sits beside the graph rather than over it — so it is deliberately
 * *not* `aria-modal`, because the graph behind it stays usable, and claiming
 * modality would lie to a screen reader about what is reachable.
 */
export function PersonSheet({ relations, personId, onClose, onCenter }: PersonSheetProps) {
  const { t } = useMuraI18n();
  const isDesktop = useIsDesktop();
  const person = personId ? relations.personById(personId) : undefined;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (person) {
      opener.current = document.activeElement as HTMLElement | null;
      headingRef.current?.focus();
    } else {
      opener.current?.focus?.();
    }
  }, [person]);

  useEffect(() => {
    if (!person) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [person, onClose]);

  return (
    <AnimatePresence>
      {person && (
        <>
          {/* A backdrop belongs to the modal case only. On desktop the graph
              behind the panel is still there to be used. */}
          {!isDesktop && (
            <motion.div
              key="backdrop"
              className="fixed inset-0 z-40 bg-ink/25"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              onClick={onClose}
            />
          )}

          {isDesktop ? (
            <motion.aside
              key="panel"
              role="dialog"
              aria-label={person.display_name}
              className="absolute inset-y-0 right-0 z-50 flex flex-col overflow-y-auto border-l border-ink/[0.08] bg-raised px-6 pb-6 pt-5 shadow-card"
              style={{ width: PERSON_PANEL_WIDTH }}
              initial={{ x: PERSON_PANEL_WIDTH, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: PERSON_PANEL_WIDTH, opacity: 0 }}
              transition={{ type: "spring", stiffness: 320, damping: 34 }}
            >
              <button
                type="button"
                onClick={onClose}
                aria-label={t("closePanel")}
                className="absolute right-4 top-4 flex size-9 items-center justify-center rounded-full text-muted hover:text-ink focus-ring"
              >
                <X className="size-4" strokeWidth={2} />
              </button>
              <PersonBody
                person={person}
                headingRef={headingRef}
                onClose={onClose}
                onCenter={onCenter}
                stacked
              />
            </motion.aside>
          ) : (
            <motion.div
              key="sheet"
              role="dialog"
              aria-modal="true"
              aria-label={person.display_name}
              className="fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-[460px] rounded-t-panel bg-raised px-6 pb-[max(env(safe-area-inset-bottom),24px)] pt-3 shadow-card"
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 34 }}
              drag="y"
              dragConstraints={{ top: 0, bottom: 0 }}
              dragElastic={{ top: 0, bottom: 0.5 }}
              onDragEnd={(_, info) => {
                if (info.offset.y > 90 || info.velocity.y > 600) onClose();
              }}
            >
              <div aria-hidden className="mx-auto h-1.5 w-10 rounded-full bg-ink/15" />
              <PersonBody
                person={person}
                headingRef={headingRef}
                onClose={onClose}
                onCenter={onCenter}
              />
            </motion.div>
          )}
        </>
      )}
    </AnimatePresence>
  );
}

function PersonBody({
  person,
  headingRef,
  onClose,
  onCenter,
  stacked = false,
}: {
  person: ArchivePerson;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  onClose: () => void;
  onCenter: (id: string) => void;
  /** The narrow panel puts its two actions one above the other. */
  stacked?: boolean;
}) {
  const { t } = useMuraI18n();

  return (
    <>
      <div className="mt-5 flex items-start gap-4">
        <PersonAvatar
          personId={person.person_id}
          displayName={person.display_name}
          size={64}
        />
        <div className="min-w-0 flex-1 pt-1">
          {/* Focused on open, so a keyboard user lands on the person's name
              rather than somewhere arbitrary inside the panel. */}
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="text-balance text-title font-bold leading-tight tracking-[-0.02em] outline-none"
          >
            {person.display_name}
          </h2>
          {person.relation_to_speaker && (
            <p className="mt-0.5 text-meta text-muted">{person.relation_to_speaker}</p>
          )}
        </div>
      </div>

      {person.aliases.length > 0 && (
        <p className="mt-4 text-meta leading-relaxed text-muted">
          {person.aliases.join(" · ")}
        </p>
      )}

      <p className="mt-4 text-meta font-medium text-muted">
        {person.story_count === 0
          ? t("noMemoriesYet")
          : person.story_count === 1
            ? t("oneMemoryRecorded")
            : t("memoriesRecorded", { count: person.story_count })}
      </p>

      <div className={`mt-6 flex gap-3 ${stacked ? "flex-col" : ""}`}>
        <Button
          asChild
          variant="soft"
          size="lg"
          className={stacked ? "" : "flex-1"}
          onClick={onClose}
        >
          <Link href={`/person/${encodeURIComponent(person.person_id)}`}>
            {t("openProfile")}
          </Link>
        </Button>
        <Button
          size="lg"
          className={stacked ? "" : "flex-1"}
          onClick={() => {
            onCenter(person.person_id);
            onClose();
          }}
        >
          {t("centerHere")}
        </Button>
      </div>
    </>
  );
}
