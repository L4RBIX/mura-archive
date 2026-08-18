/**
 * One definition of where a user can go.
 *
 * Both the mobile bar and the desktop rail read this, so the two can never
 * drift into offering different destinations — which is the usual way a
 * responsive app ends up with two navigations that disagree.
 */

import { BookOpen, Home, Mic, Settings2, Trees } from "lucide-react";
import type { TranslationKey } from "@/lib/i18n";

export interface NavItem {
  href: string;
  labelKey: TranslationKey;
  icon: typeof Home;
  /** The action the product is built around; rendered with emphasis. */
  primary?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/home", labelKey: "navHome", icon: Home },
  { href: "/tree", labelKey: "navFamily", icon: Trees },
  { href: "/record", labelKey: "navRecord", icon: Mic, primary: true },
  // Stories replaces Ask in the primary bar. Ask is still a demonstration and
  // reachable from home; the archive of real memories has more claim to a tab
  // than a preview does.
  { href: "/stories", labelKey: "navStories", icon: BookOpen },
  { href: "/settings", labelKey: "navSettings", icon: Settings2 },
];

/**
 * Routes that deliberately have no navigation.
 *
 * Two different reasons, both deliberate. The landing and auth pages are not
 * inside the product yet, so a tab bar would offer doors that lead nowhere.
 * Record and processing are the opposite: the user is mid-task, often sitting
 * with the person whose story they are capturing, and a bar inviting them
 * elsewhere is exactly the wrong thing to put on screen. Both keep their own
 * back affordance.
 */
const CHROMELESS = ["/", "/sign-in", "/sign-up", "/record", "/processing"];

/**
 * Screens the user reaches before the product has started.
 *
 * These are the only ones that still float a language switcher: there is no
 * rail and no Settings behind them yet, so nothing else could offer the choice.
 */
const PRE_PRODUCT = ["/", "/sign-in", "/sign-up"];

export function isPreProduct(pathname: string | null): boolean {
  if (!pathname) return false;
  if (pathname === "/") return true;
  return PRE_PRODUCT.some((route) => route !== "/" && pathname.startsWith(route));
}

export function hasAppChrome(pathname: string | null): boolean {
  if (!pathname) return false;
  if (pathname === "/") return false;
  return !CHROMELESS.some((route) => route !== "/" && pathname.startsWith(route));
}

/** A tab is current when its section is, so `/person/x` still lights «Семья». */
export function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/home") return pathname === "/home";
  if (href === "/tree") return pathname.startsWith("/tree") || pathname.startsWith("/person");
  // A story is reached from the memories list and belongs to that section.
  if (href === "/stories") return pathname.startsWith("/stories") || pathname.startsWith("/story");
  return pathname.startsWith(href);
}
