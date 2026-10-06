import type { MetadataRoute } from "next";

/** Public pages may be indexed; personal pages and individual analyses may not. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: ["/", "/how-it-works", "/m/"],
      disallow: ["/dashboard", "/history", "/watchlist", "/compare", "/analysis/", "/api/"],
    },
  };
}
