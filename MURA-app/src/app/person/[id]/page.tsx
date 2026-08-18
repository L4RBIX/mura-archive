import type { Metadata } from "next";
import { PersonView } from "@/components/person/person-view";

export const metadata: Metadata = { title: "Person" };

/**
 * A person is addressed by canonical archive id.
 *
 * No `generateStaticParams` any more: the people who exist are the viewer's
 * own family, known only after authentication, so there is no build-time set
 * to prerender and a fixture list would be the wrong one for every user.
 */
export default async function PersonPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PersonView personId={id} />;
}
