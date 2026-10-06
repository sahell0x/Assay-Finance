import Link from "next/link";

import { verdictWord, VERDICT_TEXT } from "@/components/landing/report-card";
import { ReportShape } from "@/components/report-shape";
import { Marquee } from "@/components/ui/marquee";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import type { ShowcaseCard } from "@/lib/types";

/** A ticker tape of companies that have already been graded, running under the hero.
 *  Each entry is a stored analysis: its report shape, its verdict and its score. It
 *  keeps moving under the pointer, and stands still for anyone who
 *  prefers reduced motion. */
export function TickerTape({ cards }: { cards: ShowcaseCard[] }) {
  const graded = cards.filter((c) => c.rating);
  if (graded.length === 0) return null;
  // A short list would leave the tape mostly empty on a wide screen.
  const repeat = Math.max(4, Math.ceil(12 / graded.length));

  return (
    <section aria-label="Companies already graded" className="relative border-y border-rule bg-surface">
      <Marquee repeat={repeat} className="py-0 [--duration:38s] [--gap:0rem]">
        {graded.map((c) => (
          <Link
            key={c.id}
            href={`/analysis/${c.id}`}
            className="group flex items-center gap-3 border-r border-rule px-6 py-4 transition-colors hover:bg-paper"
          >
            <ReportShape
              scores={c.dimension_scores}
              rating={c.rating}
              size={34}
              labels={false}
              className="transition-transform duration-500 group-hover:rotate-[72deg]"
            />
            <span className="text-[15px] font-semibold text-ink">{c.ticker}</span>
            <span className="hidden max-w-[12rem] truncate text-[13px] text-ink-muted sm:inline">
              {c.name}
            </span>
            <span className={cn("text-[14px] font-semibold", VERDICT_TEXT[c.rating!])}>
              {verdictWord(c.rating!)}
            </span>
            <span className="nums text-[14px] font-semibold text-ink">
              {formatScore(c.total_score)}
            </span>
          </Link>
        ))}
      </Marquee>
      <div aria-hidden className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-surface" />
      <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-surface" />
    </section>
  );
}
