"use client";

/**
 * Playback of a real recording.
 *
 * This replaces the mock player, which drew a seeded waveform and animated a
 * progress bar over audio that was never retrievable. On a family archive that
 * is not a placeholder, it is a claim that a recording exists — so the player
 * now either plays the actual bytes Core serves or the page says the audio is
 * unavailable.
 *
 * Deliberately the platform `<audio>` element: it brings keyboard support,
 * screen-reader semantics and OS media controls that a hand-built transport
 * would have to reimplement, and none of that is where this product should be
 * spending its originality.
 */

import { useMuraI18n } from "@/lib/i18n";
import { recordingAudioUrl } from "@/lib/mura/archive-api";

export function RecordingPlayer({
  familyId,
  recordingId,
  available,
}: {
  familyId: string;
  recordingId: string;
  available: boolean;
}) {
  const { t } = useMuraI18n();

  if (!available) {
    return (
      // A one-line absence does not need a surface, a shadow and 40px of
      // padding announcing it.
      <p className="text-meta text-muted">{t("storyAudioUnavailable")}</p>
    );
  }

  return (
    <div className="rounded-panel bg-raised p-3">
      {/* `preload="none"`: a story page must not pull a whole recording down
          before anyone has asked to hear it. */}
      <audio
        controls
        preload="none"
        className="w-full"
        src={recordingAudioUrl(familyId, recordingId)}
      >
        {t("storyAudioUnavailable")}
      </audio>
    </div>
  );
}
