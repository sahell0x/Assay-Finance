"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";

import { Hint } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

/** How many analyses are left, and whether the day's compute budget is spent.
 *
 *  Small and permanent rather than a banner that appears at the worst moment: someone
 *  about to start a run should be able to see the cost of it beforehand. It reads as an
 *  allowance rather than as a countdown — "2 free left" invites a run, "1 used" does not.
 */
export function UsageMeter() {
  const { data } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    retry: false,
    staleTime: 20_000,
  });

  const reduced = useReducedMotion();
  if (!data) return null;

  const budgetSpent = data.budget?.exhausted;
  const exhausted = data.exhausted || budgetSpent;

  return (
    <Hint
      label={
        budgetSpent
          ? "New analyses are paused until midnight UTC because today's limit has been reached. Anything already analyzed still opens normally."
          : data.authenticated
            ? data.paid_credits > 0
              ? `Each new analysis uses 1 credit. You have ${data.free_remaining} of ${data.limit} free credits left, plus ${data.paid_credits} you bought. Click to see your usage.`
              : `Each new analysis uses 1 credit. You have ${data.remaining} of ${data.limit} free credits left. Click to see your usage or buy more.`
            : `Each new analysis uses 1 credit. You have ${data.remaining} of ${data.limit} free credits. Create a free account to get ${data.account_free_credits} more and keep your history on any device.`
      }
    >
      <Link
        href={data.authenticated ? "/credits" : "/signup"}
        className="hidden items-center gap-2 text-[13px] text-ink-muted transition-colors hover:text-ink sm:inline-flex"
      >
        <span
          aria-hidden
          className={cn("size-1.5 rounded-full", exhausted ? "bg-sell-fill" : "bg-buy-fill")}
        />
        {/* The count rolls when it changes, so spending a credit is visible. */}
        <span className="relative inline-flex h-[1.2em] overflow-hidden">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={data.remaining}
              className="nums font-medium text-ink"
              initial={reduced ? false : { y: "-100%", opacity: 0 }}
              animate={{ y: "0%", opacity: 1 }}
              exit={reduced ? undefined : { y: "100%", opacity: 0 }}
              transition={{ duration: 0.35 }}
            >
              {data.remaining}
            </motion.span>
          </AnimatePresence>
        </span>
        <span className="-ml-1 hidden xl:inline">
          {data.remaining === 1 ? "credit left" : "credits left"}
        </span>
      </Link>
    </Hint>
  );
}
