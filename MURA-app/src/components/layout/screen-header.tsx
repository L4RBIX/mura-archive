import { BackButton } from "./back-button";

interface ScreenHeaderProps {
  title?: string;
  fallbackHref?: string;
  /** Rendered on the right edge; a spacer keeps the title centered otherwise. */
  right?: React.ReactNode;
}

export function ScreenHeader({ title, fallbackHref, right }: ScreenHeaderProps) {
  return (
    // The three-column grid keeps the title optically centred no matter how
    // wide the right slot grows, so a running timer can never crowd or clip it.
    <header className="grid grid-cols-[minmax(44px,1fr)_auto_minmax(44px,1fr)] items-center gap-2 px-5 pb-2 pt-screen">
      <BackButton fallbackHref={fallbackHref} />
      {title ? (
        <span className="truncate text-center text-body font-semibold text-ink/60">
          {title}
        </span>
      ) : (
        <span aria-hidden />
      )}
      <div className="flex justify-end">
        {right ?? <span aria-hidden className="size-11" />}
      </div>
    </header>
  );
}
