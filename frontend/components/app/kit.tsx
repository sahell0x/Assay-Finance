"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import * as React from "react";

import { EASE } from "@/components/landing/motion";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import { DIMENSIONS, type Rating } from "@/lib/types";

/** The product's shared motion vocabulary, so every interior page moves the same way as
 *  the landing page. Everything here holds its finished frame under reduced motion. */

export const VERDICT_CHIP: Record<Rating, string> = {
  BUY: "bg-buy-wash text-buy",
  HOLD: "bg-hold-wash text-hold",
  SELL: "bg-sell-wash text-sell",
};

export const VERDICT_FILL: Record<Rating, string> = {
  BUY: "bg-buy-fill",
  HOLD: "bg-hold-fill",
  SELL: "bg-sell-fill",
};

const VERDICT_VAR: Record<Rating, string> = {
  BUY: "var(--buy-fill)",
  HOLD: "var(--hold-fill)",
  SELL: "var(--sell-fill)",
};

export function verdictWord(r: Rating) {
  return r.charAt(0) + r.slice(1).toLowerCase();
}

/** "Buy", "Hold" or "Sell" in its colour. The word is always there; colour never carries
 *  the verdict alone. */
export function VerdictChip({ rating, size = "md", className }: { rating: Rating; size?: "sm" | "md"; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md font-semibold",
        size === "sm" ? "px-1.5 py-0.5 text-[12px]" : "px-2 py-0.5 text-[13px]",
        VERDICT_CHIP[rating],
        className,
      )}
    >
      {verdictWord(rating)}
    </span>
  );
}

/** A score out of 10 as a short bar that grows when first seen. */
export function ScoreBar({
  score,
  rating,
  className,
  delay = 0,
}: {
  score: number | null | undefined;
  rating?: Rating | null;
  className?: string;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  const ref = React.useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true });
  const pct = typeof score === "number" ? Math.max(2, Math.min(100, score * 10)) : 0;
  return (
    <span ref={ref} className={cn("block h-1.5 overflow-hidden rounded-full bg-surface-sunk", className)}>
      <motion.span
        className={cn("block h-full rounded-full", rating ? VERDICT_FILL[rating] : "bg-faint")}
        initial={false}
        animate={{ width: reduced || seen ? `${pct}%` : "0%" }}
        transition={{ duration: 0.9, ease: EASE, delay }}
      />
    </span>
  );
}

/** A number that counts to its value the first time it is seen. */
export function CountUp({
  value,
  decimals = 0,
  format,
  className,
}: {
  value: number;
  decimals?: number;
  format?: (v: number) => string;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const ref = React.useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true });
  const fmt = React.useCallback(
    (v: number) => (format ? format(v) : v.toFixed(decimals)),
    [format, decimals],
  );

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced || !seen) {
      el.textContent = fmt(reduced ? value : 0);
      return;
    }
    const start = performance.now();
    const dur = 1100;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / dur);
      const e = 1 - Math.pow(1 - k, 4);
      el.textContent = fmt(value * e);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, seen, reduced, fmt]);

  return (
    <span ref={ref} className={cn("nums", className)}>
      {fmt(reduced ? value : 0)}
    </span>
  );
}

/** A figure with a label: the dashboard's headline numbers. */
export function StatTile({
  label,
  value,
  decimals,
  format,
  hint,
  children,
  className,
}: {
  label: string;
  value?: number | null;
  decimals?: number;
  format?: (v: number) => string;
  hint?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col rounded-[14px] border border-rule bg-surface p-5", className)}>
      <p className="text-[13px] font-medium text-ink-muted">{label}</p>
      <p className="mt-2 text-[34px] font-semibold leading-none tracking-[-0.04em] text-ink">
        {typeof value === "number" ? <CountUp value={value} decimals={decimals} format={format} /> : "—"}
      </p>
      {children && <div className="mt-4">{children}</div>}
      {hint && <p className="mt-auto pt-3 text-[13px] leading-relaxed text-ink-muted">{hint}</p>}
    </div>
  );
}

/** A list whose items settle in one after another the first time it appears. */
export function Stagger({
  as = "ul",
  className,
  children,
  gap = 0.05,
}: {
  as?: "ul" | "ol" | "div" | "tbody";
  className?: string;
  children: React.ReactNode;
  gap?: number;
}) {
  const reduced = useReducedMotion();
  const Comp = motion[as];
  return (
    <Comp
      className={className}
      initial={reduced ? false : "hidden"}
      animate="shown"
      transition={{ staggerChildren: gap }}
    >
      {children}
    </Comp>
  );
}

export const STAGGER_ITEM = {
  hidden: { opacity: 0, y: 10 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } },
} as const;

export function StaggerItem({
  as = "li",
  className,
  children,
}: {
  as?: "li" | "div" | "tr";
  className?: string;
  children: React.ReactNode;
}) {
  const Comp = motion[as];
  return (
    <Comp className={className} variants={STAGGER_ITEM}>
      {children}
    </Comp>
  );
}

/** The five-spoke report shape, drawn out from the centre when it first appears. */
export function LiveShape({
  scores,
  rating,
  size = 44,
  className,
  delay = 0,
}: {
  scores: Record<string, number | null | undefined> | null | undefined;
  rating?: Rating | null;
  size?: number;
  className?: string;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  const ref = React.useRef<SVGSVGElement>(null);
  const seen = useInView(ref, { once: true });
  const c = size / 2;
  const r = size / 2 - 2;
  const at = (i: number, k: number) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / DIMENSIONS.length;
    return `${(c + Math.cos(a) * r * k).toFixed(2)},${(c + Math.sin(a) * r * k).toFixed(2)}`;
  };
  const ring = DIMENSIONS.map((_, i) => at(i, 1)).join(" ");
  const shape = DIMENSIONS.map((d, i) => {
    const v = scores?.[d];
    return at(i, typeof v === "number" ? Math.max(0.08, Math.min(1, v / 10)) : 0.05);
  }).join(" ");
  const flat = DIMENSIONS.map((_, i) => at(i, 0.05)).join(" ");
  const tone = rating ? VERDICT_VAR[rating] : "var(--faint)";

  return (
    <svg ref={ref} viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden className={cn("shrink-0 overflow-visible", className)}>
      <polygon points={ring} fill="var(--surface-sunk)" stroke="var(--rule)" strokeWidth={1} />
      <motion.polygon
        initial={false}
        animate={{ points: reduced || seen ? shape : flat }}
        transition={{ duration: 0.9, ease: EASE, delay }}
        fill={tone}
        fillOpacity={0.3}
        stroke={tone}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Score as large text, rounded the way every report rounds it. */
export function ScoreText({ score, className }: { score: number | null | undefined; className?: string }) {
  return <span className={cn("nums font-semibold tracking-[-0.02em] text-ink", className)}>{formatScore(score)}</span>;
}

/** An empty screen that draws a blank report card and names the next step. */
export function EmptyPanel({
  title,
  body,
  action,
  className,
}: {
  title: string;
  body: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const size = 120;
  const c = size / 2;
  const at = (i: number, k: number) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
    return `${(c + Math.cos(a) * 54 * k).toFixed(1)},${(c + Math.sin(a) * 54 * k).toFixed(1)}`;
  };
  return (
    <div className={cn("flex flex-col items-center rounded-[20px] border border-dashed border-brand-edge bg-surface px-6 py-14 text-center", className)}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden>
        {[1, 0.66, 0.33].map((k, j) => (
          <motion.polygon
            key={k}
            points={[0, 1, 2, 3, 4].map((i) => at(i, k)).join(" ")}
            fill="none"
            stroke="var(--brand-edge)"
            strokeWidth={1}
            initial={reduced ? false : { pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 1.1, ease: EASE, delay: j * 0.15 }}
          />
        ))}
        <motion.circle
          cx={c}
          cy={c}
          r={4}
          fill="var(--ink)"
          animate={reduced ? undefined : { scale: [1, 1.6, 1], opacity: [1, 0.5, 1] }}
          transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
        />
      </svg>
      <h2 className="mt-5 text-[22px] font-semibold tracking-[-0.03em] text-ink">{title}</h2>
      <div className="mt-2 max-w-[48ch] text-[15px] leading-relaxed text-ink-muted">{body}</div>
      {action && <div className="mt-6 flex flex-wrap justify-center gap-2.5">{action}</div>}
    </div>
  );
}
