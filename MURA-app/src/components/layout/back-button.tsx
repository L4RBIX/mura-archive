"use client";

import { ChevronLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMuraI18n } from "@/lib/i18n";

interface BackButtonProps {
  /** Where to go when there is no history, e.g. after a deep link. */
  fallbackHref?: string;
}

export function BackButton({ fallbackHref = "/home" }: BackButtonProps) {
  const router = useRouter();
  const { t } = useMuraI18n();

  const goBack = () => {
    if (window.history.length > 1) router.back();
    else router.push(fallbackHref);
  };

  return (
    <button
      type="button"
      aria-label={t("goBack")}
      onClick={goBack}
      className="flex size-11 items-center justify-center rounded-full bg-raised text-ink shadow-soft transition-transform duration-200 active:scale-95 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink/40"
    >
      <ChevronLeft className="size-5" strokeWidth={2} />
    </button>
  );
}
