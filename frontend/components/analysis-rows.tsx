"use client";

import { ArrowUpRight, Trash2 } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";

import { ScoreBar, STAGGER_ITEM, VerdictChip } from "@/components/app/kit";
import { cn } from "@/lib/cn";
import { DASH, formatScore, relativeTime } from "@/lib/format";
import type { AnalysisSummary } from "@/lib/types";

/** What a run that has no verdict yet is doing, in words a reader understands. */
export function RunStatus({ status }: { status: string }) {
  if (status === "failed") return <span className="text-[13px] font-medium text-sell">Did not finish</span>;
  const live = status === "queued" || status === "running";
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-muted">
      {live && (
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-ink/40 motion-reduce:animate-none" />
          <span className="relative inline-flex size-2 rounded-full bg-ink" />
        </span>
      )}
      {status === "queued" ? "Waiting to start" : status === "running" ? "Running now" : status}
    </span>
  );
}

/** A list of runs. Shared by the dashboard and the history page.
 *
 *  Rows rather than cards: someone scanning thirty analyses wants to compare ratings down
 *  a column. Each row carries the verdict, the score drawn as a bar, the confidence and
 *  when it ran; rows settle in one after another and leave with a short collapse when
 *  deleted.
 */
export function AnalysisRows({
  rows,
  onDelete,
}: {
  rows: AnalysisSummary[];
  onDelete?: (id: string) => void;
}) {
  const reduced = useReducedMotion();
  if (rows.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-[14px] border border-rule bg-surface">
      <div
        aria-hidden
        className="hidden grid-cols-[minmax(0,1.2fr)_7rem_minmax(0,1.4fr)_6.5rem_7rem_2.5rem] gap-4 border-b border-rule px-5 py-2.5 text-[12px] font-medium text-ink-muted md:grid"
      >
        <span>Company</span>
        <span>Verdict</span>
        <span>Score</span>
        <span>Confidence</span>
        <span>When</span>
        <span />
      </div>
      <motion.ul initial={reduced ? false : "hidden"} animate="shown" transition={{ staggerChildren: 0.04 }}>
        <AnimatePresence initial={false}>
          {rows.map((r) => (
            <motion.li
              key={r.id}
              layout={!reduced}
              variants={STAGGER_ITEM}
              exit={{ opacity: 0, height: 0, transition: { duration: 0.25 } }}
              className="group relative border-b border-rule last:border-0"
            >
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-5 py-3.5 transition-colors group-hover:bg-paper md:grid-cols-[minmax(0,1.2fr)_7rem_minmax(0,1.4fr)_6.5rem_7rem_2.5rem]">
                <div className="flex min-w-0 items-center gap-2.5">
                  <Link
                    href={`/analysis/${r.id}`}
                    className="nums text-[16px] font-semibold tracking-[-0.01em] text-ink after:absolute after:inset-0 after:content-['']"
                  >
                    {r.ticker}
                  </Link>
                  {r.cached && <span className="truncate text-[12px] text-ink-muted">Saved result</span>}
                  <ArrowUpRight
                    aria-hidden
                    className="size-3.5 text-ink-muted opacity-0 transition-opacity group-hover:opacity-100"
                  />
                </div>

                <div className="justify-self-end md:justify-self-start">
                  {r.rating ? <VerdictChip rating={r.rating} /> : <RunStatus status={r.status} />}
                </div>

                <div className="col-span-2 flex items-center gap-3 md:col-span-1">
                  <ScoreBar score={r.total_score} rating={r.rating} className="flex-1" />
                  <span className="nums w-8 text-right text-[15px] font-semibold text-ink">
                    {typeof r.total_score === "number" ? formatScore(r.total_score) : DASH}
                  </span>
                </div>

                <span className="hidden text-[14px] capitalize text-ink-muted md:block">{r.conviction ?? DASH}</span>
                <span className="hidden text-[14px] text-ink-muted md:block">
                  {relativeTime(r.completed_at ?? r.created_at)}
                </span>

                <div className="hidden md:block">
                  {onDelete && (
                    <button
                      type="button"
                      onClick={() => onDelete(r.id)}
                      className={cn(
                        "relative z-10 grid size-8 place-items-center rounded-md text-ink-muted opacity-0 transition-[opacity,color,background-color]",
                        "hover:bg-sell-wash hover:text-sell focus-visible:opacity-100 group-hover:opacity-100",
                      )}
                      aria-label={`Delete the ${r.ticker} analysis`}
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </button>
                  )}
                </div>

                {/* Phones: the when and the delete action share a line under the bar. */}
                <div className="col-span-2 flex items-center justify-between text-[13px] text-ink-muted md:hidden">
                  <span>
                    {relativeTime(r.completed_at ?? r.created_at)}
                    {r.conviction ? `, ${r.conviction} confidence` : ""}
                  </span>
                  {onDelete && (
                    <button
                      type="button"
                      onClick={() => onDelete(r.id)}
                      className="relative z-10 font-medium hover:text-sell"
                      aria-label={`Delete the ${r.ticker} analysis`}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </motion.ul>
    </div>
  );
}
