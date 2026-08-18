"use client";

import { Play } from "lucide-react";
import Link from "next/link";
import { formatDuration } from "@/lib/format";
import type { Story } from "@/lib/types";
import { useMuraI18n } from "@/lib/i18n";

export function MemoryCard({ story }: { story: Story }) {
  const { t } = useMuraI18n();
  return (
    <Link
      href={`/story/${story.id}`}
      className="block rounded-panel bg-raised p-5 shadow-soft transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] active:scale-[0.98] focus-ring"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          {story.isNew && (
            <span className="mb-1.5 inline-block rounded-full bg-clay px-2.5 py-0.5 text-caption font-semibold">
              {t("new")}
            </span>
          )}
          <h3 className="line-clamp-2 text-item font-semibold leading-snug">
            {story.title}
          </h3>
          <p className="mt-1 text-meta text-muted">
            {story.recordedLabel} · {formatDuration(story.durationSec)}
          </p>
        </div>
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-sand">
          <Play className="size-3.5 fill-current" strokeWidth={0} />
        </span>
      </div>
    </Link>
  );
}
