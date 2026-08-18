import type { Metadata } from "next";
import { Suspense } from "react";
import { FamilyGate } from "@/components/family/family-gate";
import { ProcessingView } from "@/components/processing/processing-view";

export const metadata: Metadata = { title: "Обработка воспоминания" };

export default function ProcessingPage() {
  // Gated on a session, but the family this recording belongs to comes from the
  // URL, not from the current selection -- see ProcessingView.
  return (
    <Suspense>
      <FamilyGate>
        <ProcessingView />
      </FamilyGate>
    </Suspense>
  );
}
