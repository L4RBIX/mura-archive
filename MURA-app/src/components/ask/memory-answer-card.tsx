"use client";

import { motion } from "framer-motion";
import Image from "next/image";
import { DemoBadge } from "@/components/demo/demo-notice";
import { useMuraI18n } from "@/lib/i18n";
import type { DemoMemory } from "@/lib/mascot/demo-memory";

const EASE = [0.23, 1, 0.32, 1] as const;

/**
 * What the mascot found, shown while she talks about it. Photos lead — this is
 * a memory, not a search result.
 */
export function MemoryAnswerCard({ memory }: { memory: DemoMemory }) {
  const { t } = useMuraI18n();
  const [wide, tall] = memory.photos;

  return (
    <motion.article
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: EASE }}
      className="w-full overflow-hidden rounded-panel bg-raised shadow-card"
    >
      {/* The card travels on its own into other screens, so it carries its own
          marker rather than relying on a banner elsewhere on the page. */}
      <div className="flex items-center gap-2 px-4 pt-3">
        <DemoBadge className="shrink-0 rounded-full bg-ink/80 px-2 py-0.5 text-caption font-semibold uppercase tracking-[0.08em] text-sand" />
        <span className="text-caption font-medium text-ink/55">{t("demoAskAnswerBadge")}</span>
      </div>

      <div className="flex gap-1 p-1">
        <motion.div
          initial={{ opacity: 0, scale: 1.04 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1, duration: 0.7, ease: EASE }}
          className="relative aspect-[4/3] flex-[1.35] overflow-hidden rounded-surface bg-sand"
        >
          <Image
            src={wide.src}
            alt={t(wide.altKey)}
            fill
            sizes="(max-width: 430px) 60vw, 260px"
            className="object-cover"
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, scale: 1.04 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.7, ease: EASE }}
          className="relative aspect-[4/3] flex-1 overflow-hidden rounded-surface bg-sand"
        >
          <Image
            src={tall.src}
            alt={t(tall.altKey)}
            fill
            sizes="(max-width: 430px) 40vw, 180px"
            className="object-cover object-top"
          />
        </motion.div>
      </div>

      <div className="px-5 pb-5 pt-3.5">
        <p className="text-caption font-semibold uppercase tracking-[0.16em] text-ink/60">
          {t("memoryFound")}
        </p>
        <h2 className="mt-2 text-balance text-section font-bold leading-[1.25] tracking-[-0.02em]">
          {t(memory.titleKey)}
        </h2>
        <p className="mt-1.5 text-meta font-medium text-ink/65">{t(memory.eraKey)}</p>
        <p className="mt-3 text-pretty text-body leading-relaxed text-ink/75">
          {t(memory.summaryKey)}
        </p>
      </div>
    </motion.article>
  );
}
