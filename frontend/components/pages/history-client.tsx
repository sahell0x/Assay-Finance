"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { motion } from "motion/react";
import * as React from "react";
import { toast } from "sonner";

import { AnalysisRows } from "@/components/analysis-rows";
import { verdictWord } from "@/components/app/kit";
import { ScoreHistory } from "@/components/charts/score-history";
import { EmptyState } from "@/components/empty-state";
import { AnonymousNotice, PageShell } from "@/components/page-shell";
import { Input } from "@/components/ui/input";
import { SkeletonTable } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import type { AnalysisSummary, Rating } from "@/lib/types";

const RATINGS: (Rating | "ALL")[] = ["ALL", "BUY", "HOLD", "SELL"];

/** Runs grouped under "Today", "Yesterday" or their date, newest group first. The list
 *  arrives newest first, so the groups do too. */
function groupByDay(rows: AnalysisSummary[]): [string, AnalysisSummary[]][] {
  const key = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86_400_000);
  const groups = new Map<string, AnalysisSummary[]>();
  for (const r of rows) {
    const iso = r.completed_at ?? r.created_at;
    const d = iso ? new Date(iso) : null;
    const label = !d
      ? "Undated"
      : key(d) === key(today)
        ? "Today"
        : key(d) === key(yesterday)
          ? "Yesterday"
          : formatDate(iso);
    groups.set(label, [...(groups.get(label) ?? []), r]);
  }
  return [...groups.entries()];
}

export function HistoryClient() {
  const queryClient = useQueryClient();
  const [ticker, setTicker] = React.useState("");
  const [rating, setRating] = React.useState<Rating | "ALL">("ALL");

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  // The backend has always scoped history to the anonymous cookie when there is no
  // account; only this component insisted on one.
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["analyses", { limit: 200 }],
    queryFn: () => api.listAnalyses({ limit: 200 }),
  });

  const { data: history = [] } = useQuery({
    queryKey: ["ticker-history", ticker],
    queryFn: () => api.tickerHistory(ticker),
    enabled: ticker.trim().length >= 1,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteAnalysis(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["analyses"] }),
    onError: () => toast.error("That analysis could not be deleted. Try again in a moment."),
  });

  const filtered = rows.filter((r: AnalysisSummary) => {
    if (ticker && !r.ticker.includes(ticker.toUpperCase())) return false;
    if (rating !== "ALL" && r.rating !== rating) return false;
    return true;
  });

  return (
    <PageShell
      title="History"
      lede="Every analysis you have run, newest first. Re-opening one costs nothing."
    >
      {!user && <AnonymousNotice what="Your history" />}

      <div className="mb-8 flex flex-wrap items-end gap-x-6 gap-y-4">
        <div>
          <label htmlFor="filter-ticker" className="block text-[13px] font-medium text-ink-muted">
            Company
          </label>
          <div className="relative mt-1.5">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
            <Input
              id="filter-ticker"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="Filter by ticker"
              className="nums w-48 pl-9 uppercase placeholder:normal-case"
              autoComplete="off"
            />
          </div>
        </div>

        <div>
          <span id="filter-rating" className="block text-[13px] font-medium text-ink-muted">
            Verdict
          </span>
          <div role="radiogroup" aria-labelledby="filter-rating" className="mt-1.5 flex rounded-lg border border-rule bg-surface p-1">
            {RATINGS.map((r) => {
              const on = rating === r;
              return (
                <button
                  key={r}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => setRating(r)}
                  className={cn(
                    "relative rounded-md px-3.5 py-1.5 text-[13px] font-medium transition-colors",
                    on ? "text-paper" : "text-ink-muted hover:text-ink",
                  )}
                >
                  {on && (
                    <motion.span
                      layoutId="history-rating-pill"
                      aria-hidden
                      className="absolute inset-0 rounded-md bg-ink"
                      transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    />
                  )}
                  <span className="relative">
                    {r === "ALL" ? "All" : verdictWord(r)}
                    <span className={cn("nums ml-1.5", on ? "text-paper/70" : "text-faint")}>
                      {r === "ALL" ? rows.length : rows.filter((x) => x.rating === r).length}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <span className="nums ml-auto text-[13px] text-ink-muted">
          Showing {filtered.length} of {rows.length}
        </span>
      </div>

      {ticker.trim().length >= 1 && history.length >= 2 && (
        <div className="mb-8">
          <ScoreHistory points={history} ticker={ticker.toUpperCase()} />
        </div>
      )}

      {isLoading ? (
        <SkeletonTable rows={8} />
      ) : filtered.length === 0 ? (
        <EmptyState
          title={rows.length === 0 ? "Nothing here yet" : "Nothing matches those filters"}
          body={
            rows.length === 0
              ? "Analyses you run will be listed here, with their rating and score."
              : "Clear the company or rating filter to see everything again."
          }
          actionLabel={rows.length === 0 ? "Run an analysis" : undefined}
          actionHref={rows.length === 0 ? "/analyze" : undefined}
        />
      ) : (
        <div className="flex flex-col gap-8">
          {groupByDay(filtered).map(([day, group]) => (
            <section key={day} aria-label={day}>
              <h2 className="mb-3 flex items-center gap-3 text-[14px] font-semibold text-ink">
                {day}
                <span className="nums text-[13px] font-normal text-ink-muted">
                  {group.length} {group.length === 1 ? "analysis" : "analyses"}
                </span>
              </h2>
              <AnalysisRows
                rows={group}
                // Deleting needs an account on the server; offering it to a visitor would
                // only produce an error.
                onDelete={
                  user
                    ? (id) => {
                        if (window.confirm("Delete this analysis? This cannot be undone.")) {
                          remove.mutate(id);
                        }
                      }
                    : undefined
                }
              />
            </section>
          ))}
        </div>
      )}
    </PageShell>
  );
}
