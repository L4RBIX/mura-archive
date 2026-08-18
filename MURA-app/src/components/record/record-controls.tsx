"use client";

import { motion } from "framer-motion";
import { Check, Pause, Play, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMuraI18n } from "@/lib/i18n";

interface RecordControlsProps {
  paused: boolean;
  onPause: () => void;
  onResume: () => void;
  onRestart: () => void;
  onFinish: () => void;
}

function ControlTile({
  label,
  onClick,
  className,
  children,
}: {
  label: string;
  onClick: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <motion.button
      type="button"
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      className={cn(
        "flex h-[76px] flex-1 flex-col items-center justify-center gap-1.5 rounded-surface text-ink shadow-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink/40",
        className,
      )}
    >
      {children}
      <span className="text-caption font-medium text-ink/70">{label}</span>
    </motion.button>
  );
}

export function RecordControls({
  paused,
  onPause,
  onResume,
  onRestart,
  onFinish,
}: RecordControlsProps) {
  const { t } = useMuraI18n();
  return (
    <div className="flex gap-3">
      <ControlTile label={t("restart")} className="bg-periwinkle" onClick={onRestart}>
        <RotateCcw className="size-[22px]" strokeWidth={1.8} />
      </ControlTile>
      {paused ? (
        <ControlTile label={t("resume")} className="bg-raised" onClick={onResume}>
          <Play className="size-[22px] fill-current" strokeWidth={0} />
        </ControlTile>
      ) : (
        <ControlTile label={t("pause")} className="bg-raised" onClick={onPause}>
          <Pause className="size-[22px] fill-current" strokeWidth={0} />
        </ControlTile>
      )}
      <ControlTile label={t("finish")} className="bg-clay" onClick={onFinish}>
        <Check className="size-[22px]" strokeWidth={1.8} />
      </ControlTile>
    </div>
  );
}
