"use client";

import { grade, THRESHOLDS } from "@/components/scorecard-rail";
import { MetricTable } from "@/components/metric-table";
import { formatScore } from "@/lib/format";
import type { MetricBlock } from "@/lib/types";

/** One analysis dimension: the reading, the table, and the charts.
 *
 *  The narrative comes first because it says what the numbers mean; the table second
 *  because it is what a reader will check; the charts last because they are the slowest
 *  of the three to read.
 */
export function MetricTab({
  block,
  charts,
  emptyReason,
}: {
  block?: MetricBlock | null;
  charts?: React.ReactNode;
  emptyReason: string;
}) {
  if (!block) {
    return (
      <div className="panel p-8">
        <p className="text-lead text-ink">Not available</p>
        <p className="mt-2 max-w-[52ch] text-base text-muted-foreground">
          {emptyReason}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-7">
      <div className="grid gap-7 lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-10">
        <div className="min-w-0">
          {block.narrative && (
            <p
              className="memo-prose"
              style={{ fontSize: "var(--text-lead)", lineHeight: 1.65 }}
            >
              {block.narrative}
            </p>
          )}
        </div>
        <div className="panel self-start p-4">
          <div className="text-small text-muted-foreground">Score for this area</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="nums text-[2rem] font-semibold leading-none text-ink">
              {formatScore(block.score)}
            </span>
            <span className="text-base text-muted-foreground">out of 10</span>
          </div>
          <p className={`mt-1 text-base font-semibold ${grade(block.score, THRESHOLDS).text}`}>
            {grade(block.score, THRESHOLDS).word}
          </p>
          <p className="mt-2 text-micro leading-relaxed text-muted-foreground">
            Based on the measures below. Any measure without enough data is left out
            rather than counted as zero.
          </p>
        </div>
      </div>

      {block.warnings.length > 0 && (
        <ul className="space-y-2">
          {block.warnings.map((w, i) => (
            <li
              key={i}
              className="max-w-[70ch] border-l-2 border-hold py-0.5 pl-3 text-base leading-relaxed text-muted-foreground"
            >
              {w}
            </li>
          ))}
        </ul>
      )}

      <MetricTable
        metrics={block.metrics}
        order={block.order}
        caption={`${block.dimension} metrics`}
      />

      {charts}
    </div>
  );
}
