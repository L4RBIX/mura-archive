"use client";

/**
 * The four things that can be true of an archive read, told apart.
 *
 * Loading, empty, forbidden and failed are different situations with different
 * remedies, and collapsing them into one apology is how "your family archive
 * is empty" ends up shown to somebody whose network merely blinked. An empty
 * archive in particular is a real, correct state that deserves its own words
 * rather than a spinner that never resolves.
 *
 * Nothing renders children until the data belongs to the current family, so a
 * screen can never paint one family's content under another's name.
 */

import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useMuraI18n } from "@/lib/i18n";
import type { ArchiveResource } from "@/lib/mura/use-archive";

export function ArchiveState<T>({
  resource,
  loadingLabel,
  isEmpty = false,
  empty,
  children,
}: {
  resource: ArchiveResource<T>;
  loadingLabel?: string;
  /** Computed by the caller, which knows what "nothing here" means for it. */
  isEmpty?: boolean;
  empty?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useMuraI18n();

  if (resource.status === "idle" || resource.status === "loading") {
    return (
      <div
        className="flex flex-1 flex-col items-center justify-center gap-4 px-8 py-16"
        role="status"
        aria-live="polite"
      >
        <div className="size-10 animate-pulse rounded-full bg-clay/60" />
        {loadingLabel && <p className="text-meta text-muted">{loadingLabel}</p>}
      </div>
    );
  }

  if (resource.status === "forbidden") {
    // A role that may not read this surface is not an outage, and saying the
    // service failed would be false.
    return (
      <Notice title={t("archiveForbidden")} />
    );
  }

  if (resource.status === "error") {
    return (
      <Notice
        title={t("archiveError")}
        action={
          <Button variant="soft" onClick={resource.reload} className="mt-4">
            {t("archiveRetry")}
          </Button>
        }
      />
    );
  }

  // `ready` with no data for the current family cannot happen, but rendering
  // children on that state would be the one bug worth preventing outright.
  if (resource.data === null || resource.familyId === null) return null;

  if (isEmpty && empty) return <>{empty}</>;

  return <>{children}</>;
}

function Notice({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div
      className="flex flex-1 flex-col items-center justify-center px-8 py-16 text-center"
      role="status"
      aria-live="polite"
    >
      <p className="max-w-[42ch] text-balance text-body font-medium leading-relaxed">{title}</p>
      {action}
    </div>
  );
}
