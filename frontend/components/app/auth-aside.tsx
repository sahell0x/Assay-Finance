"use client";

import { Check } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { LiveCard } from "@/components/landing/live-card";
import { EASE, RiseText } from "@/components/landing/motion";
import type { ShowcaseCard } from "@/lib/types";

const POINTS = [
  "Three free reports before you sign up, ten more after",
  "History and watchlists that follow you to any device",
  "Every number shows how it was worked out",
];

/** The right half of the sign-in pages: what an account is for, and beside it a real
 *  report being worked out, cycling through companies already graded. */
export function AuthAside({ cards }: { cards: ShowcaseCard[] }) {
  const reduced = useReducedMotion();
  return (
    <div className="relative mx-auto w-full max-w-[32rem]">
      <h2 className="text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink xl:text-[42px]">
        <RiseText text="A report card for every stock." delay={0.1} />
      </h2>
      <ul className="mt-7 flex flex-col gap-3.5">
        {POINTS.map((p, i) => (
          <motion.li
            key={p}
            initial={reduced ? false : { opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease: EASE, delay: 0.45 + i * 0.1 }}
            className="flex items-center gap-3 text-[15px] font-medium text-ink-soft"
          >
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-ink text-paper">
              <Check className="size-3.5" strokeWidth={3} aria-hidden />
            </span>
            {p}
          </motion.li>
        ))}
      </ul>
      {cards.length > 0 && (
        <div className="mt-10">
          <LiveCard cards={cards} />
        </div>
      )}
    </div>
  );
}
