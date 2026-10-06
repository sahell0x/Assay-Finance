"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { AssayMark } from "@/components/brand";
import { RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";

import { useTickerCommand } from "@/components/ticker-command";
import { Button } from "@/components/ui/button";

/** The close.
 *
 *  An account is offered on what it actually buys — more runs and history that follows
 *  you between devices — rather than as the price of seeing anything. Everything on the
 *  page above already worked without one.
 */
export function ClosingCta() {
  const command = useTickerCommand();

  return (
    <section className="pb-24 sm:pb-32">
      <div className={CONTAINER}>
        <div className="relative overflow-hidden rounded-[14px] bg-brand px-6 py-14 text-center text-brand-on sm:px-12 sm:py-20 dark:border dark:border-rule dark:bg-surface dark:text-ink">
          <AssayMark className="relative mx-auto size-10 [--mark-cut:#0a0a0a] [--mark-tile:#ffffff] dark:[--mark-tile:#ededed]" />
          <h2 className="relative mx-auto mt-6 max-w-[18ch] text-[34px] font-semibold leading-[1.08] tracking-[-0.035em] sm:text-[52px]">
            <RiseText inView text="Know what a stock is really worth." />
          </h2>
          <p className="relative mx-auto mt-4 max-w-[48ch] text-[17px] leading-relaxed opacity-80">
            Three reports are free and need no account. Make one, and everything you have
            already run comes with you.
          </p>
          <div className="relative mt-9 flex flex-col justify-center gap-3 sm:flex-row">
            <Button
              size="xl"
              onClick={command.open}
              className="bg-paper text-ink hover:bg-paper/90 dark:bg-ink dark:text-paper dark:hover:bg-ink/90"
            >
              Analyze a company <ArrowRight aria-hidden />
            </Button>
            <Button
              asChild
              size="xl"
              variant="outline"
              className="border-white/25 bg-transparent text-inherit hover:bg-white/10 hover:text-inherit dark:border-rule"
            >
              <Link href="/signup">Create a free account</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
