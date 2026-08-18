import type { Metadata } from "next";
import { HomeView } from "@/components/home/home-view";

export const metadata: Metadata = { title: "Today" };

export default function HomePage() {
  return <HomeView />;
}
