"use client";

import { motion, useReducedMotion } from "motion/react";

import { CountUp } from "@/components/app/kit";
import { ReportScale } from "@/components/app/report-scale";
import { EASE } from "@/components/landing/motion";
import { Hint } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { formatCurrency, formatScore } from "@/lib/format";
import type { PriceTarget, Rating, Scorecard } from "@/lib/types";

const TONE: Record<Rating, { text: string; wash: string; edge: string; word: string }> = {
  BUY: { text: "text-buy", wash: "var(--buy-wash)", edge: "border-buy/20", word: "Buy" },
  HOLD: { text: "text-hold", wash: "var(--hold-wash)", edge: "border-hold/20", word: "Hold" },
  SELL: { text: "text-sell", wash: "var(--sell-wash)", edge: "border-sell/20", word: "Sell" },
};

/** The verdict: the one memorable element on the page.
 *
 *  Order is the order a reader asks: what is the call, what does that mean in plain
 *  words, how close was it, and what are the shares worth. The rating word is the
 *  largest thing and carries the verdict colour; everything else stays quiet so it can.
 */
export function RatingBlock({
  scorecard,
  priceTarget,
  price,
  summary,
  asOf,
}: {
  scorecard: Scorecard;
  priceTarget?: PriceTarget | null;
  price?: number | null;
  summary?: string | null;
  asOf?: string | null;
  cached?: boolean;
  cachedAt?: string | null;
}) {
  const reduced = useReducedMotion();
  const rating = scorecard.rating;
  const tone = TONE[rating];
  const rise = (delay: number) => ({
    initial: reduced ? false : { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6, ease: EASE, delay },
  });
  const target = priceTarget ?? scorecard.price_target;
  const edge = scorecard.distance_to_edge;
  const coverage = Math.round((scorecard.coverage ?? 0) * 100);
  const hasTarget = target?.available && target.low !== null && target.high !== null;

  let position: { word: string; cls: string } | null = null;
  if (hasTarget && price !== null && price !== undefined) {
    if (price > target!.high!) position = { word: "Looks expensive", cls: "text-sell" };
    else if (price < target!.low!) position = { word: "Looks cheap", cls: "text-buy" };
    else position = { word: "Fairly priced", cls: "text-hold" };
  }

  return (
    <section aria-label={`Our view: ${tone.word}`} className="space-y-4">
      {/* A plain bordered card: the verdict word carries the colour, nothing else does. */}
      <motion.div {...rise(0)} className="rounded-[14px] border border-rule bg-surface p-5 sm:p-7">
        <div className="grid gap-x-10 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
          <div className="min-w-0">
            <p className="pill">Our view</p>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-5 gap-y-1">
              {/* The verdict is stamped once the score has counted up to it. */}
              <motion.p
                initial={reduced ? false : { opacity: 0, scale: 1.25, filter: "blur(10px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                transition={{ duration: 0.55, ease: EASE, delay: reduced ? 0 : 0.9 }}
                className={cn("mt-3 origin-bottom-left font-semibold leading-[0.9]", tone.text)}
                style={{ fontSize: "clamp(3.25rem, 8vw, 5.5rem)", letterSpacing: "-0.045em" }}
              >
                {tone.word}
              </motion.p>
              <p className="nums text-ink">
                <span className="text-page font-semibold tracking-tight">
                  {scorecard.total === null ? (
                    formatScore(scorecard.total)
                  ) : (
                    <CountUp value={scorecard.total} format={formatScore} />
                  )}
                </span>
                <span className="text-lead text-ink-soft"> out of 10</span>
              </p>
            </div>
            {summary && (
              <motion.p {...rise(0.5)} className="mt-4 max-w-[62ch] text-lead leading-relaxed text-ink">
                {summary}
              </motion.p>
            )}
          </div>

          <div className="self-end">
            <ReportScale total={scorecard.total} thresholds={scorecard.thresholds} rating={rating} />
            <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-small text-ink-soft">
              <Hint label="How clearly the score sits inside this rating rather than near the edge of another.">
                <div tabIndex={0} className="cursor-help">
                  <dt className="inline">Confidence </dt>
                  <dd className="inline font-semibold capitalize text-ink">
                    {scorecard.conviction}
                  </dd>
                </div>
              </Hint>
              {edge !== null && edge !== undefined && (
                <Hint label="How far the score would have to move to change the rating.">
                  <div tabIndex={0} className="cursor-help">
                    <dd className="nums inline font-semibold text-ink">
                      {edge < 0.1 ? "Less than 0.1" : edge.toFixed(1)}
                    </dd>
                    <dt className="inline"> points from the next rating</dt>
                  </div>
                </Hint>
              )}
              <Hint label="How much of the data needed for the score was available for this company.">
                <div tabIndex={0} className="cursor-help">
                  <dt className="inline">Data found </dt>
                  <dd className="nums inline font-semibold text-ink">{coverage}%</dd>
                </div>
              </Hint>
            </dl>
          </div>
        </div>
      </motion.div>

      {/* Price against value: the second question everyone asks. */}
      <motion.div {...rise(0.15)} className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Fact
          label="Fair value range"
          hint="What one share would be worth if the market valued this company the way it values similar companies."
          value={
            hasTarget ? (
              <>
                {formatCurrency(target!.low)}
                <span className="px-1 font-normal text-muted-foreground">to</span>
                {formatCurrency(target!.high)}
              </>
            ) : (
              <span className="text-lead font-normal text-muted-foreground">Not enough data</span>
            )
          }
          note={
            position && price != null ? (
              <>
                <span className={cn("font-semibold", position.cls)}>{position.word}</span>
                <span className="text-muted-foreground">
                  {" "}
                  at today&rsquo;s price of {formatCurrency(price)}
                </span>
              </>
            ) : null
          }
        />
        <Fact label="Analyzed on" value={asOf ?? "—"} />
      </motion.div>
    </section>
  );
}

function Fact({
  label,
  value,
  note,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  hint?: string;
}) {
  const title = <p className="text-small font-medium text-muted-foreground">{label}</p>;
  return (
    <div className="panel px-4 py-3">
      {hint ? (
        <Hint label={hint}>
          <span tabIndex={0} className="cursor-help underline decoration-rule decoration-dotted underline-offset-4">
            {title}
          </span>
        </Hint>
      ) : (
        title
      )}
      <p className="nums mt-0.5 text-section font-semibold tracking-tight text-ink">{value}</p>
      {note && <p className="mt-0.5 text-small">{note}</p>}
    </div>
  );
}
