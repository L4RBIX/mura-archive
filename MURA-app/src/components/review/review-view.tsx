"use client";

import { HelpCircle, Scale } from "lucide-react";
import { useCallback } from "react";
import { ArchiveState } from "@/components/archive/archive-state";
import { FamilyGate } from "@/components/family/family-gate";
import { ScreenHeader } from "@/components/layout/screen-header";
import { PageContainer } from "@/components/shell/page-container";
import { useMuraI18n } from "@/lib/i18n";
import { fetchArchiveReviewItems, type ArchiveReviewItem } from "@/lib/mura/archive-api";
import { useArchiveResource } from "@/lib/mura/use-archive";

/**
 * The things the archive cannot settle on its own.
 *
 * Every item here is persisted: a question extraction could not resolve, or a
 * conflict the archive detected between claims. There is no client-side rule
 * deciding what counts as uncertain — putting that definition in a browser is
 * how "needs review" quietly becomes whatever the UI finds convenient, and it
 * would also mean two clients disagreeing about the same family.
 *
 * The wording is human. `evidence_class`, assertion modes and confidences stay
 * on the server; what a family member is asked is a question in their own
 * language.
 *
 * Nothing is resolvable from this screen yet. Conflict resolution is a
 * capability-guarded mutation, and offering a button that 403s for a viewer
 * would be worse than offering none.
 */
function ReviewContent() {
  const { t } = useMuraI18n();
  const load = useCallback(
    (familyId: string, signal: AbortSignal) => fetchArchiveReviewItems(familyId, signal),
    [],
  );
  const review = useArchiveResource<ArchiveReviewItem[]>(load);
  const items = review.data ?? [];

  return (
    <div className="pb-16">
      <ScreenHeader title={t("reviewTitle")} fallbackHref="/home" />

      <ArchiveState
        resource={review}
        loadingLabel={t("reviewLoading")}
        isEmpty={items.length === 0}
        empty={
          <PageContainer>
            <div className="mx-auto max-w-[46ch] py-14 text-center">
              <h1 className="text-balance text-section font-bold leading-snug tracking-[-0.02em]">
                {t("reviewEmptyTitle")}
              </h1>
              <p className="mt-2.5 text-body leading-relaxed text-muted">
                {t("reviewEmptyBody")}
              </p>
            </div>
          </PageContainer>
        }
      >
        <PageContainer>
          <ul className="max-w-[58ch] divide-y divide-ink/[0.06] pt-1">
            {items.map((entry) => {
              const isConflict = entry.kind.startsWith("conflict");
              const Icon = isConflict ? Scale : HelpCircle;
              return (
                <li key={entry.review_id} className="flex items-start gap-3.5 py-4">
                  <Icon
                    aria-hidden
                    className={`mt-0.5 size-5 shrink-0 ${isConflict ? "text-ink/60" : "text-ink/35"}`}
                    strokeWidth={1.8}
                  />
                  <div className="min-w-0">
                    {/* Only a conflict is labelled. An eyebrow reading «ВОПРОС»
                        above every question, next to a question-mark icon, on a
                        page titled «Нужно уточнить», says nothing three other
                        things have not already said. */}
                    {isConflict && (
                      <p className="mb-1 text-caption font-semibold uppercase tracking-[0.14em] text-muted">
                        {t("reviewConflict")}
                      </p>
                    )}
                    <p className="text-item font-medium leading-snug">{entry.question}</p>
                    {entry.detail && (
                      <p className="mt-1.5 text-body leading-relaxed text-muted">{entry.detail}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </PageContainer>
      </ArchiveState>
    </div>
  );
}

export function ReviewView() {
  return (
    <FamilyGate>
      <ReviewContent />
    </FamilyGate>
  );
}
