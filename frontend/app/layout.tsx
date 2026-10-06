import type { Metadata, Viewport } from "next";
import { Instrument_Sans, Newsreader } from "next/font/google";

import { Providers } from "@/components/providers";
import { SiteChrome } from "@/components/site-chrome";

import "./globals.css";

/* Instrument Sans carries the whole interface — a crisp neutral grotesk with true
   tabular figures from a 13px table cell up to the composite score.
   Newsreader sets the memo body, the one surface that is read rather than scanned. */
const instrument = Instrument_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-instrument",
  display: "swap",
});

const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-newsreader",
  display: "swap",
  // Only analysis pages use the serif; preloading it everywhere wasted a download.
  preload: false,
});

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
  ],
};

export const metadata: Metadata = {
  title: {
    default: "Assay — know if a stock is worth buying",
    template: "%s | Assay",
  },
  description:
    "Pick any US-listed company and get a clear buy, hold or sell view in about two minutes, with every number taken from its financial reports and every claim linked to its source.",
  openGraph: {
    title: "Assay — know if a stock is worth buying",
    description:
      "Pick a company and get a clear buy, hold or sell view in about two minutes. Free, no account needed.",
    type: "website",
    siteName: "Assay",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: next-themes writes the class on <html> before React
    // hydrates, which is the whole point — it is what stops the light-theme flash.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${instrument.variable} ${newsreader.variable}`}
    >
      <body>
        <Providers>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-base focus:shadow-float"
          >
            Skip to content
          </a>
          <SiteChrome>{children}</SiteChrome>
        </Providers>
      </body>
    </html>
  );
}
