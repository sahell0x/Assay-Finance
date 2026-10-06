"use client";

import { ArrowRight } from "lucide-react";
import {
  AnimatePresence,
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "motion/react";
import Link from "next/link";
import * as React from "react";

import { verdictWord, VERDICT_CHIP, VERDICT_TEXT } from "@/components/landing/report-card";
import { EASE } from "@/components/landing/motion";
import { grade, THRESHOLDS } from "@/components/scorecard-rail";
import { cn } from "@/lib/cn";
import { formatCurrency, formatScore } from "@/lib/format";
import { DIMENSIONS, DIMENSION_LABELS, type Rating, type ShowcaseCard } from "@/lib/types";

const CYCLE_MS = 7000;

const ZONE: Record<Rating, string> = {
  SELL: "bg-sell-fill",
  HOLD: "bg-hold-fill",
  BUY: "bg-buy-fill",
};

/** The hero's working specimen. It plays one assay on a real stored analysis: the five
 *  areas are measured one after another, the overall score counts up, the marker slides
 *  along the scale, and only then is the verdict stamped. Then it moves on to the next
 *  company, and keeps going under the pointer; reduced motion shows the finished card and never cycles.
 *
 *  Everything on it comes from the showcase row, so it cannot show a company the product
 *  has not actually analyzed. */
export function LiveCard({ cards }: { cards: ShowcaseCard[] }) {
  const reduced = useReducedMotion();
  const usable = cards.filter((c) => c.rating && typeof c.total_score === "number");
  const [index, setIndex] = React.useState(0);

  React.useEffect(() => {
    if (reduced || usable.length < 2) return;
    const t = setTimeout(() => setIndex((i) => (i + 1) % usable.length), CYCLE_MS);
    return () => clearTimeout(t);
  }, [index, reduced, usable.length]);

  // A gentle tilt that follows the pointer, so the card reads as an object on the page.
  const rx = useSpring(useMotionValue(0), { stiffness: 140, damping: 18 });
  const ry = useSpring(useMotionValue(0), { stiffness: 140, damping: 18 });
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (reduced || e.pointerType !== "mouse") return;
    const r = e.currentTarget.getBoundingClientRect();
    ry.set(((e.clientX - r.left) / r.width - 0.5) * 6);
    rx.set(-((e.clientY - r.top) / r.height - 0.5) * 6);
  };

  const card = usable[index];
  if (!card) return null;

  return (
    <div className="relative [perspective:1400px]">
      <motion.div
        onPointerMove={onMove}
        onPointerLeave={() => {
          rx.set(0);
          ry.set(0);
        }}
        style={{ rotateX: rx, rotateY: ry }}
        initial={reduced ? false : { opacity: 0, y: 40, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 1, ease: EASE, delay: 0.35 }}
        className="card-soft relative overflow-hidden [transform-style:preserve-3d]"
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={card.id}
            initial={reduced ? false : { opacity: 0, filter: "blur(6px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, filter: "blur(6px)" }}
            transition={{ duration: 0.35 }}
          >
            <Assay card={card} reduced={!!reduced} />
          </motion.div>
        </AnimatePresence>

        {usable.length > 1 && (
          <div className="flex items-center gap-1.5 border-t border-rule px-5 py-3">
            {usable.map((c, i) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Show ${c.name ?? c.ticker}`}
                aria-current={i === index}
                className={cn(
                  "relative h-7 overflow-hidden rounded-md px-2 text-[12px] sm:px-2.5 font-semibold transition-colors",
                  i === index ? "bg-surface-sunk text-ink" : "text-ink-muted hover:text-ink",
                )}
              >
                {c.ticker}
                {i === index && !reduced && (
                  <motion.span
                    key={`${c.id}-progress`}
                    aria-hidden
                    className="absolute inset-x-0 bottom-0 h-px origin-left bg-ink"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: CYCLE_MS / 1000, ease: "linear" }}
                  />
                )}
              </button>
            ))}
            <Link
              href={`/analysis/${card.id}`}
              className="group ml-auto flex items-center gap-1 whitespace-nowrap text-[13px] font-medium text-ink"
            >
              Full report
              <ArrowRight
                className="size-3.5 transition-transform group-hover:translate-x-0.5"
                aria-hidden
              />
            </Link>
          </div>
        )}
      </motion.div>
    </div>
  );
}

function Assay({ card, reduced }: { card: ShowcaseCard; reduced: boolean }) {
  const rating = card.rating as Rating;
  const total = card.total_score as number;
  // The bars take 0.9s to measure; the verdict waits for them.
  const verdictAt = reduced ? 0 : 1.35;

  const score = useMotionValue(reduced ? total : 0);
  const shown = useTransform(score, (v) => formatScore(v));
  const left = useTransform(score, (v) => `${Math.max(0, Math.min(100, v * 10))}%`);
  React.useEffect(() => {
    if (reduced) return;
    const c = animate(score, total, { duration: 1.3, ease: EASE, delay: 0.25 });
    return () => c.stop();
  }, [reduced, score, total]);

  return (
    <>
      <div className="flex items-center gap-3 border-b border-rule px-5 py-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-surface-sunk text-[12px] font-semibold text-ink">
          {card.ticker.slice(0, 4)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold text-ink">{card.name ?? card.ticker}</p>
          <p className="truncate text-[13px] text-ink-muted">
            <span className="nums">{formatCurrency(card.price)}</span>
            {card.sector ? `, ${card.sector}` : ""}
          </p>
        </div>
        <motion.span
          initial={reduced ? false : { opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: verdictAt + 0.15, type: "spring", stiffness: 380, damping: 22 }}
          className={cn(
            "ml-auto shrink-0 rounded-md px-2.5 py-1 text-[13px] font-semibold",
            VERDICT_CHIP[rating],
          )}
        >
          {verdictWord(rating)}
        </motion.span>
      </div>

      <div className="grid items-end gap-6 border-b border-rule px-5 py-6 sm:grid-cols-[8.5rem_minmax(0,1fr)]">
        <div>
          <div className="relative h-[50px]">
            {/* Until the verdict lands, the slot says what is happening in it. */}
            <motion.p
              aria-hidden
              initial={reduced ? false : { opacity: 1 }}
              animate={{ opacity: 0 }}
              transition={{ delay: verdictAt, duration: 0.15 }}
              className="absolute inset-0 flex items-end pb-1 text-[15px] font-medium text-ink-muted"
            >
              Measuring…
            </motion.p>
            <motion.p
              initial={reduced ? false : { opacity: 0, scale: 1.35, filter: "blur(8px)" }}
              animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
              transition={{ delay: verdictAt, duration: 0.5, ease: EASE }}
              className={cn(
                "absolute inset-0 origin-bottom-left text-[52px] font-semibold leading-[0.95] tracking-[-0.04em]",
                VERDICT_TEXT[rating],
              )}
            >
              {verdictWord(rating)}
            </motion.p>
          </div>
          <p className="nums mt-2 text-[13px] text-ink-muted">
            <motion.span className="text-[20px] font-semibold text-ink">{shown}</motion.span> / 10
          </p>
        </div>

        <div aria-label={`Overall ${formatScore(total)} out of 10`}>
          <div className="relative h-2">
            <div className="grid h-full grid-cols-[50fr_25fr_25fr] gap-0.5 overflow-hidden rounded-full">
              {(["SELL", "HOLD", "BUY"] as const).map((z) => (
                <span
                  key={z}
                  className={cn(ZONE[z], "transition-opacity", z === rating ? "opacity-100" : "opacity-20")}
                />
              ))}
            </div>
            <motion.span
              aria-hidden
              style={{ left }}
              className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-paper bg-ink shadow-float"
            />
          </div>
          <div className="nums mt-2.5 grid grid-cols-[50fr_25fr_25fr] text-[12px] text-ink-muted">
            <span>Sell</span>
            <span>Hold {THRESHOLDS.hold}+</span>
            <span>Buy {THRESHOLDS.buy}+</span>
          </div>
        </div>
      </div>

      <ul className="px-5 py-2">
        {DIMENSIONS.map((d, i) => {
          const v = card.dimension_scores?.[d];
          const g = typeof v === "number" ? grade(v, THRESHOLDS) : null;
          return (
            <li
              key={d}
              className="grid grid-cols-[7.5rem_minmax(0,1fr)_2rem] items-center gap-3 border-b border-rule py-2.5 text-[13px] text-ink last:border-0 sm:grid-cols-[8.5rem_minmax(0,1fr)_4rem_2rem]"
            >
              {DIMENSION_LABELS[d]}
              <span className="h-1 overflow-hidden rounded-full bg-surface-sunk">
                {g && (
                  <motion.span
                    className={cn("block h-full origin-left rounded-full", g.bar)}
                    style={{ width: `${(v as number) * 10}%` }}
                    initial={reduced ? false : { scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 0.7, ease: EASE, delay: 0.2 + i * 0.12 }}
                  />
                )}
              </span>
              <motion.span
                className="hidden text-[12px] text-ink-muted sm:inline"
                initial={reduced ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6 + i * 0.12 }}
              >
                {g?.word ?? "—"}
              </motion.span>
              <span className="nums text-right font-semibold">
                {typeof v === "number" ? formatScore(v) : "—"}
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}
