import Link from "next/link";

/**
 * Sign-in through Supabase.
 *
 * A link, not a client-side SDK call. The whole OAuth round trip happens on the
 * server — `/api/auth/start` mints the PKCE verifier into an httpOnly cookie and
 * `/api/auth/callback` exchanges the code — so this component never touches a
 * token and there is nothing here for a script on the page to read.
 */

const PROVIDERS = [
  { id: "google", label: "Продолжить с Google" },
] as const;

export function SupabaseSignIn({ redirectTo }: { redirectTo: string }) {
  return (
    <div className="w-full max-w-form">
      <h1 className="text-section font-semibold tracking-[-0.02em]">Вход в архив</h1>
      <p className="mt-3 max-w-measure text-body leading-relaxed text-muted">
        Архив открыт только участникам вашей семьи. Мы используем вашу учётную
        запись, чтобы узнать вас, — и больше ни для чего.
      </p>

      <div className="mt-8 space-y-3">
        {PROVIDERS.map((provider) => (
          <Link
            key={provider.id}
            href={`/api/auth/start?provider=${provider.id}&next=${encodeURIComponent(redirectTo)}`}
            className="flex h-14 w-full items-center justify-center gap-3 rounded-control bg-ink-deep px-6 text-item font-semibold text-raised transition-opacity hover:opacity-90 focus-ring"
          >
            <GoogleMark />
            {provider.label}
          </Link>
        ))}
      </div>

      <p className="mt-6 text-meta leading-relaxed text-muted">
        Продолжая, вы соглашаетесь, что записи и расшифровки хранятся в вашем
        семейном архиве.
      </p>
    </div>
  );
}

/** Google's mark, at its official proportions. */
function GoogleMark() {
  return (
    <svg aria-hidden viewBox="0 0 18 18" className="size-5 shrink-0">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}
