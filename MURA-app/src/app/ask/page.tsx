import type { Metadata } from "next";
import { AskView } from "@/components/ask/ask-view";

export const metadata: Metadata = { title: "Спросить о семье" };

export default function AskPage() {
  return <AskView />;
}
