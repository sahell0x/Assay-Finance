import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { BandRule } from "@/components/band-rule";
import { grade } from "@/components/scorecard-rail";
import { cn } from "@/lib/cn";
import { formatCurrency, formatScore } from "@/lib/format";
import { DIMENSIONS, DIMENSION_LABELS, type AnalysisDetail, type Rating } from "@/lib/types";

export const VERDICT_CHIP: Record<Rating, string> = {
  BUY: "bg-buy-wash text-buy",
  HOLD: "bg-hold-wash text-hold",
  SELL: "bg-sell-wash text-sell",
};

export const VERDICT_TEXT: Record<Rating, string> = {
  BUY: "text-buy",
  HOLD: "text-hold",
  SELL: "text-sell",
};

const BAR: Record<string, string> = {
  "text-buy": "bg-buy-fill",
  "text-hold": "bg-hold-fill",
  "text-sell": "bg-sell-fill",
};

export function verdictWord(r: Rating) {
  return r.charAt(0) + r.slice(1).toLowerCase();
}

/** A finished analysis, shrunk to what defines one: who, the verdict and the score, the
 *  scale that produced it, and one line per area. Every value is read from the stored
 *  run. The verdict is the only coloured thing on the card. */
export function ReportCard({ analysis }: { analysis: AnalysisDetail }) {
  const card = analysis.scorecard;
  if (!card) return null;
  const market = analysis.blocks?.market ?? {};

  return (
    <Link
      href={`/analysis/${analysis.id}`}
      className="card-soft group block overflow-hidden transition-colors hover:border-brand-edge"
    >
      <div className="flex items-center gap-3 border-b border-rule px-5 py-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-surface-sunk text-[12px] font-semibold text-ink">
          {analysis.ticker.slice(0, 4)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold text-ink">
            {market.name ?? analysis.ticker}
          </p>
          <p className="truncate text-[13px] text-ink-muted">
            <span className="nums">{formatCurrency(market.price)}</span>
            {market.sector ? ` · ${market.sector}` : ""}
          </p>
        </div>
        <span
          className={cn(
            "ml-auto shrink-0 rounded-md px-2.5 py-1 text-[13px] font-semibold",
            VERDICT_CHIP[card.rating],
          )}
        >
          {verdictWord(card.rating)}
        </span>
      </div>

      <div className="grid items-end gap-5 border-b border-rule px-5 py-5 sm:grid-cols-[auto_minmax(0,1fr)]">
        <div>
          <p
            className={cn(
              "text-[52px] font-semibold leading-[0.9] tracking-[-0.035em]",
              VERDICT_TEXT[card.rating],
            )}
          >
            {verdictWord(card.rating)}
          </p>
          <p className="nums mt-2 text-[13px] text-ink-muted">
            <span className="text-[20px] font-semibold text-ink">{formatScore(card.total)}</span>{" "}
            / 10
          </p>
        </div>
        <BandRule total={card.total} thresholds={card.thresholds} rating={card.rating} size="sm" />
      </div>

      <ul className="px-5 py-2">
        {DIMENSIONS.map((d) => {
          const v = card.dimension_scores?.[d];
          const g = typeof v === "number" ? grade(v, card.thresholds) : null;
          return (
            <li
              key={d}
              className="grid grid-cols-[8.5rem_minmax(0,1fr)_4rem_2rem] items-center gap-3 border-b border-rule py-2.5 text-[13px] text-ink last:border-0"
            >
              {DIMENSION_LABELS[d]}
              <span className="h-1 overflow-hidden rounded-full bg-surface-sunk">
                {g && (
                  <span
                    className={cn("block h-full rounded-full", BAR[g.text])}
                    style={{ width: `${(v as number) * 10}%` }}
                  />
                )}
              </span>
              <span className="text-[12px] text-ink-muted">{g?.word ?? "—"}</span>
              <span className="nums text-right font-semibold">
                {typeof v === "number" ? formatScore(v) : "—"}
              </span>
            </li>
          );
        })}
      </ul>

      <span className="flex items-center gap-1.5 border-t border-rule px-5 py-3 text-[13px] font-medium text-ink">
        Open the full report
        <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
      </span>
    </Link>
  );
}
