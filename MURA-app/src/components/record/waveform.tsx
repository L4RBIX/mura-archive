"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const BAR_COUNT = 40;
const IDLE_HEIGHT = 0.08;

/**
 * Live waveform: new bars enter on the right and history slides left,
 * the way a real voice recorder draws.
 */
export function Waveform({
  active,
  level,
  className,
}: {
  active: boolean;
  level: number;
  className?: string;
}) {
  const [amps, setAmps] = useState<number[]>(() =>
    Array.from({ length: BAR_COUNT }, () => IDLE_HEIGHT),
  );

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      setAmps((prev) => [
        ...prev.slice(1),
        active ? Math.max(IDLE_HEIGHT, level) : IDLE_HEIGHT,
      ]);
    }, 110);
    return () => clearInterval(id);
  }, [active, level]);

  return (
    <div className={cn("flex h-10 items-center gap-[3px]", className)} aria-hidden>
      {amps.map((amp, i) => (
        <span
          key={i}
          className="h-full min-w-0 flex-1 rounded-full bg-ink/85 transition-transform duration-150 ease-linear"
          style={{ transform: `scaleY(${active ? amp : amp * 0.6})` }}
        />
      ))}
    </div>
  );
}
