"use client";

import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import * as React from "react";

import { EASE } from "@/components/landing/motion";

import { api } from "@/lib/api";

/** The frame every interior page sits in.
 *
 *  One container width, one header shape, one place to change either. The pages used to
 *  each declare their own and had drifted apart by a few pixels and a font size.
 *
 *  The title, a one-line explanation of the page, and the page's main action. No label
 *  above the title: the navigation already says where you are.
 */
export function PageShell({
  title,
  eyebrow,
  lede,
  action,
  children,
}: {
  title?: string;
  /** Accepted for older call sites; no longer rendered. */
  eyebrow?: string;
  lede?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  const rise = (delay: number) => ({
    initial: reduced ? false : { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6, ease: EASE, delay },
  });

  return (
    <div className="mx-auto w-full max-w-[80rem] px-4 pb-20 pt-10 sm:px-6 lg:px-8">
      {title && (
        <header className="mb-10 flex flex-wrap items-end justify-between gap-x-10 gap-y-5">
          <div className="min-w-0">
            <motion.h1
              {...rise(0)}
              className="text-[34px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[42px]"
            >
              {title}
            </motion.h1>
            {lede && (
              <motion.p {...rise(0.08)} className="mt-3 max-w-[64ch] text-[16px] leading-relaxed text-ink-muted">
                {lede}
              </motion.p>
            )}
          </div>
          {action && (
            <motion.div {...rise(0.14)} className="shrink-0">
              {action}
            </motion.div>
          )}
        </header>
      )}
      <motion.div {...rise(0.18)}>{children}</motion.div>
    </div>
  );
}

/** Said once, wherever a page's contents are kept against a cookie rather than an
 *  account. It is an offer, not a wall — everything on the page already works.
 *
 *  A quiet grey bar, not a coloured one: colour on this site means a verdict. */
export function AnonymousNotice({ what }: { what: string }) {
  // Pages render this as `{!user && ...}`, which is also true while the sign-in check is
  // still loading. Deciding here means a signed-in person never sees the notice flash.
  const { data: user, isPending } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
    staleTime: 60_000,
  });
  if (isPending || user) return null;

  return (
    <p className="mb-7 rounded-2xl bg-brand-wash px-5 py-3.5 text-[15px] leading-relaxed text-ink-soft">
      {what} is saved in this browser. Create a free account to keep it on any device;
      nothing here will be lost.{" "}
      <a href="/signup" className="font-medium text-ink">
        Create an account
      </a>
    </p>
  );
}
