"use client";

/**
 * The boundary between demonstration content and a real family archive.
 *
 * `/tree`, `/ask`, `/story/<fixture>` and `/person/<fixture>` are served
 * entirely from `src/data` fixtures. They are useful for showing what MURA
 * becomes, and they are not going away — but they were presenting invented
 * relatives, memories and answers with no visible marker at all, and `/tree`
 * went further and titled them «Ваша семья». A signed-in user with a real
 * archive saw the same nine fabricated people under a possessive heading.
 *
 * That is the one thing this product must never do. A family archive that
 * invents relatives is worse than no archive, so demonstration content has to
 * announce itself.
 *
 * The notice is deliberately louder once someone is signed in. Signed out,
 * "this is an example" is a reasonable default reading of a landing
 * experience; signed in, the user has an actual archive and the only honest
 * message is that this is not it.
 */

import { useMuraI18n } from "@/lib/i18n";
import { useMuraSession } from "@/lib/mura/session-provider";

export type DemoSurface = "tree" | "story" | "person" | "ask";

const NOTICE_KEY = {
  tree: "demoTreeNotice",
  story: "demoStoryNotice",
  person: "demoPersonNotice",
  ask: "demoAskNotice",
} as const;

/**
 * Whether the viewer has a real archive that this content could be confused
 * with. Only `authenticated` counts: while the session is still settling we
 * must not claim either way.
 */
export function useHasRealArchive(): boolean {
  const { auth } = useMuraSession();
  return auth.status === "authenticated";
}

/**
 * A persistent, non-dismissible marker. Non-dismissible on purpose: a banner
 * the user can close is a banner that is absent exactly when it matters.
 */
export function DemoNotice({
  surface,
  className,
}: {
  surface: DemoSurface;
  className?: string;
}) {
  const { t } = useMuraI18n();
  const signedIn = useHasRealArchive();

  // Tree is the surface that actually claimed ownership, so it gets the
  // stronger signed-in wording. The others are already non-possessive.
  const message =
    surface === "tree" && signedIn ? t("demoTreeNoticeSignedIn") : t(NOTICE_KEY[surface]);

  return (
    <div
      role="note"
      className={
        className ??
        "mx-6 mb-4 flex items-start gap-2.5 rounded-surface bg-clay/45 px-4 py-3 text-left"
      }
    >
      <DemoBadge />
      <p className="text-meta leading-relaxed text-ink/75">{message}</p>
    </div>
  );
}

/**
 * Compact inline marker, for headers and cards where a full notice would crowd.
 *
 * Outlined rather than a filled near-black chip. As `bg-ink/80` it was the
 * highest-contrast element on Home — a demonstration label pulling the eye
 * harder than «Семейное древо» and the family's own memories beside it, which
 * is the wrong thing for demo styling to win. Outlined uppercase still reads
 * unmistakably as a badge, and the surfaces that need more than a badge carry
 * the full `DemoNotice` sentence anyway.
 */
export function DemoBadge({ className }: { className?: string }) {
  const { t } = useMuraI18n();
  return (
    <span
      className={
        className ??
        "mt-px shrink-0 rounded-full border border-ink/30 px-2 py-0.5 text-caption font-semibold uppercase tracking-[0.08em] text-ink/70"
      }
    >
      {t("demoBadge")}
    </span>
  );
}
