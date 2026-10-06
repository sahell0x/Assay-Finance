"use client";

import { ArrowRight, Check, ExternalLink, FileDown, Link2, Loader2 } from "lucide-react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { VERDICT_TEXT } from "@/components/landing/report-card";
import { Appear, EASE, RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";
import { cn } from "@/lib/cn";
import { formatExact, formatMetric, formatPercentile, formatScore, sourceLabel, titleCase } from "@/lib/format";
import type { AnalysisDetail, Evidence, MetricValue, ShowcaseCard } from "@/lib/types";

/** Ticks while the cell is on screen and stops when it leaves, so off-screen demos cost
 *  nothing. Reduced motion holds every demo on its finished frame. */
function useLoop(ref: React.RefObject<Element | null>, steps: number, ms: number) {
  const reduced = useReducedMotion();
  const inView = useInView(ref, { margin: "-15% 0px" });
  const [i, setI] = React.useState(reduced ? steps - 1 : 0);
  React.useEffect(() => {
    if (reduced || !inView) return;
    const t = setInterval(() => setI((n) => (n + 1) % steps), ms);
    return () => clearInterval(t);
  }, [reduced, inView, steps, ms]);
  return reduced ? steps - 1 : i;
}

function Cell({
  title,
  body,
  href,
  linkLabel,
  className,
  children,
  delay = 0,
}: {
  title: string;
  body: string;
  href?: string;
  linkLabel?: string;
  className?: string;
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <Appear delay={delay} className={cn("flex flex-col overflow-hidden rounded-[20px] border border-rule bg-paper", className)}>
      <div className="relative flex min-h-[15rem] flex-1 items-center justify-center overflow-hidden border-b border-rule bg-surface p-6">
        {children}
      </div>
      <div className="p-6">
        <h3 className="text-[19px] font-semibold tracking-[-0.02em] text-ink">{title}</h3>
        <p className="mt-1.5 max-w-[52ch] text-[15px] leading-relaxed text-ink-muted">{body}</p>
        {href && linkLabel && (
          <Link href={href} className="group mt-4 inline-flex items-center gap-1.5 text-[14px] font-semibold text-ink">
            {linkLabel}
            <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
          </Link>
        )}
      </div>
    </Appear>
  );
}

/** A real metric opening into the formula and the report lines behind it. */
function WorkingDemo({ metric }: { metric: MetricValue }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const step = useLoop(ref, 3, 2200);
  const open = step >= 1;
  const inputs = Object.entries(metric.inputs).slice(0, 3);

  return (
    <div ref={ref} className="w-full max-w-[30rem]">
      <div className="card-soft overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3.5">
          <span className="text-[14px] font-medium text-ink">{metric.label ?? titleCase(metric.name)}</span>
          <span className="flex items-center gap-3">
            {metric.peer_percentile != null && (
              <span className="hidden text-[12px] text-ink-muted sm:inline">
                {formatPercentile(metric.peer_percentile)} of peers
              </span>
            )}
            <span className="nums text-[15px] font-semibold text-ink">{formatMetric(metric)}</span>
          </span>
        </div>
        <motion.div
          initial={false}
          animate={{ height: open ? "auto" : 0 }}
          transition={{ duration: 0.5, ease: EASE }}
          className="overflow-hidden"
        >
          <div className="border-t border-rule bg-surface-sunk/60 px-4 py-3.5">
            <code className="block font-mono text-[12.5px] text-ink">{metric.formula}</code>
            <ul className="mt-3 space-y-1.5">
              {inputs.map(([k, v], i) => (
                <motion.li
                  key={k}
                  initial={false}
                  animate={{ opacity: step === 2 ? 1 : 0.0, x: step === 2 ? 0 : -8 }}
                  transition={{ duration: 0.35, delay: step === 2 ? i * 0.12 : 0 }}
                  className="flex justify-between gap-4 text-[12.5px]"
                >
                  <span className="text-ink-muted">{titleCase(k.replaceAll("_", " "))}</span>
                  <span className="nums text-ink">{formatExact(v)}</span>
                </motion.li>
              ))}
            </ul>
          </div>
        </motion.div>
      </div>
      <p className="mt-3 text-center text-[12px] text-ink-muted">
        {metric.period} figure, from the company&rsquo;s own reports
      </p>
    </div>
  );
}

/** A sentence from a real write-up, with its source sliding out from the citation. */
function SourceDemo({ claim, source }: { claim: string; source: Evidence }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const step = useLoop(ref, 2, 2800);
  return (
    <div ref={ref} className="w-full max-w-[22rem]">
      <p className="text-[15px] leading-relaxed text-ink">
        {claim}{" "}
        <span
          className={cn(
            "rounded px-1 py-0.5 align-[1px] text-[11px] font-semibold transition-colors",
            step === 1 ? "bg-ink text-paper" : "bg-surface-sunk text-ink",
          )}
        >
          {source.label}
        </span>
      </p>
      <AnimatePresence>
        {step === 1 && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.35, ease: EASE }}
            className="card-soft mt-4 p-3.5"
          >
            <p className="flex items-center gap-1.5 text-[12px] text-ink-muted">
              <ExternalLink className="size-3" aria-hidden />
              {sourceLabel(source.source_type)}
              {source.published ? `, ${source.published}` : ""}
            </p>
            <p className="mt-1 line-clamp-2 text-[13px] font-medium text-ink">{source.title ?? source.section}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Each step of a real run ticking off in order. */
function RunDemo({ steps }: { steps: string[] }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const shown = steps.slice(0, 6);
  const step = useLoop(ref, shown.length + 2, 750);
  return (
    <div ref={ref} className="w-full max-w-[17rem]">
      <ul className="space-y-2.5">
        {shown.map((s, i) => {
          const done = i < step;
          const running = i === step;
          return (
            <li key={s} className="flex items-center gap-2.5 text-[14px]">
              <span
                className={cn(
                  "grid size-5 place-items-center rounded-full border transition-colors",
                  done ? "border-ink bg-ink text-paper" : "border-rule text-ink-muted",
                )}
              >
                {done ? (
                  <Check className="size-3" strokeWidth={3} aria-hidden />
                ) : running ? (
                  <Loader2 className="size-3 animate-spin" aria-hidden />
                ) : null}
              </span>
              <span className={cn("transition-colors", done || running ? "text-ink" : "text-ink-muted")}>{s}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Real companies' overall scores, drawn as bars that grow when they come into view. */
function CompareDemo({ cards }: { cards: ShowcaseCard[] }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const seen = useInView(ref, { once: true, margin: "-15% 0px" });
  const sorted = [...cards].filter((c) => c.rating).sort((a, b) => (b.total_score ?? 0) - (a.total_score ?? 0)).slice(0, 5);
  return (
    <div ref={ref} className="w-full max-w-[19rem] space-y-3">
      {sorted.map((c, i) => (
        <div key={c.id} className="grid grid-cols-[3.25rem_minmax(0,1fr)_2.5rem] items-center gap-3 text-[13px]">
          <span className="font-semibold text-ink">{c.ticker}</span>
          <span className="h-2 overflow-hidden rounded-full bg-surface-sunk">
            <motion.span
              className={cn(
                "block h-full rounded-full",
                c.rating === "BUY" ? "bg-buy-fill" : c.rating === "HOLD" ? "bg-hold-fill" : "bg-sell-fill",
              )}
              initial={false}
              animate={{ width: reduced || seen ? `${(c.total_score ?? 0) * 10}%` : "0%" }}
              transition={{ duration: 1, ease: EASE, delay: 0.15 + i * 0.12 }}
            />
          </span>
          <span className={cn("nums text-right font-semibold", VERDICT_TEXT[c.rating!])}>
            {formatScore(c.total_score)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** The share link being copied and the PDF being saved, in turn. */
function ShareDemo({ ticker }: { ticker: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const step = useLoop(ref, 4, 1400);
  return (
    <div ref={ref} className="flex w-full max-w-[17rem] flex-col gap-2.5">
      <div className="flex h-10 items-center gap-2 rounded-lg border border-rule bg-paper px-3 text-[13px] text-ink-muted">
        <Link2 className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate">Public link to the {ticker} report</span>
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        <span
          className={cn(
            "flex h-10 items-center justify-center gap-1.5 rounded-lg text-[13px] font-semibold transition-colors",
            step === 1 ? "bg-ink text-paper" : "border border-rule bg-paper text-ink",
          )}
        >
          {step === 1 ? <Check className="size-3.5" aria-hidden /> : <Link2 className="size-3.5" aria-hidden />}
          {step === 1 ? "Copied" : "Copy link"}
        </span>
        <span
          className={cn(
            "flex h-10 items-center justify-center gap-1.5 rounded-lg text-[13px] font-semibold transition-colors",
            step === 3 ? "bg-ink text-paper" : "border border-rule bg-paper text-ink",
          )}
        >
          {step === 3 ? <Check className="size-3.5" aria-hidden /> : <FileDown className="size-3.5" aria-hidden />}
          {step === 3 ? "Saved" : "PDF"}
        </span>
      </div>
    </div>
  );
}

/** What a run gives you, each shown working on real stored data rather than described. */
export function Capabilities({ analysis, cards }: { analysis: AnalysisDetail | null; cards: ShowcaseCard[] }) {
  const prof = analysis?.blocks?.profitability;
  const metricKey = prof ? (prof.order ?? Object.keys(prof.metrics)).find((k) => prof.metrics[k]?.value != null) : undefined;
  const metric = metricKey ? prof!.metrics[metricKey] : null;
  const source = analysis?.evidence.find((e) => e.title) ?? null;
  const claim = analysis?.memo?.key_drivers?.[0] ?? null;
  const steps = analysis?.pipeline.map((p) => p.label) ?? [];
  const ticker = analysis?.ticker ?? "AAPL";

  return (
    <section aria-labelledby="capabilities-heading" className="border-t border-rule py-24 sm:py-32">
      <div className={CONTAINER}>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:items-end">
          <h2
            id="capabilities-heading"
            className="max-w-[16ch] text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[52px]"
          >
            <RiseText inView text="Nothing taken on trust." />
          </h2>
          <Appear delay={0.15}>
            <p className="text-[17px] leading-relaxed text-ink-muted">
              Every part of a report can be opened up and checked. These are live pieces of
              real reports, not pictures of them.
            </p>
          </Appear>
        </div>

        <div className="mt-14 grid gap-4 lg:grid-cols-3">
          {metric && (
            <Cell
              className="lg:col-span-2"
              title="Every number shows its working"
              body="Around forty measures of profit, debt, growth and value. Open any one to see the formula and the exact lines of the financial reports it came from."
            >
              <WorkingDemo metric={metric} />
            </Cell>
          )}
          {claim && source && (
            <Cell
              delay={0.08}
              title="Every claim has a source"
              body="Statements in the write-up link to the filing or article they came from. Anything without a source is removed before you see it."
            >
              <SourceDemo claim={claim} source={source} />
            </Cell>
          )}
          {steps.length > 0 && (
            <Cell
              title="Watch it work"
              body="While a report runs you see each step as it happens, so you always know what is going on and how long is left."
            >
              <RunDemo steps={steps} />
            </Cell>
          )}
          {cards.length > 1 && (
            <Cell
              delay={0.08}
              title="Compare side by side"
              body="Put up to six companies in one table and see their scores, ratings and fair-value ranges next to each other."
              href="/compare"
              linkLabel="Compare companies"
            >
              <CompareDemo cards={cards} />
            </Cell>
          )}
          <Cell
            delay={0.16}
            title="Download or share"
            body="Save any report as a PDF with its sources, or share a link anyone can open without signing in."
          >
            <ShareDemo ticker={ticker} />
          </Cell>
        </div>

        <Appear className="mt-8 flex flex-wrap gap-x-8 gap-y-3 text-[15px]">
          {[
            { href: "/watchlist", label: "Keep a watchlist" },
            { href: "/history", label: "See each score over time" },
            { href: "/how-it-works", label: "Read how scores are worked out" },
          ].map((l) => (
            <Link key={l.href} href={l.href} className="group inline-flex items-center gap-1.5 font-medium text-ink">
              {l.label}
              <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          ))}
        </Appear>
      </div>
    </section>
  );
}

