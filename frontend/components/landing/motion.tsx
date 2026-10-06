"use client";

import Lenis from "lenis";
import { motion, useReducedMotion } from "motion/react";
import * as React from "react";

import { cn } from "@/lib/cn";

/** The house curve: quick out of the blocks, long settle. Every landing animation uses
 *  it, so the page moves with one hand. */
export const EASE = [0.22, 1, 0.36, 1] as const;

/** Inertial scrolling for the landing page only. Product pages keep native scrolling,
 *  where a table or a long memo has to stop exactly where the reader stops. Skipped
 *  entirely for anyone who asks for reduced motion. */
export function SmoothScroll() {
  React.useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ duration: 1.1, smoothWheel: true, autoRaf: true });
    return () => lenis.destroy();
  }, []);
  return null;
}

/** A headline that rises into place a word at a time from behind a mask, so it reads
 *  as being set rather than faded in. Screen readers get the sentence in one piece. */
export function RiseText({
  text,
  className,
  delay = 0,
  stagger = 0.06,
  inView = false,
}: {
  text: string;
  className?: string;
  delay?: number;
  stagger?: number;
  /** Wait until scrolled into view, instead of playing on load. */
  inView?: boolean;
}) {
  const reduced = useReducedMotion();
  const words = text.split(" ");
  const play = inView
    ? { whileInView: "shown", viewport: { once: true, margin: "-10% 0px" } }
    : { animate: "shown" };

  return (
    <motion.span
      className={cn("block", className)}
      initial={reduced ? false : "hidden"}
      {...play}
      transition={{ staggerChildren: stagger, delayChildren: delay }}
      aria-label={text}
    >
      {words.map((w, i) => (
        <span key={i} aria-hidden className="inline-block overflow-hidden pb-[0.12em] -mb-[0.12em] align-bottom">
          <motion.span
            className="inline-block"
            variants={{
              hidden: { y: "105%" },
              shown: { y: "0%", transition: { duration: 0.9, ease: EASE } },
            }}
          >
            {w}
            {i < words.length - 1 ? " " : ""}
          </motion.span>
        </span>
      ))}
    </motion.span>
  );
}

/** A block that settles into place once, the first time it is scrolled to. */
export function Appear({
  children,
  className,
  delay = 0,
  y = 24,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  y?: number;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-8% 0px" }}
      transition={{ duration: 0.8, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}
