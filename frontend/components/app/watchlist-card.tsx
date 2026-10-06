"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import Link from "next/link";

import { LiveShape, ScoreBar, VerdictChip } from "@/components/app/kit";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatScore, relativeTime } from "@/lib/format";
import type { WatchlistEntry } from "@/lib/types";

/** The five area scores behind a watched company's latest run. The watchlist row only
 *  carries the overall score; the shape needs the breakdown, which is one free read of a
 *  stored analysis, shared with every other view of it through the query cache. */
export function useAreaScores(analysisId?: string | null) {
  const { data } = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api.getAnalysis(analysisId as string),
    enabled: Boolean(analysisId),
    staleTime: 5 * 60_000,
  });
  return {
    scores: data?.scorecard?.dimension_scores ?? null,
    name: data?.blocks?.market?.name ?? null,
  };
}

/** One watched company as a card: its report shape, verdict, score and when it last ran.
 *  The whole card opens the latest analysis; the remove button sits above that link. */
export function WatchCard({
  entry,
  onRemove,
  delay = 0,
  className,
}: {
  entry: WatchlistEntry;
  onRemove?: () => void;
  delay?: number;
  className?: string;
}) {
  const { scores, name } = useAreaScores(entry.analysis_id);
  const analyzed = Boolean(entry.rating);
  // Some stored runs carry the ticker as the name; saying it twice adds nothing.
  const company = [entry.name, name].find((n) => n && n !== entry.ticker) ?? null;

  return (
    <div
      className={cn(
        "group relative flex h-full flex-col rounded-[14px] border border-rule bg-surface p-5 transition-[border-color,box-shadow,transform] duration-300",
        entry.analysis_id && "hover:-translate-y-0.5 hover:border-brand-edge hover:shadow-float",
        className,
      )}
    >
      <div className="flex items-start gap-3.5">
        <LiveShape scores={scores} rating={entry.rating} size={52} delay={delay} />
        <div className="min-w-0 flex-1">
          {entry.analysis_id ? (
            <Link
              href={`/analysis/${entry.analysis_id}`}
              className="nums text-[17px] font-semibold tracking-[-0.01em] text-ink after:absolute after:inset-0 after:rounded-[14px] after:content-['']"
            >
              {entry.ticker}
            </Link>
          ) : (
            <span className="nums text-[17px] font-semibold tracking-[-0.01em] text-ink">{entry.ticker}</span>
          )}
          {company && <p className="truncate text-[13px] text-ink-muted">{company}</p>}
        </div>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="relative z-10 -mr-1.5 -mt-1.5 grid size-8 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface-sunk hover:text-ink"
            aria-label={`Stop watching ${entry.ticker}`}
          >
            <X className="size-4" aria-hidden />
          </button>
        )}
      </div>

      {analyzed ? (
        <>
          <div className="mt-5 flex items-end justify-between gap-3">
            <VerdictChip rating={entry.rating!} />
            <span className="nums text-[28px] font-semibold leading-none tracking-[-0.04em] text-ink">
              {formatScore(entry.total_score)}
              <span className="text-[13px] font-medium tracking-normal text-ink-muted"> / 10</span>
            </span>
          </div>
          <ScoreBar score={entry.total_score} rating={entry.rating} className="mt-3" delay={delay} />
          <p className="mt-3 text-[12px] text-ink-muted">
            {entry.last_run ? `Last analyzed ${relativeTime(entry.last_run)}` : "Analyzed"}
          </p>
        </>
      ) : (
        <div className="mt-auto pt-5">
          <p className="text-[14px] font-medium text-ink">No verdict yet</p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">
            Its verdict and score appear here after its first analysis.
          </p>
        </div>
      )}
    </div>
  );
}
