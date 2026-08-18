import { toneBg } from "@/lib/tones";
import type { AccentTone } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Photo placeholder for a canonical archive person.
 *
 * The tone is derived from the person id rather than stored, so it is stable
 * for a given person without the archive having to hold a decorative field it
 * has no way to know. It is deliberately not derived from the *name*: two
 * relatives who share a name are different people and should not be given the
 * same colour, which would suggest a connection the archive never recorded.
 */
/**
 * `sand` (#ece9e2) is a hair off `paper` (#eee8df), so every third person got
 * an avatar with no visible circle at all — a blank initial floating beside
 * their name while their relatives had a disc. The tone here is decoration and
 * carries no meaning, so two that actually read beats three where one vanishes.
 */
const TONES: AccentTone[] = ["clay", "periwinkle"];

function toneFor(personId: string): AccentTone {
  let hash = 0;
  for (let index = 0; index < personId.length; index += 1) {
    hash = (hash * 31 + personId.charCodeAt(index)) >>> 0;
  }
  return TONES[hash % TONES.length];
}

export function PersonAvatar({
  personId,
  displayName,
  size = 40,
  className,
}: {
  personId: string;
  displayName: string;
  size?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold text-ink/75",
        toneBg[toneFor(personId)],
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
    >
      {displayName.trim()[0] ?? "?"}
    </span>
  );
}
