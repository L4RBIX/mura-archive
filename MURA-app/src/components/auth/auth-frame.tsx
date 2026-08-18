import Link from "next/link";
import type { ReactNode } from "react";

/**
 * The MURA side of the auth pages.
 *
 * Clerk owns the form itself -- password handling, MFA, lockout and recovery
 * are exactly the things worth not reimplementing -- but the page around it
 * was bare paper, so signing in felt like leaving the product and landing on a
 * vendor screen. This puts the mark, the promise and a way back around it.
 *
 * On a wide window it becomes two columns: the brand holds the left, the form
 * sits right. Below that it stacks, and the brand shrinks to a wordmark so the
 * form stays above the fold on a phone.
 */
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto grid min-h-dvh w-full max-w-wide items-center gap-10 px-6 py-10 lg:grid-cols-2 lg:gap-16 lg:px-10">
      <div className="text-center lg:text-left">
        <Link
          href="/"
          className="inline-block rounded-control [--focus-ring-offset:4px] focus-ring"
        >
          <span className="block text-caption font-semibold uppercase tracking-[0.3em] text-muted">
            Мұра
          </span>
          <span className="block text-[clamp(2.75rem,7vw,4.5rem)] font-bold leading-none tracking-[-0.04em]">
            Mura
          </span>
        </Link>
        <p className="mx-auto mt-5 max-w-[24ch] text-item leading-snug text-ink/70 lg:mx-0 lg:text-section">
          Голос вашей семьи.
          <br />
          Навсегда.
        </p>
      </div>

      <div className="flex justify-center lg:justify-start">{children}</div>
    </div>
  );
}
