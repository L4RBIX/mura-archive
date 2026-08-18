"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useCallback, useMemo, type ReactNode } from "react";
import { ArchiveState } from "@/components/archive/archive-state";
import { FamilyGate } from "@/components/family/family-gate";
import { ScreenHeader } from "@/components/layout/screen-header";
import { PageContainer } from "@/components/shell/page-container";
import { StoryLink } from "@/components/story/story-link";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import {
  fetchArchivePeople,
  fetchArchiveProfile,
  fetchArchiveRelationships,
  fetchArchiveStories,
  type ArchivePerson,
  type ArchiveProfile,
  type ArchiveRelationship,
  type ArchiveStorySummary,
} from "@/lib/mura/archive-api";
import { CoreRequestError } from "@/lib/mura/core-api";
import { buildFamilyRelations } from "@/lib/mura/family-graph";
import { useArchiveResource } from "@/lib/mura/use-archive";

interface PersonBundle {
  profile: ArchiveProfile | null;
  people: ArchivePerson[];
  relationships: ArchiveRelationship[];
  stories: ArchiveStorySummary[];
}

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.23, 1, 0.32, 1] as const } },
};

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-3 text-caption font-semibold uppercase tracking-[0.18em] text-muted">
      {children}
    </h2>
  );
}

/**
 * A memory profile for one canonical person.
 *
 * Addressed by `person_id` throughout. The previous version matched saved
 * recordings against a fixture person's *name*, and a name is not identity:
 * two relatives share one, one relative has several across Russian and Kazakh
 * spelling, and a string comparison silently merges people who are not the
 * same person. Stories appear here because the archive resolved their mentions
 * to this id.
 *
 * Sections render only when the archive has something to put in them. A
 * profile that always looks complete is a profile that is partly invented.
 */
function PersonContent({ personId }: { personId: string }) {
  const { t, locale } = useMuraI18n();

  const load = useCallback(
    async (familyId: string, signal: AbortSignal): Promise<PersonBundle> => {
      const [people, relationships, stories] = await Promise.all([
        fetchArchivePeople(familyId, signal),
        fetchArchiveRelationships(familyId, signal),
        fetchArchiveStories(familyId, { limit: 50, signal }),
      ]);
      let profile: ArchiveProfile | null = null;
      try {
        profile = await fetchArchiveProfile(familyId, personId, signal);
      } catch (error) {
        // A person can exist without a materialized profile yet. That is
        // missing detail, not a missing person.
        if (!(error instanceof CoreRequestError) || error.status !== 404) throw error;
      }
      return { profile, people, relationships, stories: stories.items };
    },
    [personId],
  );

  const bundle = useArchiveResource<PersonBundle>(load);

  const relations = useMemo(
    () => buildFamilyRelations(bundle.data?.people ?? [], bundle.data?.relationships ?? []),
    [bundle.data],
  );

  const person = relations.personById(personId);
  const places = bundle.data?.profile?.locations ?? [];
  const stories = (bundle.data?.stories ?? []).filter((story) =>
    story.person_ids.includes(personId),
  );
  const spouse = relations.spouseOf(personId);
  const connections = [
    ...relations.parentsOf(personId),
    ...relations.childrenOf(personId),
    ...relations.siblingsOf(personId),
    ...(spouse ? [spouse] : []),
  ];

  return (
    <div className="pb-16">
      <ScreenHeader fallbackHref="/tree" />

      <ArchiveState resource={bundle} loadingLabel={t("personLoading")}>
        {!person ? (
          <PageContainer>
            <p className="py-16 text-center text-body text-muted">{t("personNotFound")}</p>
          </PageContainer>
        ) : (
          <PageContainer>
            <motion.div variants={container} initial="hidden" animate="visible" className="pt-2">
              <motion.header variants={item} className="flex items-start gap-4">
                <PersonAvatar
                  personId={person.person_id}
                  displayName={person.display_name}
                  size={72}
                />
                <div className="min-w-0 pt-1">
                  <h1 className="text-balance text-title font-bold leading-tight tracking-[-0.03em]">
                    {person.display_name}
                  </h1>
                  {person.relation_to_speaker && (
                    <p className="mt-1 text-body text-muted">{person.relation_to_speaker}</p>
                  )}
                </div>
              </motion.header>

              {person.aliases.length > 0 && (
                <motion.section variants={item} className="mt-7">
                  <SectionLabel>{t("personKnownAs")}</SectionLabel>
                  <p className="text-body leading-relaxed text-ink/80">
                    {person.aliases.join(" · ")}
                  </p>
                </motion.section>
              )}

              {places.length > 0 && (
                <motion.section variants={item} className="mt-7">
                  <SectionLabel>{t("personPlaces")}</SectionLabel>
                  <p className="text-body leading-relaxed text-ink/80">
                    {places.map((place) => place.value).join(" · ")}
                  </p>
                </motion.section>
              )}

              {connections.length > 0 && (
                <motion.section variants={item} className="mt-7">
                  <SectionLabel>{t("personConnections")}</SectionLabel>
                  <ul className="flex flex-wrap gap-2">
                    {connections.map((id) => {
                      const other = relations.personById(id);
                      if (!other) return null;
                      return (
                        <li key={id}>
                          <Link
                            href={`/person/${encodeURIComponent(id)}`}
                            className="flex items-center gap-2 rounded-full bg-raised py-1.5 pl-1.5 pr-3.5 text-meta font-medium shadow-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink/40"
                          >
                            <PersonAvatar
                              personId={other.person_id}
                              displayName={other.display_name}
                              size={26}
                            />
                            {other.display_name}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </motion.section>
              )}

              <motion.section variants={item} className="mt-8">
                <SectionLabel>{t("personStories")}</SectionLabel>
                {stories.length === 0 ? (
                  <p className="rounded-surface bg-raised p-5 text-body leading-relaxed text-muted">
                    {t("personNoStories")}
                  </p>
                ) : (
                  <ul className="space-y-3">
                    {stories.map((story) => (
                      <li key={story.story_id}>
                        <StoryLink story={story} locale={locale} untitled={t("storyUntitled")} />
                      </li>
                    ))}
                  </ul>
                )}
              </motion.section>
            </motion.div>
          </PageContainer>
        )}
      </ArchiveState>
    </div>
  );
}

export function PersonView({ personId }: { personId: string }) {
  return (
    <FamilyGate>
      <PersonContent personId={personId} />
    </FamilyGate>
  );
}
