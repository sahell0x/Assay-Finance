import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The repo sits below a directory that has its own lockfile; without this Next walks
  // up and picks the wrong workspace root.
  turbopack: { root: __dirname },
  // Produces .next/standalone, which is what the Docker runner stage copies — it keeps
  // the runtime image to the server and its actual dependencies.
  output: "standalone",
  poweredByHeader: false,

  // Baseline hardening for every page. No full Content-Security-Policy yet: it needs
  // nonces for Next's inline scripts, which is a larger change than a header list.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Nothing here is meant to be embedded, so framing is refused outright.
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            // payment is allowed for Razorpay's checkout frame only, which uses the
            // Payment Request API for UPI and saved cards.
            value:
              'camera=(), microphone=(), geolocation=(), payment=(self "https://api.razorpay.com" "https://checkout.razorpay.com")',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
