"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { CountUp, LiveShape, ScoreBar, Stagger, StaggerItem, VerdictChip } from "@/components/app/kit";
import { EASE } from "@/components/landing/motion";
import { THRESHOLDS } from "@/components/scorecard-rail";
import { cn } from "@/lib/cn";
import { DASH, formatCurrency, formatDate, formatScore } from "@/lib/format";
import { DIMENSIONS, DIMENSION_LABELS, type CompareColumn, type Rating } from "@/lib/types";

/** An area's score coloured the way a report grades it: strong, average or weak. */
function tone(v: number): Rating {
  if (v >= THRESHOLDS.buy) return "BUY";
  if (v >= THRESHOLDS.hold) return "HOLD";
  return "SELL";
}

function priceOf(c: CompareColumn): number | null {
  const p = c.price_target?.inputs?.current_price;
  return typeof p === "number" ? p : null;
}

/** The fair-value range drawn against today's price, on a scale shared by every column
 *  so the ranges can be compared by eye. */
function RangeBar({ c, lo, hi }: { c: CompareColumn; lo: number; hi: number }) {
  const reduced = useReducedMotion();
  const ref = React.useRef<HTMLDivElement>(null);
  const seen = useInView(ref, { once: true });
  const pt = c.price_target;
  const price = priceOf(c);
  if (!pt?.available || pt.low == null || pt.high == null) {
    return <p className="text-[13px] text-ink-muted">Not available for this company</p>;
  }
  const pos = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const show = reduced || seen;
  const cheap = price !== null && price < pt.low;
  const dear = price !== null && price > pt.high;

  return (
    <div ref={ref}>
      <div className="relative h-6">
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-rule" />
        <motion.div
          className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-ink/80"
          style={{ left: pos(pt.low), width: `calc(${pos(pt.high)} - ${pos(pt.low)})`, transformOrigin: "left" }}
          initial={false}
          animate={{ scaleX: show ? 1 : 0 }}
          transition={{ duration: 0.8, ease: EASE, delay: 0.1 }}
        />
        {price !== null && (
          <motion.div
            className="absolute top-0 h-6 w-0.5 -translate-x-1/2 rounded-full bg-ink"
            initial={false}
            animate={{ left: show ? pos(price) : pos(lo), opacity: show ? 1 : 0 }}
            transition={{ duration: 1, ease: EASE, delay: 0.3 }}
          />
        )}
      </div>
      <p className="nums mt-1.5 text-[13px] text-ink">
        {formatCurrency(pt.low)} to {formatCurrency(pt.high)}
      </p>
      {price !== null && (
        <p className="nums text-[12px] text-ink-muted">
          Price {formatCurrency(price)}
          {cheap ? ", below the range" : dear ? ", above the range" : ", inside the range"}
        </p>
      )}
    </div>
  );
}

function Row({
  grid,
  label,
  hint,
  children,
}: {
  grid: React.CSSProperties;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid border-t border-rule" style={grid}>
      <div className="sticky left-0 z-10 bg-surface px-4 py-4 sm:px-5">
        <p className="text-[14px] font-medium text-ink">{label}</p>
        {hint && <p className="mt-0.5 text-[12px] text-ink-muted">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

/** Companies side by side. One column per company and one row per question, so the
 *  eye reads across a row to compare. The best score in a row is set heavier; colour
 *  keeps meaning only "strong, average or weak", as it does in a report. */
export function CompareBoard({ columns }: { columns: CompareColumn[] }) {
  const n = columns.length;
  const grid = { gridTemplateColumns: `minmax(8.5rem,10rem) repeat(${n}, minmax(11rem, 1fr))` };

  // One price scale for every fair-value bar.
  const values = columns.flatMap((c) => {
    const pt = c.price_target;
    const p = priceOf(c);
    return [pt?.available ? pt.low : null, pt?.available ? pt.high : null, p].filter(
      (v): v is number => typeof v === "number",
    );
  });
  const lo = values.length ? Math.min(...values) * 0.9 : 0;
  const hi = values.length ? Math.max(...values) * 1.05 : 1;

  const best = (dim: string) => Math.max(...columns.map((c) => c.dimension_scores?.[dim] ?? -1));
  const bestTotal = Math.max(...columns.map((c) => c.total ?? -1));

  return (
    <div className="overflow-hidden rounded-[20px] border border-rule bg-surface">
      <div className="thin-scroll overflow-x-auto">
        <div className="min-w-max">
          {/* Company headers. */}
          <div className="grid" style={grid}>
            <div className="sticky left-0 z-10 bg-surface" />
            {columns.map((c, i) => (
              <motion.div
                key={c.ticker}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: EASE, delay: i * 0.08 }}
                className="border-l border-rule px-4 py-5 sm:px-5"
              >
                <div className="flex items-center gap-3">
                  <LiveShape scores={c.dimension_scores} rating={c.rating} size={52} delay={0.2 + i * 0.08} />
                  <div className="min-w-0">
                    <Link
                      href={`/analysis/${c.analysis_id}`}
                      className="nums block text-[20px] font-semibold tracking-[-0.02em] text-ink underline-offset-4 hover:underline"
                    >
                      {c.ticker}
                    </Link>
                    {c.rating && <VerdictChip rating={c.rating} size="sm" className="mt-1" />}
                  </div>
                </div>
                <p className="mt-4 flex items-baseline gap-1">
                  <CountUp
                    value={c.total ?? 0}
                    format={(v) => formatScore(v)}
                    className={cn(
                      "text-[34px] leading-none tracking-[-0.04em] text-ink",
                      c.total === bestTotal && n > 1 ? "font-bold" : "font-semibold",
                    )}
                  />
                  <span className="text-[13px] text-ink-muted">/ 10</span>
                </p>
                <p className="mt-1 text-[12px] text-ink-muted">
                  {c.total === bestTotal && n > 1 ? "Highest overall, " : ""}
                  analyzed {formatDate(c.completed_at)}
                </p>
              </motion.div>
            ))}
          </div>

          {DIMENSIONS.map((dim, r) => {
            const top = best(dim);
            return (
              <Row key={dim} grid={grid} label={DIMENSION_LABELS[dim]}>
                {columns.map((c, i) => {
                  const v = c.dimension_scores?.[dim];
                  const has = typeof v === "number";
                  const isBest = has && v === top && n > 1;
                  return (
                    <div key={c.ticker} className="flex items-center gap-3 border-l border-rule px-4 py-4 sm:px-5">
                      <ScoreBar
                        score={has ? v : null}
                        rating={has ? tone(v) : null}
                        className="flex-1"
                        delay={0.1 + r * 0.06 + i * 0.04}
                      />
                      <span
                        className={cn(
                          "nums w-9 text-right text-[15px] text-ink",
                          isBest ? "font-bold" : "font-medium text-ink-soft",
                        )}
                        title={isBest ? "Best in this row" : undefined}
                      >
                        {has ? formatScore(v) : DASH}
                      </span>
                    </div>
                  );
                })}
              </Row>
            );
          })}

          <Row grid={grid} label="Fair value" hint="Range, with today's price as the line">
            {columns.map((c) => (
              <div key={c.ticker} className="border-l border-rule px-4 py-4 sm:px-5">
                <RangeBar c={c} lo={lo} hi={hi} />
              </div>
            ))}
          </Row>
        </div>
      </div>
    </div>
  );
}

/** Each company's case in its own words, and the risks it names first. */
export function CompareTheses({ columns }: { columns: CompareColumn[] }) {
  return (
    <Stagger as="div" className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3" gap={0.07}>
      {columns.map((c) => (
        <StaggerItem as="div" key={c.ticker} className="rounded-[20px] border border-rule bg-paper p-6">
          <div className="flex items-center gap-2.5">
            <span className="nums text-[16px] font-semibold text-ink">{c.ticker}</span>
            {c.rating && <VerdictChip rating={c.rating} size="sm" />}
          </div>
          {c.thesis && (
            <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
              {c.thesis.replace(/\s?\[S\d{1,2}\]/g, "")}
            </p>
          )}
          {c.key_risks?.length ? (
            <>
              <p className="mt-5 text-[13px] font-semibold text-ink">What could go wrong</p>
              <ul className="mt-2 space-y-2">
                {c.key_risks.map((r, i) => (
                  <li key={i} className="border-l-2 border-sell-fill/60 pl-3 text-[14px] leading-relaxed text-ink-muted">
                    {r.replace(/\s?\[S\d{1,2}\]/g, "")}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </StaggerItem>
      ))}
    </Stagger>
  );
}
