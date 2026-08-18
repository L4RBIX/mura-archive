import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { AppShell } from "@/components/shell/app-shell";
import { MuraI18nProvider } from "@/lib/i18n";
import { isClerkConfigured } from "@/lib/auth/providers/clerk/config";
import { MuraSessionProvider } from "@/lib/mura/session-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Mura", template: "%s — Mura" },
  description: "Голос вашей семьи. Отбасыңыздың дауысы.",
  applicationName: "Mura",
};

export const viewport: Viewport = {
  themeColor: "#eee8df",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

function Shell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <MuraI18nProvider>
      {/* Session wraps everything, so no screen can render family data before
          the app knows who is signed in and which family they chose. */}
      <MuraSessionProvider>
        <div
          aria-hidden
          className="grain pointer-events-none fixed inset-0 z-50 opacity-[0.05] mix-blend-multiply"
        />
        {/* Navigation, family context and content width live in AppShell.
            The single global `max-w-[430px]` that used to be here is gone: it
            made every window a phone. Each surface now states its own measure. */}
        <AppShell>{children}</AppShell>
      </MuraSessionProvider>
    </MuraI18nProvider>
  );
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // ClerkProvider requires a publishable key and throws without one. An
  // unconfigured deployment still renders, and the proxy reports
  // `auth_provider_unconfigured`, so the UI says so plainly rather than
  // crashing on a missing environment variable.
  const shell = <Shell>{children}</Shell>;
  return (
    <html lang="ru">
      <body>{isClerkConfigured() ? (
          // Canonical location of both flows. Clerk renders the
          // "Нет аккаунта? Создать аккаунт" cross-link only when it knows
          // where the other flow lives; without this it silently hides it.
          <ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up">
            {shell}
          </ClerkProvider>
        ) : (
          shell
        )}</body>
    </html>
  );
}
