import type { Metadata } from "next";
import { Suspense } from "react";
import { TreeView } from "@/components/tree/tree-view";

export const metadata: Metadata = { title: "Семейное древо" };

export default function TreePage() {
  return (
    <Suspense fallback={null}>
      <TreeView />
    </Suspense>
  );
}
