"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { ArchiveState } from "@/components/archive/archive-state";
import { FamilyGate } from "@/components/family/family-gate";
import { AppHeader } from "@/components/layout/app-header";
import { drawableFrom } from "@/components/tree/layout";
import { TreeCanvas } from "@/components/tree/tree-canvas";
import { Button } from "@/components/ui/button";
import { useMuraI18n } from "@/lib/i18n";
import {
  fetchArchivePeople,
  fetchArchiveRelationships,
  type ArchivePerson,
  type ArchiveRelationship,
} from "@/lib/mura/archive-api";
import { buildFamilyRelations, type FamilyRelations } from "@/lib/mura/family-graph";
import { useArchiveResource } from "@/lib/mura/use-archive";

interface Graph {
  people: ArchivePerson[];
  relationships: ArchiveRelationship[];
}

/**
 * Both halves at once. The tree cannot draw anything without people *and*
 * edges, so there is nothing to stagger and no waterfall to introduce.
 */
async function loadGraph(familyId: string, signal: AbortSignal): Promise<Graph> {
  const [people, relationships] = await Promise.all([
    fetchArchivePeople(familyId, signal),
    fetchArchiveRelationships(familyId, signal),
  ]);
  return { people, relationships };
}

/** Everyone the canvas cannot draw around the person currently centred. */
function notDrawnFrom(relations: FamilyRelations, centerId: string): ArchivePerson[] {
  const drawable = drawableFrom(relations, centerId);
  return relations.people.filter((person) => !drawable.has(person.person_id));
}

/**
 * The family tree, drawn from the archive.
 *
 * A real archive is not one connected family. Extraction builds relationships
 * per recording, so early on it produces several small islands, and the canvas
 * can only ever show the one it is centred on. With five people in the archive
 * and two on screen there was no indication the others existed, let alone a
 * way to reach them — the canvas quietly under-reported the family.
 *
 * They are drawn now, as their own islands on the same canvas, with only the
 * relationships the archive genuinely recorded between their members. No line
 * is ever drawn *between* islands: that would assert a connection exists and is
 * merely unconfirmed, which is precisely the invention `family_graph_edges`
 * exists to prevent. What sits below the canvas is why they are separate and
 * what the user can do about it.
 */
function TreeContent() {
  const { t } = useMuraI18n();
  const router = useRouter();
  const searchParams = useSearchParams();

  const graph = useArchiveResource<Graph>(useCallback(loadGraph, []));

  const relations = useMemo(
    () => buildFamilyRelations(graph.data?.people ?? [], graph.data?.relationships ?? []),
    [graph.data],
  );

  const requested = searchParams.get("center");
  // Centre on the requested person only if they are genuinely in this archive:
  // a stale id carried over from another family must select nobody.
  const centerId =
    requested && relations.personById(requested)
      ? requested
      : (relations.people[0]?.person_id ?? null);

  const others = centerId ? notDrawnFrom(relations, centerId) : [];

  return (
    <div className="flex h-dvh flex-col">
      {/* One heading, not two: the header already says «Семейное древо», and a
          page title repeating it underneath was pure duplication. */}
      <AppHeader fallbackHref="/home" title={t("familyTree")} width="full" />

      <ArchiveState
        resource={graph}
        loadingLabel={t("treeLoading")}
        isEmpty={relations.people.length === 0}
        empty={
          <div className="mx-auto max-w-[42ch] px-6 py-14 text-center">
            <h1 className="text-balance text-section font-bold leading-snug tracking-[-0.02em]">
              {t("treeEmptyTitle")}
            </h1>
            <p className="mt-2.5 text-body leading-relaxed text-muted">{t("treeEmptyBody")}</p>
            <Button asChild size="lg" className="mt-6">
              <Link href="/record">{t("recordMemory")}</Link>
            </Button>
          </div>
        }
      >
        {centerId && (
          <>
            <div className="min-h-0 flex-1">
              <TreeCanvas
                key={centerId}
                relations={relations}
                centerId={centerId}
                onCenterChange={(id) =>
                  router.push(`/tree?center=${encodeURIComponent(id)}`, { scroll: false })
                }
              />
            </div>

            {/*
              The strip that used to list "people not shown" is gone: they are
              drawn on the canvas now, as their own islands. What remains is why
              they are separate and what the user can do about it — an
              unconnected island is a question for the archive to answer from a
              recording, not a defect to apologise for.
            */}
            {others.length > 0 && (
              <div className="shrink-0 border-t border-ink/[0.06] px-page pt-3">
                <p className="max-w-measure text-meta leading-relaxed text-muted">
                  {t("treeIslandsHint")}{" "}
                  <Link
                    href="/record"
                    className="font-medium text-ink underline underline-offset-4 focus-ring"
                  >
                    {t("recordMemory")}
                  </Link>
                </p>
              </div>
            )}

            <p className="shrink-0 pb-[max(env(safe-area-inset-bottom),14px)] pt-2.5 text-center text-meta text-muted">
              {t("treeHint")}
            </p>
          </>
        )}
      </ArchiveState>
    </div>
  );
}

export function TreeView() {
  // Family scope is required before anything is read, so the gate wraps the
  // screen rather than each request.
  return (
    <FamilyGate>
      <TreeContent />
    </FamilyGate>
  );
}
