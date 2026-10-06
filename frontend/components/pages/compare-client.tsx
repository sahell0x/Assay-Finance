"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { CompareBoard, CompareTheses } from "@/components/app/compare-board";
import { EmptyPanel, LiveShape, VerdictChip } from "@/components/app/kit";
import { AnonymousNotice, PageShell } from "@/components/page-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";

/** Side-by-side scorecards.
 *
 *  A matrix rather than a row of cards: the whole point is to read across a dimension,
 *  and cards force the eye to jump between boxes to do that.
 */
export function CompareClient() {
  const [input, setInput] = React.useState("");
  const [tickers, setTickers] = React.useState<string[]>([]);

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: api.watchlist,
  });

  // Everything this person has finished analyzing is comparable, so offer it rather
  // than asking them to remember and type the symbols.
  const { data: past = [] } = useQuery({
    queryKey: ["analyses", { limit: 200 }],
    queryFn: () => api.listAnalyses({ limit: 200 }),
  });
  const analyzed = React.useMemo(
    () => [...new Set(past.filter((a) => a.status === "complete").map((a) => a.ticker))],
    [past],
  );

  const toggle = (t: string) => {
    const next = tickers.includes(t)
      ? tickers.filter((x) => x !== t)
      : [...tickers, t].slice(0, 6);
    setTickers(next);
    setInput(next.join(" "));
  };

  // Both queries are owner-scoped server-side, and an anonymous visitor is an owner.
  const { data, isLoading } = useQuery({
    queryKey: ["compare", tickers],
    queryFn: () => api.compare(tickers),
    enabled: tickers.length > 0,
  });

  const columns = data?.columns ?? [];
  const present = columns.filter((c) => c.available);

  return (
    <PageShell
      title="Compare"
      lede="See up to six companies you have analyzed side by side: their scores, ratings and fair value ranges."
    >
      {!user && <AnonymousNotice what="What you have analyzed" />}

      {analyzed.length > 0 && (
        <section className="mb-6">
          <p className="text-[14px] text-ink-muted">
            Pick from companies you have analyzed, up to six
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {analyzed.map((t) => {
              const on = tickers.includes(t);
              return (
                <li key={t}>
                  <motion.button
                    type="button"
                    layout
                    whileTap={{ scale: 0.96 }}
                    aria-pressed={on}
                    onClick={() => toggle(t)}
                    className={cn(
                      "nums inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-[14px] font-semibold transition-colors",
                      on
                        ? "border-ink bg-ink text-paper"
                        : "border-rule bg-paper text-ink hover:border-brand-edge",
                    )}
                  >
                    <AnimatePresence initial={false}>
                      {on && (
                        <motion.span
                          initial={{ width: 0, opacity: 0 }}
                          animate={{ width: "auto", opacity: 1 }}
                          exit={{ width: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <Check className="size-3.5" strokeWidth={3} aria-hidden />
                        </motion.span>
                      )}
                    </AnimatePresence>
                    {t}
                  </motion.button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <form
        className="mb-8 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const parsed = input
            .split(/[,\s]+/)
            .map((t) => t.trim().toUpperCase())
            .filter(Boolean)
            .slice(0, 6);
          setTickers(parsed);
        }}
      >
        <div>
          <label htmlFor="compare-input" className="block text-[14px] text-ink-muted">
            {analyzed.length > 0 ? "Or type tickers, separated by spaces" : "Tickers, separated by spaces"}
          </label>
          <Input
            id="compare-input"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="e.g. AAPL MSFT NVDA"
            className="nums mt-1.5 h-10 w-72 max-w-full uppercase placeholder:normal-case"
            autoComplete="off"
          />
        </div>
        <Button type="submit" variant="default" size="lg">
          Compare
        </Button>
        {watchlist.length > 1 && (
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={() => {
              const fromWatchlist = watchlist.slice(0, 6).map((w) => w.ticker);
              setInput(fromWatchlist.join(" "));
              setTickers(fromWatchlist);
            }}
          >
            Use my watchlist
          </Button>
        )}
      </form>

      {tickers.length === 0 ? (
        <EmptyPanel
          title="Nothing to compare yet"
          body={
            analyzed.length > 0
              ? "Pick two or more companies above to see them side by side."
              : "Compare lines up companies you have already analyzed. Run an analysis on two or more companies and they will appear here."
          }
          action={
            analyzed.length > 0 ? undefined : (
              <Button asChild size="lg">
                <Link href="/analyze">Run an analysis</Link>
              </Button>
            )
          }
        />
      ) : isLoading ? (
        <div className="skeleton h-96 w-full rounded-[20px]" />
      ) : present.length === 0 ? (
        <EmptyPanel
          title="None of those have been analyzed"
          body={`Run ${(data?.missing ?? tickers).join(", ")} first and they will be ready to compare.`}
          action={
            <Button asChild size="lg">
              <Link href="/analyze">Run an analysis</Link>
            </Button>
          }
        />
      ) : (
        <>
          {data?.missing?.length ? (
            <p className="mb-4 text-[14px] text-ink-muted">
              Left out because you have not analyzed {data.missing.length === 1 ? "it" : "them"} yet:{" "}
              {data.missing.join(", ")}.
            </p>
          ) : null}
          <CompareBoard columns={present} />
          <CompareTheses columns={present} />
        </>
      )}

      {analyzed.length === 0 && <GradedExamples />}
    </PageShell>
  );
}

/** For someone with nothing to compare yet: finished reports they can open for free, so
 *  the page still shows what a graded company looks like. */
function GradedExamples() {
  const { data: cards = [] } = useQuery({
    queryKey: ["showcase", 6],
    queryFn: () => api.showcase(6),
    staleTime: 5 * 60_000,
  });
  const graded = cards.filter((c) => c.rating);
  if (graded.length === 0) return null;
  return (
    <section className="mt-12">
      <h2 className="text-[19px] font-semibold tracking-[-0.02em] text-ink">See a finished report</h2>
      <p className="mt-1 text-[14px] text-ink-muted">Opening one of these is free.</p>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {graded.map((c, i) => (
          <motion.li
            key={c.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.06 }}
          >
            <Link
              href={`/analysis/${c.id}`}
              className="group flex items-center gap-3 rounded-[14px] border border-rule bg-paper p-4 transition-[border-color,transform] hover:-translate-y-0.5 hover:border-brand-edge"
            >
              <LiveShape scores={c.dimension_scores} rating={c.rating} size={40} />
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold text-ink">{c.ticker}</span>
                <span className="block truncate text-[12px] text-ink-muted">{c.name}</span>
              </span>
              <span className="flex flex-col items-end gap-1">
                <VerdictChip rating={c.rating!} size="sm" />
                <span className="nums text-[13px] font-semibold text-ink">{formatScore(c.total_score)}</span>
              </span>
              <ArrowRight className="size-3.5 text-ink-muted transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          </motion.li>
        ))}
      </ul>
    </section>
  );
}
