"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { LiveCard } from "@/components/landing/live-card";
import { EASE, RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";
import { useTickerCommand } from "@/components/ticker-command";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { ShowcaseCard } from "@/lib/types";

/** A price line that is drawn across the hero as the page opens. It is the same rising
 *  line as the logo's crossbar, at the scale of the page, and it is the only decoration
 *  in the hero. Fixed points so server and client draw the same path. */
const LINE = [
  59, 60, 59, 58, 56, 55, 57, 57, 58, 58, 58, 58, 55, 56, 56, 57, 54, 50, 49, 47, 47, 47,
  47, 46, 46, 46, 45, 47, 48, 49, 50, 50, 49, 49, 49, 49, 48, 46, 45, 47, 45, 45, 45, 42,
  42, 44, 40, 39, 39, 37, 37, 37, 34, 35, 35, 37, 37, 36, 34, 30, 30, 29, 28, 25, 23, 22,
  24, 20, 17, 17, 19, 20, 16, 12, 12, 10, 8, 9, 11, 11, 10, 11, 13, 13, 14, 14, 11, 13, 14,
  15, 11, 10, 10, 8, 8, 9
];

function linePath(w: number, h: number) {
  const step = w / (LINE.length - 1);
  return LINE.map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${((v / 70) * h).toFixed(1)}`).join(" ");
}

/** The opening: the question every visitor arrives with, a place to type, and beside it
 *  a real report being worked out. The chips under the search open companies that have
 *  already been analyzed, which costs nothing. */
export function Hero({ cards }: { cards: ShowcaseCard[] }) {
  const command = useTickerCommand();
  const reduced = useReducedMotion();
  const ref = React.useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  // The card drifts up a little faster than the page as you leave the hero.
  const lift = useTransform(scrollYProgress, [0, 1], [0, reduced ? 0 : -80]);

  const { data: usage } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    retry: false,
    staleTime: 60_000,
  });

  const free = usage?.authenticated ? null : (usage?.remaining ?? null);

  const fade = (delay: number) => ({
    initial: reduced ? false : { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.8, ease: EASE, delay },
  });

  return (
    <section ref={ref} aria-labelledby="hero-title" className="relative overflow-hidden">
      <svg
        aria-hidden
        viewBox="0 0 1440 420"
        preserveAspectRatio="none"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[55%] w-full"
      >
        <defs>
          <linearGradient id="hero-line-fade" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="var(--ink)" stopOpacity="0.05" />
            <stop offset="1" stopColor="var(--ink)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <motion.path
          d={`${linePath(1440, 420)} L1440,420 L0,420 Z`}
          fill="url(#hero-line-fade)"
          initial={reduced ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.6, duration: 1.2 }}
        />
        <motion.path
          d={linePath(1440, 420)}
          fill="none"
          stroke="var(--ink)"
          strokeOpacity="0.14"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
          initial={reduced ? false : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 2.4, ease: [0.65, 0, 0.35, 1], delay: 0.2 }}
        />
      </svg>

      <div
        className={cn(
          CONTAINER,
          "relative grid items-center gap-12 pb-24 pt-14 sm:pt-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,32rem)] lg:gap-16 lg:pb-32",
        )}
      >
        <div>
          <motion.p className="pill" {...fade(0)}>
            <span aria-hidden className="size-1.5 rounded-full" />
            {free === null
              ? "Free to try, no card needed"
              : free > 0
                ? `${free} free ${free === 1 ? "report" : "reports"}, no sign-up`
                : "Free reports used. Sign up for 10 more"}
          </motion.p>

          <h1
            id="hero-title"
            className="mt-6 text-[44px] font-semibold leading-[1.02] tracking-[-0.045em] text-ink sm:text-[64px] xl:text-[76px]"
          >
            <RiseText text="Know if a stock" delay={0.1} />
            <RiseText text="is worth buying." delay={0.28} />
          </h1>

          <motion.p
            {...fade(0.55)}
            className="mt-6 max-w-[46ch] text-[18px] leading-[1.55] text-ink-muted"
          >
            A clear buy, hold or sell call on any US company in about two minutes. Every
            number computed from its filings, every claim linked to a source.
          </motion.p>

          <motion.div {...fade(0.7)} className="mt-8 flex max-w-[32rem] flex-col gap-2.5 sm:flex-row">
            <button
              type="button"
              onClick={command.open}
              className="group flex h-12 w-full items-center gap-2.5 rounded-lg border border-rule bg-paper px-3.5 text-left text-[15px] text-ink-muted shadow-raise transition-[border-color,box-shadow] hover:border-brand-edge hover:shadow-float sm:w-auto sm:flex-1"
            >
              <Search className="size-4 shrink-0 transition-transform group-hover:scale-110" />
              Apple, Tesla, NVDA…
              <kbd className="ml-auto hidden rounded border border-rule px-1.5 font-sans text-[11px] sm:inline">
                ⌘K
              </kbd>
            </button>
            <Button size="xl" className="h-12" onClick={command.open}>
              Analyze
            </Button>
          </motion.div>

          {cards.length > 0 && (
            <motion.div {...fade(0.85)} className="mt-5 flex flex-wrap items-center gap-2 text-[13px]">
              <span className="text-ink-muted">Already analyzed:</span>
              {cards.slice(0, 5).map((c) => (
                <Link
                  key={c.id}
                  href={`/analysis/${c.id}`}
                  className="rounded-md border border-rule bg-paper px-2 py-0.5 font-medium text-ink transition-[border-color,transform] hover:-translate-y-px hover:border-brand-edge"
                >
                  {c.ticker}
                </Link>
              ))}
            </motion.div>
          )}
        </div>

        <motion.div style={{ y: lift }}>
          <LiveCard cards={cards} />
        </motion.div>
      </div>
    </section>
  );
}
