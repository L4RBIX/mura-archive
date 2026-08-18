"use client";

/**
 * The notebook page: large, calm type.
 *
 * Name highlighting used to live here, and it worked by matching words in the
 * transcript against a fixture list of people — a name match into demonstration
 * data, rendered over the user's own recording. Linking a real transcript to an
 * invented person is exactly the confusion this product must not create, so the
 * highlighting is gone rather than reimplemented against the archive: linking
 * text spans to canonical people needs evidence offsets, which Core has and
 * this component was never given.
 */
export function TranscriptReader({ paragraphs }: { paragraphs: string[] }) {
  return (
    <div className="space-y-6">
      {paragraphs.map((paragraph, i) => (
        <p key={i} className="text-section leading-[1.7] tracking-[-0.01em] text-ink/90">
          {paragraph}
        </p>
      ))}
    </div>
  );
}
