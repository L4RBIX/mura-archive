"use client";

import { createContext, useCallback, useContext, type ReactNode } from "react";
import { fetchArchiveOverview, type ArchiveOverview } from "@/lib/mura/archive-api";
import { useArchiveResource, type ArchiveResource } from "@/lib/mura/use-archive";

/**
 * One read of the archive summary, shared by everything that needs it.
 *
 * The rail wants the family's counts and Home wants the same object plus its
 * recent stories. Fetching in both would issue two identical requests on every
 * visit to Home — the exact repeated-request problem worth avoiding, and it
 * would also let the two disagree for a moment after a change.
 *
 * All of the family-isolation guarantees come from `useArchiveResource`
 * underneath: render-phase reset on a family change, generation-checked
 * responses, and nothing loaded at all when signed out. This only shares the
 * result; it does not relax any of that.
 *
 * Mounted inside the product chrome, so the pre-product screens never issue it.
 */

const OverviewContext = createContext<ArchiveResource<ArchiveOverview> | null>(null);

const load = (familyId: string, signal: AbortSignal) =>
  fetchArchiveOverview(familyId, signal);

export function ArchiveOverviewProvider({ children }: { children: ReactNode }) {
  const resource = useArchiveResource<ArchiveOverview>(useCallback(load, []));
  return <OverviewContext.Provider value={resource}>{children}</OverviewContext.Provider>;
}

/** The full resource, including status. Null outside the provider. */
export function useArchiveOverviewResource(): ArchiveResource<ArchiveOverview> | null {
  return useContext(OverviewContext);
}

/**
 * Just the summary, once it has arrived.
 *
 * Returns null while loading, when signed out, and when there is no family —
 * three different situations that share one correct behaviour here: show
 * nothing rather than a zero.
 */
export function useArchiveOverview(): ArchiveOverview | null {
  const resource = useContext(OverviewContext);
  return resource?.status === "ready" ? resource.data : null;
}
