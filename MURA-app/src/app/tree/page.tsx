import type { Metadata } from "next";
import { Suspense } from "react";
import { TreeView } from "@/components/tree/tree-view";

export const metadata: Metadata = { title: "Family tree" };

export default function TreePage() {
  return (
    <Suspense fallback={null}>
      <TreeView />
    </Suspense>
  );
}
