import type { Metadata } from "next";
import { FamilyGate } from "@/components/family/family-gate";
import { RecordView } from "@/components/record/record-view";

export const metadata: Metadata = { title: "New memory" };

export default function RecordPage() {
  // Recording writes into a family archive, so it may not render until the app
  // knows which authorized family it is writing to.
  return (
    <FamilyGate>
      <RecordView />
    </FamilyGate>
  );
}
