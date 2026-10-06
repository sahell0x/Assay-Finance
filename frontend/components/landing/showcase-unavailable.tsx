"use client";

import { ArrowRight } from "lucide-react";

import { useTickerCommand } from "@/components/ticker-command";
import { Button } from "@/components/ui/button";

/** What the landing page says before anything has ever been analyzed.
 *
 *  An empty screen is an invitation to act, so this says what is missing and offers the
 *  one action that fixes it. It is honest about why: the page shows real runs, and on a
 *  fresh database there are none — inventing a company to display here would contradict
 *  the only thing the page is trying to establish.
 */
export function ShowcaseUnavailable() {
  const command = useTickerCommand();

  return (
    <section className="mt-14 border-y border-rule bg-surface-sunk/40">
      <div className="mx-auto max-w-[1440px] px-4 py-14 sm:px-6 sm:py-20 xl:px-12 min-[1440px]:px-[88px]">
        <div className="max-w-[54ch] rounded-[10px] border border-dashed border-rule bg-surface p-8">
          <h2 className="text-section text-ink">
            Nothing has been analyzed here yet
          </h2>
          <p className="mt-2.5 text-base leading-relaxed text-muted-foreground">
            This is where a finished analysis sits, ready to look through. The page only
            ever shows runs that really happened, so it stays empty until the first one
            does. Run a company and it appears here.
          </p>
          <Button className="mt-5" onClick={command.open}>
            Analyze a company
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </div>
    </section>
  );
}
