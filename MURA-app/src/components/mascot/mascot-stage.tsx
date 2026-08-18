"use client";

import { Lastochka } from "@/components/mascot/lastochka";
import type { MascotState } from "@/lib/mascot/types";
import { cn } from "@/lib/utils";

interface MascotStageProps {
  state: MascotState;
  size?: number;
  className?: string;
}

/**
 * The mascot, and nothing around her.
 *
 * She used to carry captions for her own voice-over and a "tap to hear" button
 * for when a browser blocked autoplay. With the voice removed there is nothing
 * to caption and nothing to unblock, so the stage is just her.
 */
export function MascotStage({ state, size = 260, className }: MascotStageProps) {
  return (
    <div className={cn("relative flex flex-col items-center", className)}>
      <Lastochka state={state} size={size} />
    </div>
  );
}
