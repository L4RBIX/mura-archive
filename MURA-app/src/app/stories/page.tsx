import type { Metadata } from "next";
import { StoriesView } from "@/components/story/stories-view";

export const metadata: Metadata = { title: "Воспоминания" };

export default function StoriesPage() {
  return <StoriesView />;
}
