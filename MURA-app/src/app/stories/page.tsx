import type { Metadata } from "next";
import { StoriesView } from "@/components/story/stories-view";

export const metadata: Metadata = { title: "Memories" };

export default function StoriesPage() {
  return <StoriesView />;
}
