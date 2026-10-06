"use client";

import { Banknote, HeartPulse, MessageCircle, Scale, Sprout, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import * as React from "react";

import { verdictWord, VERDICT_TEXT } from "@/components/landing/report-card";
import { Appear, EASE, RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";
import { grade, THRESHOLDS } from "@/components/scorecard-rail";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import { DIMENSIONS, DIMENSION_LABELS, type Rating, type ShowcaseCard } from "@/lib/types";

const AREAS: Record<(typeof DIMENSIONS)[number], { Icon: LucideIcon; question: string; body: string }> = {
  profitability: {
    Icon: Banknote,
    question: "Does it make money?",
    body: "Margins and returns on the money invested in the business.",
  },
  financial_health: {
    Icon: HeartPulse,
    question: "Can it pay its bills?",
    body: "Debt, interest cover and the cash it keeps on hand.",
  },
  growth: {
    Icon: Sprout,
    question: "Is it getting bigger?",
    body: "Sales, profit per share and free cash flow over several years.",
  },
  valuation: {
    Icon: Scale,
    question: "Is the price fair?",
    body: "What you pay for each dollar of profit, against similar companies.",
  },
  sentiment: {
    Icon: MessageCircle,
    question: "What is the news saying?",
    body: "The tone of recent filings and news coverage about the company.",
  },
};

const TONE: Record<Rating, string> = {
  BUY: "var(--buy-fill)",
  HOLD: "var(--hold-fill)",
  SELL: "var(--sell-fill)",
};

/** What the grade is made of, said the way a non-specialist would ask it. Beside the
 *  five questions, one real company's report shape: pointing at a question lights its
 *  spoke and shows that company's score for it. The verdict scale underneath is read
 *  from the same thresholds a report uses, so this page cannot disagree with one. */
export function Grading({ example }: { example: ShowcaseCard | null }) {
  const [active, setActive] = React.useState(0);

  return (
    <section aria-labelledby="grading-heading" className="border-t border-rule bg-surface py-24 sm:py-32">
      <div className={CONTAINER}>
        <div className="max-w-[44rem]">
          <h2
            id="grading-heading"
            className="text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[52px]"
          >
            <RiseText inView text="Five questions, one clear answer." />
          </h2>
          <Appear delay={0.15}>
            <p className="mt-5 text-[17px] leading-relaxed text-ink-muted sm:text-[18px]">
              Each area is scored out of 10 from the company&rsquo;s own numbers, then the
              five are weighted into one overall score. Same rules for every company.
            </p>
          </Appear>
        </div>

        <div className="mt-14 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)] lg:gap-16">
          <ul className="flex flex-col gap-2">
            {DIMENSIONS.map((d, i) => {
              const { Icon, question, body } = AREAS[d];
              const on = i === active;
              return (
                <li key={d}>
                  <button
                    type="button"
                    onPointerEnter={() => setActive(i)}
                    onFocus={() => setActive(i)}
                    onClick={() => setActive(i)}
                    aria-pressed={on}
                    className={cn(
                      "relative flex w-full items-start gap-4 rounded-[14px] border p-5 text-left transition-colors",
                      on ? "border-rule bg-paper shadow-float" : "border-transparent hover:bg-paper/60",
                    )}
                  >
                    <span
                      className={cn(
                        "grid size-11 shrink-0 place-items-center rounded-xl transition-colors",
                        on ? "bg-ink text-paper" : "bg-surface-sunk text-ink",
                      )}
                    >
                      <Icon className="size-5" strokeWidth={2} aria-hidden />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[13px] font-semibold text-ink-muted">
                        {DIMENSION_LABELS[d]}
                      </span>
                      <span className="mt-0.5 block text-[19px] font-semibold tracking-[-0.02em] text-ink">
                        {question}
                      </span>
                      <motion.span
                        initial={false}
                        animate={{ height: on ? "auto" : 0, opacity: on ? 1 : 0 }}
                        transition={{ duration: 0.35, ease: EASE }}
                        className="block overflow-hidden"
                      >
                        <span className="block pt-1.5 text-[15px] leading-relaxed text-ink-muted">
                          {body}
                        </span>
                      </motion.span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          {example && <ShapePanel card={example} active={active} />}
        </div>

        <Appear className="mt-16">
          <VerdictScale card={example} />
        </Appear>
      </div>
    </section>
  );
}

function ShapePanel({ card, active }: { card: ShowcaseCard; active: number }) {
  const reduced = useReducedMotion();
  const ref = React.useRef<SVGSVGElement>(null);
  const seen = useInView(ref, { once: true, margin: "-15% 0px" });
  const size = 360;
  const c = size / 2;
  const r = size / 2 - 64;
  const angle = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / DIMENSIONS.length;
  const at = (i: number, k: number) => [c + Math.cos(angle(i)) * r * k, c + Math.sin(angle(i)) * r * k] as const;
  const ring = (k: number) => DIMENSIONS.map((_, i) => at(i, k).join(",")).join(" ");
  const k = (d: string) => {
    const v = card.dimension_scores[d];
    return typeof v === "number" ? Math.max(0.06, Math.min(1, v / 10)) : 0.04;
  };
  const shape = DIMENSIONS.map((d, i) => at(i, k(d)).join(",")).join(" ");
  const flat = DIMENSIONS.map((_, i) => at(i, 0.02).join(",")).join(" ");
  const rating = card.rating ?? "HOLD";
  const d = DIMENSIONS[active];
  const v = card.dimension_scores[d];
  const g = typeof v === "number" ? grade(v, THRESHOLDS) : null;
  const drawn = reduced || seen;

  return (
    <div className="lg:sticky lg:top-24 lg:self-start">
      <div className="card-soft p-6">
        <div className="flex items-center justify-between text-[13px]">
          <span className="font-semibold text-ink">{card.name ?? card.ticker}</span>
          <span className={cn("font-semibold", VERDICT_TEXT[rating])}>
            {verdictWord(rating)} {formatScore(card.total_score)}
          </span>
        </div>

        <svg ref={ref} viewBox={`0 0 ${size} ${size}`} className="mx-auto mt-2 w-full max-w-[22rem] overflow-visible" role="img" aria-label={`${card.ticker} scores by area`}>
          <g fill="none" stroke="var(--rule)" strokeWidth={1}>
            {[1, 0.75, 0.5, 0.25].map((s) => (
              <polygon key={s} points={ring(s)} />
            ))}
          </g>
          {DIMENSIONS.map((_, i) => {
            const [x, y] = at(i, 1);
            return (
              <line
                key={i}
                x1={c}
                y1={c}
                x2={x}
                y2={y}
                stroke={i === active ? "var(--ink)" : "var(--rule)"}
                strokeWidth={i === active ? 1.5 : 1}
                style={{ transition: "stroke .3s" }}
              />
            );
          })}
          <motion.polygon
            initial={false}
            animate={{ points: drawn ? shape : flat }}
            transition={{ duration: 1.2, ease: EASE, delay: 0.2 }}
            fill={TONE[rating]}
            fillOpacity={0.22}
            stroke={TONE[rating]}
            strokeWidth={2}
            strokeLinejoin="round"
          />
          {DIMENSIONS.map((dim, i) => {
            const [x, y] = at(i, drawn ? k(dim) : 0.02);
            const on = i === active;
            return (
              <motion.circle
                key={dim}
                initial={false}
                animate={{ cx: x, cy: y, r: on ? 6 : 3.5 }}
                transition={{ duration: on ? 0.3 : 1.2, ease: EASE, delay: drawn && !on ? 0.2 : 0 }}
                fill={on ? "var(--ink)" : TONE[rating]}
                stroke="var(--surface)"
                strokeWidth={2}
              />
            );
          })}
          {DIMENSIONS.map((dim, i) => {
            const [x, y] = at(i, 1.22);
            const on = i === active;
            return (
              <text
                key={dim}
                x={x}
                y={y}
                textAnchor={Math.abs(x - c) < 4 ? "middle" : x > c ? "start" : "end"}
                dominantBaseline="middle"
                fontSize={13}
                fontWeight={on ? 700 : 500}
                fill={on ? "var(--ink)" : "var(--ink-muted)"}
                style={{ fontFamily: "var(--font-sans)", transition: "fill .3s" }}
              >
                {DIMENSION_LABELS[dim]}
              </text>
            );
          })}
        </svg>

        <div className="mt-2 flex items-end justify-between border-t border-rule pt-5">
          <div className="min-w-0">
            <p className="text-[13px] text-ink-muted">{DIMENSION_LABELS[d]}</p>
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={d}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
                className={cn("text-[15px] font-semibold", g?.text ?? "text-ink-muted")}
              >
                {g?.word ?? "Not scored"}
              </motion.p>
            </AnimatePresence>
          </div>
          <AnimatePresence mode="wait" initial={false}>
            <motion.p
              key={d}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25, ease: EASE }}
              className="nums text-[44px] font-semibold leading-none tracking-[-0.04em] text-ink"
            >
              {typeof v === "number" ? formatScore(v) : "—"}
              <span className="text-[16px] font-medium tracking-normal text-ink-muted"> / 10</span>
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

/** The one rule that turns a score into a verdict, with the example company's score
 *  sweeping in to where it landed. */
function VerdictScale({ card }: { card: ShowcaseCard | null }) {
  const reduced = useReducedMotion();
  const ref = React.useRef<HTMLDivElement>(null);
  const seen = useInView(ref, { once: true, margin: "-10% 0px" });
  const total = card?.total_score ?? null;

  return (
    <div ref={ref} className="card-soft p-6 sm:p-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[17px] font-semibold text-ink">The overall score decides the verdict</p>
        {card && total !== null && (
          <p className="text-[14px] text-ink-muted">
            {card.ticker} landed at <span className="nums font-semibold text-ink">{formatScore(total)}</span>
          </p>
        )}
      </div>
      <div className="relative mt-8">
        <div className="grid grid-cols-[50fr_25fr_25fr] gap-1 text-[14px] font-semibold">
          <span className="rounded-l-full bg-sell-wash px-4 py-3 text-sell">Sell</span>
          <span className="bg-hold-wash px-4 py-3 text-hold">Hold</span>
          <span className="rounded-r-full bg-buy-wash px-4 py-3 text-right text-buy">Buy</span>
        </div>
        {total !== null && (
          <motion.span
            aria-hidden
            initial={false}
            animate={{ left: `${(reduced || seen ? total : 0) * 10}%` }}
            transition={{ duration: 1.6, ease: EASE, delay: 0.2 }}
            className="absolute -top-3 bottom-[-0.75rem] w-0.5 -translate-x-1/2 rounded-full bg-ink"
          >
            <span className="absolute -top-1 left-1/2 size-2.5 -translate-x-1/2 rounded-full bg-ink" />
          </motion.span>
        )}
      </div>
      <div className="nums mt-4 grid grid-cols-[50fr_25fr_25fr] text-[13px] font-semibold text-ink-muted">
        <span>0</span>
        <span>{THRESHOLDS.hold}</span>
        <span className="flex justify-between">
          <span>{THRESHOLDS.buy}</span>
          <span>10</span>
        </span>
      </div>
    </div>
  );
}
