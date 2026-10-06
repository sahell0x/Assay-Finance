"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import * as React from "react";

import { EASE } from "@/components/landing/motion";
import { cn } from "@/lib/cn";

/** The fill of one report-card bar. It grows from nothing the first time it is seen, a
 *  beat after the one above it, so the card reads top to bottom like it was marked. */
export function ReportBarFill({ pct, className, index = 0 }: { pct: number; className: string; index?: number }) {
  const reduced = useReducedMotion();
  const ref = React.useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true });
  return (
    <motion.span
      ref={ref}
      className={cn("block h-full rounded-full", className)}
      initial={false}
      animate={{ width: reduced || seen ? `${pct}%` : "0%" }}
      transition={{ duration: 0.9, ease: EASE, delay: reduced ? 0 : 0.3 + index * 0.1 }}
    />
  );
}
