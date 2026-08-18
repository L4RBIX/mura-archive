"use client";

import { motion } from "framer-motion";
import type { FamilyGraphEdge } from "./layout";

export function OrganicEdge({ edge }: { edge: FamilyGraphEdge }) {
  const isMarriage = edge.kind === "marriage";
  return (
    <motion.path
      d={edge.d}
      fill="none"
      stroke="#8a857d"
      strokeOpacity={isMarriage ? 0.4 : 0.42}
      strokeWidth={isMarriage ? 1.25 : 1.5}
      strokeLinecap="round"
      initial={{ pathLength: 0, opacity: 0 }}
      animate={{ pathLength: 1, opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.15 } }}
      transition={{
        pathLength: { duration: 0.65, ease: [0.23, 1, 0.32, 1], delay: edge.delay },
        opacity: { duration: 0.3, delay: edge.delay },
      }}
    />
  );
}
