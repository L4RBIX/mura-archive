import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev indicator defaults to bottom-left, which is exactly where the
  // desktop rail puts the language switcher — in development it sits on top of
  // it and makes visual verification of the rail impossible. Production is
  // unaffected; this only moves the dev-only overlay out of the way.
  devIndicators: { position: "bottom-right" },
};

export default nextConfig;
