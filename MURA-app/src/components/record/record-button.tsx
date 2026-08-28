"use client";

import { Mic } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

interface RecordButtonProps {
  href?: string;
  onClick?: () => void;
  size?: number;
  label?: string;
  sublabel?: string;
  className?: string;
  /**
   * Present but not yet usable.
   *
   * The record screen used to *remove* this control until a speaker had been
   * chosen, so somebody arriving at the one screen the product is built around
   * found no button on it — the missing precondition was explained in a line
   * of grey text where the control should have been. Disabled with its reason
   * beneath it is the honest form: the control is where it belongs, it plainly
   * cannot be pressed, and the screen says why.
   */
  disabled?: boolean;
}

/**
 * The one button. A quiet ink circle with a breathing ring — pressing it is
 * the whole product.
 */
export function RecordButton({
  href,
  onClick,
  size = 136,
  label,
  sublabel,
  className,
  disabled = false,
}: RecordButtonProps) {
  const content = (
    <span className="flex flex-col items-center gap-5">
      <span className="relative block" style={{ width: size, height: size }}>
        {/* The breathing ring is an invitation, so it stops when the control
            cannot be pressed. A pulsing disabled button is a lie about it. */}
        {!disabled && (
          <>
            <span className="absolute inset-0 animate-breathe rounded-full border border-ink/25" />
            <span
              className="absolute inset-0 animate-breathe rounded-full border border-ink/15"
              style={{ animationDelay: "1.4s" }}
            />
          </>
        )}
        <span className="relative flex size-full items-center justify-center rounded-full bg-ink text-raised shadow-card transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] group-active:scale-95">
          <Mic
            style={{ width: size * 0.3, height: size * 0.3 }}
            strokeWidth={1.7}
          />
        </span>
      </span>
      {(label || sublabel) && (
        <span className="flex flex-col items-center gap-1">
          {label && <span className="text-item font-semibold">{label}</span>}
          {sublabel && <span className="text-meta text-muted">{sublabel}</span>}
        </span>
      )}
    </span>
  );

  const sharedClass = cn(
    "group block rounded-panel [--focus-ring-offset:8px] focus-ring",
    disabled && "cursor-not-allowed opacity-45",
    className,
  );

  if (disabled) {
    return (
      <button type="button" disabled aria-disabled className={sharedClass}>
        {content}
      </button>
    );
  }

  if (href) {
    return (
      <Link href={href} className={sharedClass}>
        {content}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className={sharedClass}>
      {content}
    </button>
  );
}
