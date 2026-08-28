"use client";

import { motion } from "framer-motion";
import { VoiceToFamily } from "@/components/brand/voice-to-family";
import { Button } from "@/components/ui/button";
import { useMuraI18n } from "@/lib/i18n";
import { NARRATOR_ROLES, useNarratorRole, type NarratorRole } from "@/lib/mura/narrator-role";

/**
 * The third step of first run: who is holding the phone.
 *
 * Asked once, immediately after the family exists and immediately before the
 * first recording, because that is the only moment the answer is useful. It is
 * skippable in one tap and it never blocks anything — the point of this flow is
 * to reach the first recording quickly, and a question that stands between
 * someone and that moment had better be earning its place.
 *
 * It says what it is for, and it says what it is not. «Это не запись в архиве»
 * is there because a family-archive product asking "who are you in this family"
 * reasonably sounds like it is about to write that down, and it is not: the
 * answer stays in this browser and only reorders the questions offered. Who a
 * memory is attributed to is still asked, out loud, every time something is
 * recorded.
 */
export function RoleStep({ onDone }: { onDone: () => void }) {
  const { t } = useMuraI18n();
  const { role, setRole } = useNarratorRole();

  const choose = (next: NarratorRole) => {
    setRole(next);
    // No confirm step: the choice is the answer, and a second tap on «Дальше»
    // to agree with what you just tapped is a step that exists for the form.
    onDone();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
      // Hosted inside Home, so it sizes to its content rather than claiming a
      // viewport: the greeting, the navigation and the recorder stay on screen
      // and this never becomes a wall between the user and the product.
      className="relative w-full max-w-form"
    >
      {/*
        The motif is clipped to this step's own box.

        Positioned decoration that hangs past the right edge has nothing to clip
        it when it sits directly on the page rather than inside a panel, so on a
        320px phone it pushed the document 60px wider than the viewport and the
        whole app scrolled sideways. The clipping wrapper is a separate element
        from the content so `overflow-hidden` can never cut off a focus ring.
      */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -right-10 top-2 w-56 text-ink/30 sm:-right-4 sm:w-72">
          <VoiceToFamily className="size-full" delay={0.1} />
        </div>
      </div>

      <div className="relative">
        <h1 className="text-balance text-title font-bold leading-tight tracking-[-0.025em]">
          {t("roleStepTitle")}
        </h1>
        <p className="mt-3 max-w-[44ch] text-body leading-relaxed text-muted">
          {t("roleStepBody")}
        </p>

        <div className="mt-7 flex flex-col gap-2">
          {NARRATOR_ROLES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => choose(option.value)}
              aria-pressed={role === option.value}
              className={`flex min-h-[56px] items-center rounded-surface px-4 text-left text-body font-medium transition-colors focus-ring ${
                role === option.value
                  ? "bg-ink text-raised"
                  : "bg-raised text-ink hover:bg-sand"
              }`}
            >
              {t(option.labelKey)}
            </button>
          ))}
        </div>

        <Button variant="ghost" size="md" className="mt-5 w-full" onClick={onDone}>
          {t("roleStepSkip")}
        </Button>
      </div>
    </motion.div>
  );
}
