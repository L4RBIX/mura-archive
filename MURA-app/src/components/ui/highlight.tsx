import { toneBg } from "@/lib/tones";
import type { AccentTone } from "@/lib/types";
import { cn } from "@/lib/utils";

interface HighlightProps {
  tone?: AccentTone;
  className?: string;
  children: React.ReactNode;
}

/**
 * The pastel highlighter mark — Mura’s signature. Names in transcripts, the
 * live sentence while recording, and key phrases all wear it.
 */
export function Highlight({ tone = "clay", className, children }: HighlightProps) {
  return (
    <mark
      className={cn(
        "rounded-[0.35em] box-decoration-clone px-[0.18em] py-[0.08em] text-inherit",
        toneBg[tone],
        className,
      )}
    >
      {children}
    </mark>
  );
}
