"use client";

/**
 * Search across the family archive.
 *
 * Honest about its reach. **Core has no search endpoint** — `apps/api/archive.py`
 * exposes list and detail routes only — so this filters what it can load: the
 * family's people, and the most recent page of memories Core will serve in one
 * request. That is genuinely useful for an archive of a few dozen memories and
 * genuinely insufficient for one of a few thousand, and the dialog says so in
 * one line rather than letting the user believe an empty result means the
 * archive holds nothing.
 *
 * People are matched on `display_name` and `aliases` because that is what a
 * person types, but a *result* is always a canonical `person_id`. Nothing here
 * joins a story to a person by name; stories are matched on their own text.
 */

import { Search, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import { fetchArchivePeople, fetchArchiveStories } from "@/lib/mura/archive-api";
import {
  searchArchive,
  type SearchBundle,
} from "@/lib/mura/archive-search";
import { useArchiveResource } from "@/lib/mura/use-archive";

/** The largest single page Core will serve. */
const SEARCH_WINDOW = 100;

export function ArchiveSearch({ onClose }: { onClose: () => void }) {
  const { t, locale } = useMuraI18n();
  const [query, setQuery] = useState("");
  const [personId, setPersonId] = useState<string | null>(null);
  const [year, setYear] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const load = useCallback(
    async (familyId: string, signal: AbortSignal): Promise<SearchBundle> => {
      const [people, page] = await Promise.all([
        fetchArchivePeople(familyId, signal),
        fetchArchiveStories(familyId, { limit: SEARCH_WINDOW, signal }),
      ]);
      return { people, stories: page.items, totalStories: page.page.total };
    },
    [],
  );
  const archive = useArchiveResource<SearchBundle>(load);
  const bundle = archive.data;

  const results = useMemo(
    () =>
      bundle ? searchArchive(bundle, query, { personId, year }) : [],
    [bundle, query, personId, year],
  );

  // Years the archive genuinely has memories from — never a range invented by
  // counting backwards from today.
  const years = useMemo(() => {
    const found = new Set((bundle?.stories ?? []).map((s) => s.recorded_at.slice(0, 4)));
    return [...found].sort().reverse();
  }, [bundle]);

  useEffect(() => setActive(0), [query, personId, year]);
  useEffect(() => inputRef.current?.focus(), []);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      const chosen = results[active];
      if (chosen) {
        event.preventDefault();
        document.getElementById(`${listId}-${active}`)?.querySelector("a")?.click();
      }
    }
  };

  const partial = bundle ? bundle.totalStories > bundle.stories.length : false;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("searchTitle")}
      className="fixed inset-0 z-[90] flex items-start justify-center bg-ink/25 px-4 pt-[8vh] backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[80vh] w-full max-w-form flex-col overflow-hidden rounded-panel bg-paper shadow-card">
        <div className="flex items-center gap-3 border-b border-ink/[0.08] px-4">
          <Search aria-hidden className="size-5 shrink-0 text-muted" strokeWidth={1.8} />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label={t("searchPlaceholder")}
            aria-controls={listId}
            placeholder={t("searchPlaceholder")}
            className="h-14 flex-1 bg-transparent text-body outline-none placeholder:text-muted"
          />
          <button
            type="button"
            onClick={onClose}
            aria-label={t("searchClose")}
            className="flex size-11 shrink-0 items-center justify-center rounded-full text-muted hover:text-ink focus-ring"
          >
            <X className="size-5" strokeWidth={2} />
          </button>
        </div>

        {(bundle?.people.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1.5 border-b border-ink/[0.08] px-4 py-2.5">
            <Facet active={!personId && !year} onClick={() => { setPersonId(null); setYear(null); }}>
              {t("searchAll")}
            </Facet>
            {bundle?.people.slice(0, 6).map((person) => (
              <Facet
                key={person.person_id}
                active={personId === person.person_id}
                onClick={() =>
                  setPersonId((current) =>
                    current === person.person_id ? null : person.person_id,
                  )
                }
              >
                {person.display_name}
              </Facet>
            ))}
            {years.map((value) => (
              <Facet
                key={value}
                active={year === value}
                onClick={() => setYear((current) => (current === value ? null : value))}
              >
                {value}
              </Facet>
            ))}
          </div>
        )}

        <p className="sr-only" role="status" aria-live="polite">
          {t("searchResultCount", { count: results.length })}
        </p>

        <ul id={listId} className="min-h-0 flex-1 overflow-y-auto p-2">
          {results.map((result, index) => (
            <li key={`${result.kind}:${result.id}`} id={`${listId}-${index}`}>
              {result.kind === "person" ? (
                <Link
                  href={`/person/${encodeURIComponent(result.id)}`}
                  onClick={onClose}
                  className={`flex items-center gap-3 rounded-surface px-3 py-2.5 focus-ring ${
                    index === active ? "bg-sand" : ""
                  }`}
                >
                  <PersonAvatar
                    personId={result.person.person_id}
                    displayName={result.person.display_name}
                    size={32}
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-body font-medium">
                      {result.person.display_name}
                    </span>
                    <span className="block text-caption text-muted">{t("searchPerson")}</span>
                  </span>
                </Link>
              ) : (
                <Link
                  href={`/story/${encodeURIComponent(result.id)}`}
                  onClick={onClose}
                  className={`block rounded-surface px-3 py-2.5 focus-ring ${
                    index === active ? "bg-sand" : ""
                  }`}
                >
                  <span className="block truncate text-body font-medium">
                    {result.story.title ?? t("storyUntitled")}
                  </span>
                  <span className="block text-caption text-muted">
                    {result.story.speaker_name} ·{" "}
                    {new Date(result.story.recorded_at).toLocaleDateString(
                      locale === "kk" ? "kk-KZ" : "ru-RU",
                    )}
                  </span>
                </Link>
              )}
            </li>
          ))}
          {archive.status === "ready" && results.length === 0 && (
            <p className="px-3 py-6 text-center text-body text-muted">{t("searchNothing")}</p>
          )}
          {archive.status === "loading" && (
            <p className="px-3 py-6 text-center text-body text-muted">{t("searchLoading")}</p>
          )}
        </ul>

        {/*
          The reach of this search, stated plainly. Without it an empty result
          reads as "your family archive does not contain this", which would be a
          claim the product cannot currently make.
        */}
        {partial && bundle && (
          <p className="border-t border-ink/[0.08] px-4 py-2.5 text-caption leading-relaxed text-muted">
            {t("searchPartial", {
              loaded: bundle.stories.length,
              total: bundle.totalStories,
            })}
          </p>
        )}
      </div>
    </div>
  );
}

function Facet({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full px-3 py-1 text-caption font-medium transition-colors focus-ring ${
        active ? "bg-ink text-raised" : "bg-raised text-ink/70 hover:bg-sand"
      }`}
    >
      {children}
    </button>
  );
}
