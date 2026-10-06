import Link from "next/link";

import { Brand } from "@/components/brand";
import { CONTAINER } from "@/components/landing/shared";
import { ThemeSwitch } from "@/components/theme-toggle";
import { cn } from "@/lib/cn";

const COLUMNS: { heading: string; links: { label: string; href: string }[] }[] = [
  {
    heading: "Product",
    links: [
      { label: "New analysis", href: "/analyze" },
      { label: "Dashboard", href: "/dashboard" },
      { label: "Watchlist", href: "/watchlist" },
      { label: "Compare", href: "/compare" },
    ],
  },
  {
    heading: "Learn",
    links: [
      { label: "How it works", href: "/how-it-works" },
      { label: "Example report", href: "/#showcase" },
      { label: "History", href: "/history" },
    ],
  },
  {
    heading: "Account",
    links: [
      { label: "Sign in", href: "/login" },
      { label: "Create account", href: "/signup" },
      { label: "Credits", href: "/credits" },
    ],
  },
];

/** The full footer for the pages a visitor reads; `slim` for the pages they work in. */
export function SiteFooter({ slim = false }: { slim?: boolean }) {
  const year = new Date().getFullYear();

  if (slim) {
    return (
      <footer className="mt-10 border-t border-rule">
        <div className="mx-auto flex max-w-[80rem] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-6 sm:px-6 lg:px-8">
          <Brand className="text-[15px] font-bold" markClassName="size-5" />
          <p className="max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
            Figures come from companies&rsquo; official financial reports. For information
            only &mdash; this is not investment advice.
          </p>
          <div className="ml-auto flex items-center gap-4">
            <Link href="/how-it-works" className="text-[13px] text-ink-muted hover:text-ink">
              How it works
            </Link>
            <ThemeSwitch />
          </div>
        </div>
      </footer>
    );
  }

  return (
    <footer className="border-t border-rule">
      <div className={cn(CONTAINER, "py-14 sm:py-16")}>
        <div className="grid gap-12 lg:grid-cols-[minmax(0,1.3fr)_repeat(3,minmax(0,1fr))]">
          <div className="max-w-[36ch]">
            <Brand className="text-[19px] font-bold" markClassName="size-6" />
            <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
              A plain-English report card for any US company. Every number computed from
              its filings, every claim linked to a source.
            </p>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.heading} aria-label={col.heading}>
              <p className="text-[13px] font-medium text-ink">{col.heading}</p>
              <ul className="mt-4 flex flex-col gap-3">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      href={l.href}
                      className="text-[14px] text-ink-muted transition-colors hover:text-ink"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-rule pt-6 text-[13px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span className="flex items-center gap-4">
            © {year} Assay
            <ThemeSwitch />
          </span>
          <span className="max-w-[70ch] leading-relaxed sm:text-right">
            Figures come from companies&rsquo; official financial reports. Ratings follow the
            same fixed rules for every company. For information only &mdash; this is not
            investment advice.
          </span>
        </div>
      </div>
    </footer>
  );
}
