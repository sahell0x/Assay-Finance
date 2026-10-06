"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { Stagger, StaggerItem } from "@/components/app/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SkeletonTable } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRupees } from "@/lib/format";
import type { ActivityFilter, CreditActivity } from "@/lib/types";

const FILTERS: { id: ActivityFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "usage", label: "Analyses" },
  { id: "purchases", label: "Purchases" },
];

function describe(t: CreditActivity): React.ReactNode {
  switch (t.kind) {
    case "purchase":
      return t.pack_name ? `Bought the ${t.pack_name} pack` : "Bought credits";
    case "spend":
    case "free_spend":
      return t.ticker ? `Analysis of ${t.ticker}` : "Analysis";
    case "refund":
    case "free_refund":
      return t.ticker
        ? `Given back: the ${t.ticker} analysis did not finish`
        : "Given back: an analysis did not finish";
  }
}

/** Every credit in and out, like a bank statement: newest first, one row per movement,
 *  with the money shown next to anything that cost money. */
export function ActivityLog() {
  const [filter, setFilter] = React.useState<ActivityFilter>("all");

  const query = useInfiniteQuery({
    queryKey: ["credit-activity", filter],
    queryFn: ({ pageParam }) => api.creditActivity(filter, pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next,
  });
  const rows = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section aria-labelledby="activity-heading">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 id="activity-heading" className="text-[22px] font-semibold tracking-[-0.03em] text-ink">
          Activity
        </h2>
        <div className="flex rounded-lg border border-rule bg-surface p-0.5" role="group" aria-label="Show">
          {FILTERS.map((f) => {
            const on = filter === f.id;
            return (
              <button
                key={f.id}
                type="button"
                aria-pressed={on}
                onClick={() => setFilter(f.id)}
                className={cn(
                  "relative rounded-md px-3 py-1 text-[13px] font-medium transition-colors",
                  on ? "text-paper" : "text-ink-muted hover:text-ink",
                )}
              >
                {on && (
                  <motion.span
                    layoutId="activity-filter"
                    aria-hidden
                    className="absolute inset-0 rounded-md bg-ink"
                    transition={{ type: "spring", stiffness: 450, damping: 36 }}
                  />
                )}
                <span className="relative">{f.label}</span>
              </button>
            );
          })}
        </div>
        <Button asChild variant="ghost" size="sm" className="ml-auto">
          <a href={api.creditActivityCsvUrl()} download>
            <Download className="size-3.5" aria-hidden />
            Download CSV
          </a>
        </Button>
      </div>

      {query.isLoading ? (
        <SkeletonTable rows={5} />
      ) : rows.length === 0 ? (
        <p className="border-t border-rule py-6 text-base text-muted-foreground">
          {filter === "purchases"
            ? "No purchases yet."
            : "Nothing yet. Every analysis you run, and every credit you buy, will be listed here."}
        </p>
      ) : (
        <>
          <div className="panel overflow-x-auto">
            <table className="w-full min-w-[36rem] text-base">
              <thead>
                <tr className="border-b border-rule text-left text-small text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Date</th>
                  <th className="px-4 py-2.5 font-medium">What</th>
                  <th className="px-4 py-2.5 font-medium">Credit</th>
                  <th className="px-4 py-2.5 text-right font-medium">Amount</th>
                  <th className="px-4 py-2.5 text-right font-medium">Change</th>
                </tr>
              </thead>
              <Stagger as="tbody" key={filter} gap={0.035}>
                {rows.map((t) => (
                  <StaggerItem as="tr" key={t.id} className="border-b border-rule-soft transition-colors last:border-0 hover:bg-surface-sunk/50">
                    <td className="whitespace-nowrap px-4 py-2.5 text-small text-muted-foreground">
                      {formatDateTime(t.created_at)}
                    </td>
                    <td className="px-4 py-2.5 text-ink">
                      {t.analysis_id && (t.kind === "spend" || t.kind === "free_spend") ? (
                        <Link href={`/analysis/${t.analysis_id}`} className="hover:underline">
                          {describe(t)}
                        </Link>
                      ) : (
                        describe(t)
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={t.source === "free" ? "neutral" : "brand"}>
                        {t.source === "free" ? "Free" : "Bought"}
                      </Badge>
                    </td>
                    <td className="nums whitespace-nowrap px-4 py-2.5 text-right text-ink-soft">
                      {t.amount_paise !== null ? formatRupees(t.amount_paise) : ""}
                    </td>
                    <td
                      className={cn(
                        "nums whitespace-nowrap px-4 py-2.5 text-right font-medium",
                        t.delta > 0 ? "text-buy" : "text-ink-soft",
                      )}
                    >
                      {t.delta > 0 ? `+${t.delta}` : `−${Math.abs(t.delta)}`}
                    </td>
                  </StaggerItem>
                ))}
              </Stagger>
            </table>
          </div>
          {query.hasNextPage && (
            <Button
              variant="outline"
              className="mt-3"
              disabled={query.isFetchingNextPage}
              onClick={() => query.fetchNextPage()}
            >
              {query.isFetchingNextPage ? "Loading…" : "Show older activity"}
            </Button>
          )}
        </>
      )}
    </section>
  );
}
