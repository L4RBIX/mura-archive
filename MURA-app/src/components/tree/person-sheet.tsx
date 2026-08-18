"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import type { FamilyRelations } from "@/lib/mura/family-graph";

interface PersonSheetProps {
  relations: FamilyRelations;
  personId: string | null;
  onClose: () => void;
  onCenter: (id: string) => void;
}

/**
 * A quick look at one person, from the archive.
 *
 * Everything shown is something Core recorded. There is no biography, because
 * the archive does not write one, and the previous version's summary text came
 * from a fixture. An absent field is simply absent: a profile that always
 * looks complete is a profile that is partly invented.
 *
 * The memory count is `story_count` -- stories that resolved to this canonical
 * person -- and not a client-side match on names.
 */
export function PersonSheet({ relations, personId, onClose, onCenter }: PersonSheetProps) {
  const { t } = useMuraI18n();
  const person = personId ? relations.personById(personId) : undefined;

  return (
    <AnimatePresence>
      {person && (
        <>
          <motion.div
            key="backdrop"
            className="fixed inset-0 z-40 bg-ink/25"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
          />
          <motion.div
            key="sheet"
            role="dialog"
            aria-modal="true"
            aria-label={person.display_name}
            className="fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-[460px] rounded-t-[32px] bg-raised px-6 pb-[max(env(safe-area-inset-bottom),24px)] pt-3 shadow-card"
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

            <div className="mt-5 flex items-start gap-4">
              <PersonAvatar
                personId={person.person_id}
                displayName={person.display_name}
                size={64}
              />
              <div className="min-w-0 flex-1 pt-1">
                <h2 className="truncate text-title font-bold leading-tight tracking-[-0.02em]">
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

            <div className="mt-6 flex gap-3">
              <Button asChild variant="soft" size="lg" className="flex-1" onClick={onClose}>
                <Link href={`/person/${encodeURIComponent(person.person_id)}`}>
                  {t("openProfile")}
                </Link>
              </Button>
              <Button
                size="lg"
                className="flex-1"
                onClick={() => {
                  onCenter(person.person_id);
                  onClose();
                }}
              >
                {t("centerHere")}
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
