"use client";

import { motion, useReducedMotion } from "motion/react";

import { EASE } from "@/components/landing/motion";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import type { Rating } from "@/lib/types";

const ZONE: Record<Rating, { on: string; off: string; text: string }> = {
  SELL: { on: "bg-sell-fill", off: "bg-sell-fill/20", text: "text-sell" },
  HOLD: { on: "bg-hold-fill", off: "bg-hold-fill/20", text: "text-hold" },
  BUY: { on: "bg-buy-fill", off: "bg-buy-fill/20", text: "text-buy" },
};

function fmt(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/** The report's sell/hold/buy scale. Same drawing as the shared BandRule, but the
 *  marker travels in from zero to where the score landed when the report opens, and the
 *  zone it lands in lights up as it arrives. */
export function ReportScale({
  total,
  thresholds,
  rating,
}: {
  total: number | null;
  thresholds: { buy: number; hold: number };
  rating: Rating;
}) {
  const reduced = useReducedMotion();
  const pct = (v: number) => Math.max(0, Math.min(100, (v / 10) * 100));
  const holdAt = pct(thresholds.hold);
  const buyAt = pct(thresholds.buy);
  const markerAt = total === null ? null : pct(total);
  const travel = { duration: reduced ? 0 : 1.4, ease: EASE, delay: reduced ? 0 : 0.3 };

  const zones: { key: Rating; from: number; to: number; label: string; range: string }[] = [
    { key: "SELL", from: 0, to: holdAt, label: "Sell", range: `below ${fmt(thresholds.hold)}` },
    { key: "HOLD", from: holdAt, to: buyAt, label: "Hold", range: `${fmt(thresholds.hold)} to ${fmt(thresholds.buy)}` },
    { key: "BUY", from: buyAt, to: 100, label: "Buy", range: `above ${fmt(thresholds.buy)}` },
  ];

  return (
    <div className="w-full">
      <div className="relative h-7">
        {markerAt !== null && (
          <motion.span
            className="nums absolute bottom-1 -translate-x-1/2 whitespace-nowrap text-base font-semibold text-ink"
            initial={reduced ? false : { left: "0%", opacity: 0 }}
            animate={{ left: `${markerAt}%`, opacity: 1 }}
            transition={travel}
          >
            {formatScore(total)}
          </motion.span>
        )}
      </div>

      <div className="relative flex h-3 w-full gap-[3px]">
        {zones.map((z) => (
          <span
            key={z.key}
            aria-hidden
            className="relative h-full overflow-hidden first:rounded-l-full last:rounded-r-full"
            style={{ width: `${z.to - z.from}%` }}
          >
            <span className={cn("absolute inset-0", ZONE[z.key].off)} />
            {z.key === rating && (
              <motion.span
                className={cn("absolute inset-0", ZONE[z.key].on)}
                initial={reduced ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: reduced ? 0 : 1.2 }}
              />
            )}
          </span>
        ))}
        {markerAt !== null && (
          <motion.span
            aria-label={`Score ${formatScore(total)} out of 10`}
            role="img"
            className="absolute top-1/2 size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-surface bg-ink shadow-raise"
            initial={reduced ? false : { left: "0%" }}
            animate={{ left: `${markerAt}%` }}
            transition={travel}
          />
        )}
      </div>

      <div className="mt-2.5 flex w-full gap-[3px] text-small">
        {zones.map((z) => (
          <span key={z.key} className="min-w-0" style={{ width: `${z.to - z.from}%` }}>
            <span className={cn("block font-semibold", z.key === rating ? ZONE[z.key].text : "text-muted-foreground")}>
              {z.label}
            </span>
            <span className="nums block truncate text-micro text-muted-foreground">{z.range}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
