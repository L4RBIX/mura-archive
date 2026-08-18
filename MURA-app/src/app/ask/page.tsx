import type { Metadata } from "next";
import { AskView } from "@/components/ask/ask-view";

export const metadata: Metadata = { title: "Ask" };

export default function AskPage() {
  return <AskView />;
}
