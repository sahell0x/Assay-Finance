"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { motion, useInView, useReducedMotion } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { CountUp, LiveShape, ScoreBar, VerdictChip, verdictWord } from "@/components/app/kit";
import { EASE } from "@/components/landing/motion";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import type { Rating, UsageState } from "@/lib/types";

/** Credits left, with a ring that empties as free credits are spent. */
export function CreditsTile({ usage }: { usage: UsageState | undefined }) {
  const reduced = useReducedMotion();
  const ref = React.useRef<SVGSVGElement>(null);
  const seen = useInView(ref, { once: true });
  const share = usage && usage.limit > 0 ? usage.free_remaining / usage.limit : 0;
  const R = 26;
  const C = 2 * Math.PI * R;

  return (
    <div className="flex flex-col rounded-[14px] border border-rule bg-surface p-5">
      <p className="text-[13px] font-medium text-ink-muted">Credits left</p>
      <div className="mt-2 flex items-center justify-between gap-4">
        <p className="text-[34px] font-semibold leading-none tracking-[-0.04em] text-ink">
          {usage ? <CountUp value={usage.remaining} /> : "—"}
        </p>
        <svg ref={ref} viewBox="0 0 64 64" className="size-14 -rotate-90" aria-hidden>
          <circle cx="32" cy="32" r={R} fill="none" stroke="var(--surface-sunk)" strokeWidth="6" />
          <motion.circle
            cx="32"
            cy="32"
            r={R}
            fill="none"
            stroke="var(--ink)"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={C}
            initial={false}
            animate={{ strokeDashoffset: C * (1 - (reduced || seen ? share : 0)) }}
            transition={{ duration: 1.1, ease: EASE, delay: 0.2 }}
          />
        </svg>
      </div>
      <p className="mt-auto pt-3 text-[13px] leading-relaxed text-ink-muted">
        {usage
          ? `${usage.free_remaining} of ${usage.limit} free${usage.paid_credits ? `, plus ${usage.paid_credits} bought` : ""}. `
          : ""}
        {usage?.authenticated && (
          <Link href="/credits" className="font-medium text-ink underline-offset-4 hover:underline">
            {usage.can_buy ? "Buy credits" : "Credits and billing"}
          </Link>
        )}
      </p>
    </div>
  );
}

/** How the finished analyses split between buy, hold and sell, as one stacked bar. */
export function VerdictMixTile({ ratings }: { ratings: Rating[] }) {
  const reduced = useReducedMotion();
  const ref = React.useRef<HTMLDivElement>(null);
  const seen = useInView(ref, { once: true });
  const counts: Record<Rating, number> = { BUY: 0, HOLD: 0, SELL: 0 };
  ratings.forEach((r) => (counts[r] += 1));
  const total = ratings.length;
  const order: Rating[] = ["BUY", "HOLD", "SELL"];
  const fill: Record<Rating, string> = { BUY: "bg-buy-fill", HOLD: "bg-hold-fill", SELL: "bg-sell-fill" };
  const dot: Record<Rating, string> = { BUY: "bg-buy", HOLD: "bg-hold", SELL: "bg-sell" };

  return (
    <div ref={ref} className="flex flex-col rounded-[14px] border border-rule bg-surface p-5">
      <p className="text-[13px] font-medium text-ink-muted">Verdicts so far</p>
      {total === 0 ? (
        <>
          <p className="mt-2 text-[34px] font-semibold leading-none tracking-[-0.04em] text-ink">—</p>
          <p className="mt-auto pt-3 text-[13px] leading-relaxed text-ink-muted">
            Your finished analyses will be split into buy, hold and sell here.
          </p>
        </>
      ) : (
        <>
          <div className="mt-4 flex h-2.5 gap-0.5 overflow-hidden rounded-full bg-surface-sunk">
            {order.map((r, i) =>
              counts[r] ? (
                <motion.span
                  key={r}
                  className={cn("h-full", fill[r])}
                  initial={false}
                  animate={{ width: reduced || seen ? `${(counts[r] / total) * 100}%` : "0%" }}
                  transition={{ duration: 0.9, ease: EASE, delay: 0.15 + i * 0.12 }}
                />
              ) : null,
            )}
          </div>
          <ul className="mt-auto flex flex-wrap gap-x-4 gap-y-1 pt-4 text-[13px]">
            {order.map((r) => (
              <li key={r} className="flex items-center gap-1.5 text-ink-muted">
                <span aria-hidden className={cn("size-2 rounded-full", dot[r])} />
                {verdictWord(r)}
                <span className="nums font-semibold text-ink">{counts[r]}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** Companies the product has already graded, which anyone can open without spending a
 *  credit. Shown on a dashboard that has nothing of its own yet, so a new account lands
 *  on something to read rather than an empty table. */
export function ShowcaseRail() {
  const { data: cards = [] } = useQuery({
    queryKey: ["showcase", 8],
    queryFn: () => api.showcase(8),
    staleTime: 5 * 60_000,
  });
  const graded = cards.filter((c) => c.rating);
  if (graded.length === 0) return null;

  return (
    <section aria-labelledby="showcase-rail" className="mt-12">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h2 id="showcase-rail" className="text-[21px] font-semibold tracking-[-0.025em] text-ink">
            Read a finished report while you wait
          </h2>
          <p className="mt-1 text-[14px] text-ink-muted">
            These companies are already graded. Opening one is free.
          </p>
        </div>
      </div>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {graded.slice(0, 4).map((c, i) => (
          <motion.li
            key={c.id}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, ease: EASE, delay: i * 0.06 }}
          >
            <Link
              href={`/analysis/${c.id}`}
              className="group flex h-full flex-col rounded-[14px] border border-rule bg-surface p-5 transition-[border-color,box-shadow,transform] duration-300 hover:-translate-y-0.5 hover:border-brand-edge hover:shadow-float"
            >
              <div className="flex items-center gap-3">
                <LiveShape scores={c.dimension_scores} rating={c.rating} size={44} delay={i * 0.08} />
                <div className="min-w-0">
                  <p className="nums text-[16px] font-semibold text-ink">{c.ticker}</p>
                  <p className="truncate text-[13px] text-ink-muted">{c.name}</p>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <VerdictChip rating={c.rating!} />
                <span className="nums text-[20px] font-semibold tracking-[-0.03em] text-ink">
                  {formatScore(c.total_score)}
                </span>
              </div>
              <ScoreBar score={c.total_score} rating={c.rating} className="mt-3" delay={i * 0.08} />
              <span className="mt-4 inline-flex items-center gap-1 text-[13px] font-medium text-ink">
                Open report
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </span>
            </Link>
          </motion.li>
        ))}
      </ul>
    </section>
  );
}
