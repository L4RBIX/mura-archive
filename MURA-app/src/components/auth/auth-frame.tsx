import Link from "next/link";
import type { ReactNode } from "react";
import { VoiceToFamily } from "@/components/brand/voice-to-family";

/**
 * The MURA side of the auth pages.
 *
 * Clerk owns the form itself — password handling, MFA, lockout and recovery are
 * exactly the things worth not reimplementing — and this is the page around it.
 *
 * ## What it replaces
 *
 * Two columns of nothing much: a wordmark with a kicker above it, one line of
 * tagline, and a form floating in beige. The page a person lands on before
 * deciding whether to trust a product with twenty years of family recordings
 * said almost nothing about what it holds.
 *
 * Now the left column is a filled ink panel carrying the promise and one
 * concrete line about what the archive keeps, and the form sits on paper beside
 * it. The tonal split does the work: two clearly different surfaces, rather
 * than one field of beige with a boundary drawn on it.
 *
 * On a phone the panel collapses to a short header so the form stays above the
 * fold — a full-height brand panel that pushes sign-in off a 667px screen is
 * worse than no panel at all.
 */
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      {/* The promise. Ink-filled, and the only place on this page allowed
          weight — the form has to stay the thing you can act on. */}
      <aside className="relative overflow-hidden bg-ink-deep px-6 pb-10 pt-[max(env(safe-area-inset-top),28px)] text-raised sm:px-10 lg:flex lg:flex-col lg:justify-between lg:px-14 lg:pb-14 lg:pt-14">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 overflow-hidden"
        >
          {/* Text-coloured line art, so it takes the panel's own foreground and
              needs no second copy for the paper surfaces. */}
          <div className="absolute -right-10 top-[22%] w-[30rem] text-raised/70 sm:right-4 lg:-right-4 lg:w-[36rem]">
            <VoiceToFamily className="size-full" delay={0.15} />
          </div>
        </div>

        <div className="relative">
          <Link
            href="/"
            className="inline-block rounded-control [--focus-ring-offset:4px] focus-ring"
          >
            <span className="block text-[clamp(2.25rem,4.4vw,3.25rem)] font-bold leading-none tracking-[-0.045em]">
              Mura
            </span>
            <span className="mt-1.5 block text-meta text-raised/55">Мұра</span>
          </Link>
        </div>

        <div className="relative mt-8 lg:mt-0">
          <p className="max-w-[17ch] text-balance text-[clamp(1.5rem,2.6vw,2.1rem)] font-semibold leading-[1.15] tracking-[-0.03em]">
            Голос вашей семьи.
            <br />
            Навсегда.
          </p>
          {/* Concrete rather than a slogan: this names what the archive
              actually holds, which is the question somebody signing up is
              asking before they hand over their family's recordings. */}
          <p className="mt-4 hidden max-w-[38ch] text-body leading-relaxed text-raised/60 lg:block">
            Записи голосом, расшифровки, люди и связи между поколениями — в одном
            частном архиве, который видит только ваша семья.
          </p>
        </div>
      </aside>

      <main className="flex items-center justify-center px-6 py-12 sm:px-10 lg:px-14">
        <div className="w-full max-w-form">{children}</div>
      </main>
    </div>
  );
}
