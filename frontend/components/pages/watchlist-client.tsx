"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import * as React from "react";

import { STAGGER_ITEM, verdictWord } from "@/components/app/kit";
import { WatchCard } from "@/components/app/watchlist-card";
import { EmptyState } from "@/components/empty-state";
import { AnonymousNotice, PageShell } from "@/components/page-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Rating, WatchlistEntry } from "@/lib/types";

/** How the list splits: one count per verdict, plus the companies not analyzed yet. */
function WatchSummary({ rows }: { rows: WatchlistEntry[] }) {
  const order: Rating[] = ["BUY", "HOLD", "SELL"];
  const dot: Record<Rating, string> = { BUY: "bg-buy", HOLD: "bg-hold", SELL: "bg-sell" };
  const count = (r: Rating) => rows.filter((w) => w.rating === r).length;
  const unrated = rows.filter((w) => !w.rating).length;
  return (
    <div className="mb-6 grid grid-cols-2 overflow-hidden rounded-[14px] border border-rule bg-surface sm:grid-cols-4">
      {order.map((r) => (
        <div key={r} className="border-b border-r border-rule px-5 py-4 sm:border-b-0 [&:nth-child(2)]:border-r-0 [&:nth-child(3)]:border-b-0 sm:[&:nth-child(2)]:border-r">
          <p className="flex items-center gap-2 text-[13px] text-ink-muted">
            <span aria-hidden className={cn("size-2 rounded-full", dot[r])} />
            {verdictWord(r)}
          </p>
          <p className="nums mt-1 text-[28px] font-semibold leading-none tracking-[-0.04em] text-ink">{count(r)}</p>
        </div>
      ))}
      <div className="px-5 py-4">
        <p className="text-[13px] text-ink-muted">Not analyzed yet</p>
        <p className="nums mt-1 text-[28px] font-semibold leading-none tracking-[-0.04em] text-ink">{unrated}</p>
      </div>
    </div>
  );
}

export function WatchlistClient() {
  const queryClient = useQueryClient();
  const reduced = useReducedMotion();
  const [ticker, setTicker] = React.useState("");
  const [running, setRunning] = React.useState<string[]>([]);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [addError, setAddError] = React.useState<string | null>(null);

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  // No `enabled` guard: the watchlist is scoped to whoever is asking, and for a visitor
  // without an account that is their cookie. Waiting for a user here was what made the
  // page look like it required one.
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: api.watchlist,
  });

  const query = ticker.trim();
  const { data: suggestions = [] } = useQuery({
    queryKey: ["tickers", query],
    queryFn: () => api.searchTickers(query),
    enabled: query.length > 0,
    staleTime: 5 * 60_000,
  });

  const add = useMutation({
    /* Only real tickers are watched. Anything else would sit on the list forever as
       "not analyzed yet", because there is nothing to analyze. */
    mutationFn: async (t: string) => {
      const matches = await queryClient.fetchQuery({
        queryKey: ["tickers", t],
        queryFn: () => api.searchTickers(t),
        staleTime: 5 * 60_000,
      });
      if (!matches.some((m) => m.ticker === t)) {
        throw new Error(
          matches.length
            ? `${t} is not a ticker. Pick one of the suggestions below.`
            : `No company found for ${t}. Try its ticker symbol, like AAPL for Apple.`,
        );
      }
      return api.addWatch(t);
    },
    onSuccess: () => {
      setTicker("");
      setAddError(null);
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (e) =>
      setAddError(
        e instanceof ApiError || e instanceof Error
          ? e.message
          : "That ticker could not be added. Try again in a moment.",
      ),
  });

  const remove = useMutation({
    mutationFn: (t: string) => api.removeWatch(t),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  /** Bulk re-run. Sequential on purpose: the worker takes one job at a time, so firing
   *  eight at once would only queue them behind each other while looking chaotic. */
  const rerunAll = async () => {
    setNotice(null);
    const queued: string[] = [];
    for (const row of rows) {
      setRunning((r) => [...r, row.ticker]);
      try {
        await api.runAnalysis({ ticker: row.ticker });
        queued.push(row.ticker);
      } catch (e) {
        setNotice(
          e instanceof Error
            ? `Stopped after ${queued.length} of ${rows.length}: ${e.message}`
            : "Some tickers could not be queued.",
        );
        break;
      } finally {
        setRunning((r) => r.filter((t) => t !== row.ticker));
      }
    }
    if (queued.length && !notice) {
      setNotice(
        `Started ${queued.length} analys${queued.length === 1 ? "is" : "es"}. They appear in your history as they finish.`,
      );
    }
    queryClient.invalidateQueries({ queryKey: ["usage"] });
  };

  return (
    <PageShell
      title="Watchlist"
      lede="Companies you are following, with the rating and score from their most recent completed analysis."
      action={
        <div className="w-full max-w-[22rem] sm:w-auto">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (ticker.trim()) add.mutate(ticker.trim().toUpperCase());
            }}
          >
            <Input
              value={ticker}
              onChange={(e) => {
                setTicker(e.target.value.toUpperCase());
                setAddError(null);
              }}
              placeholder="Add a company"
              className="nums w-40 uppercase"
              aria-label="Ticker to add"
              autoComplete="off"
            />
            <Button type="submit" variant="outline" disabled={add.isPending}>
              Add
            </Button>
          </form>
          {addError && (
            <p role="alert" className="mt-2 text-small text-sell">
              {addError}
            </p>
          )}
          {query.length > 0 && suggestions.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {suggestions
                .filter((sug) => !rows.some((r) => r.ticker === sug.ticker))
                .slice(0, 5)
                .map((sug) => (
                  <li key={sug.ticker}>
                    <button
                      type="button"
                      onClick={() => add.mutate(sug.ticker)}
                      className="rounded-full border border-rule bg-surface px-3 py-1 text-small text-muted-foreground transition-colors hover:border-brand hover:text-ink"
                    >
                      <span className="nums">{sug.ticker}</span>
                      <span className="ml-1.5 text-micro">{sug.name}</span>
                    </button>
                  </li>
                ))}
            </ul>
          )}
        </div>
      }
    >
      {!user && <AnonymousNotice what="Your watchlist" />}

      {notice && (
        <p className="mb-4 rounded-md border border-rule bg-surface px-3 py-2 text-small text-ink-soft">
          {notice}
        </p>
      )}

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[13.5rem] rounded-[14px]" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing watched yet"
          body="Add a company above, or use \u201cAdd to watchlist\u201d on any analysis, to keep its latest rating in one place and refresh them all at once."
        />
      ) : (
        <>
          <WatchSummary rows={rows} />

          <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button
              variant="default"
              onClick={rerunAll}
              disabled={running.length > 0}
            >
              <RefreshCw className={running.length > 0 ? "animate-spin" : undefined} aria-hidden />
              {running.length > 0
                ? `Starting ${running[0]}`
                : rows.length === 1
                  ? `Refresh ${rows[0].ticker}`
                  : `Refresh all ${rows.length}`}
            </Button>
            <span className="text-small text-muted-foreground">
              Each company uses 1 credit, unless it was analyzed recently &mdash;
              then it&rsquo;s free.
            </span>
          </div>

          <motion.ul
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            initial={reduced ? false : "hidden"}
            animate="shown"
            transition={{ staggerChildren: 0.05 }}
          >
            <AnimatePresence initial={false}>
              {rows.map((w, i) => (
                <motion.li
                  key={w.ticker}
                  layout={!reduced}
                  variants={STAGGER_ITEM}
                  exit={{ opacity: 0, scale: 0.94, transition: { duration: 0.2 } }}
                >
                  <WatchCard
                    entry={w}
                    delay={i * 0.05}
                    onRemove={() => remove.mutate(w.ticker)}
                    className={running.includes(w.ticker) ? "border-ink" : undefined}
                  />
                </motion.li>
              ))}
            </AnimatePresence>
          </motion.ul>
        </>
      )}
    </PageShell>
  );
}
