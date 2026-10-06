import { ReportBarFill } from "@/components/app/report-bar";
import { Hint } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { DASH, formatScore } from "@/lib/format";
import { DIMENSION_LABELS, DIMENSIONS, type Scorecard } from "@/lib/types";

/** What each area measures, in a line. */
const AREA_HELP: Record<string, string> = {
  profitability: "How much profit it makes from its sales",
  financial_health: "Debt, cash and ability to pay its bills",
  growth: "How fast sales and profit are growing",
  valuation: "How cheap or expensive the shares are",
  sentiment: "The tone of recent news and filings",
};

/** The rating cut-offs (backend: analytics/scoring.py). Used to grade an area where
 *  no scorecard is to hand, such as a single metric tab. */
export const THRESHOLDS = { buy: 7.5, hold: 5 } as const;

/** Grade words use the same cut-offs and colours as the rating itself, so a reader
 *  learns one colour code and it means the same thing everywhere on the page. */
export function grade(score: number, t: { buy: number; hold: number }) {
  if (score >= t.buy) return { word: "Strong", text: "text-buy", bar: "bg-buy-fill" };
  if (score >= t.hold) return { word: "Average", text: "text-hold", bar: "bg-hold-fill" };
  return { word: "Weak", text: "text-sell", bar: "bg-sell-fill" };
}

/** The report card: one line per area, each with a plain grade. */
export function ScorecardRail({
  scorecard,
  title = "Report card",
}: {
  scorecard: Scorecard;
  title?: string;
}) {
  const weights = scorecard.weights_applied ?? {};

  return (
    <section aria-label={title} className="panel p-4">
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="sec-title">{title}</h2>
        <span className="text-small text-muted-foreground">out of 10</span>
      </header>

      <ul className="mt-2">
        {DIMENSIONS.map((dim, i) => {
          const score = scorecard.dimension_scores?.[dim] ?? null;
          const weight = weights[dim];
          const unavailable = score === null || score === undefined;
          const g = unavailable ? null : grade(score, scorecard.thresholds);

          return (
            <li key={dim} className="border-b border-rule-soft py-3 last:border-b-0">
              <div className="flex items-baseline justify-between gap-3">
                <Hint
                  label={`${AREA_HELP[dim] ?? ""}${weight ? `. Counts for ${Math.round(weight * 100)}% of the overall score.` : "."}`}
                >
                  <span tabIndex={0} className="cursor-help text-base font-medium text-ink">
                    {DIMENSION_LABELS[dim]}
                  </span>
                </Hint>
                <span className="flex shrink-0 items-baseline gap-2">
                  {g && <span className={cn("text-small font-semibold", g.text)}>{g.word}</span>}
                  <span className="nums w-8 text-right text-lead font-semibold text-ink">
                    {unavailable ? (
                      <Hint label="There was not enough data to score this area, so the overall score is based on the other areas.">
                        <span className="absent text-base" tabIndex={0}>
                          {DASH}
                        </span>
                      </Hint>
                    ) : (
                      formatScore(score)
                    )}
                  </span>
                </span>
              </div>
              <div
                className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-sunk"
                role="img"
                aria-label={`${DIMENSION_LABELS[dim]}: ${unavailable ? "not available" : `${formatScore(score)} out of 10, ${g!.word.toLowerCase()}`}`}
              >
                {!unavailable && (
                  <ReportBarFill pct={Math.max(3, (score / 10) * 100)} className={g!.bar} index={i} />
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-1 flex items-baseline justify-between border-t border-rule pt-3">
        <span className="text-base font-semibold text-ink">Overall</span>
        <span className="nums text-section font-bold tracking-tight text-ink">
          {formatScore(scorecard.total)}
        </span>
      </div>

      {scorecard.dimensions_unavailable?.length > 0 && (
        <p className="mt-3 text-small leading-relaxed text-muted-foreground">
          {scorecard.dimensions_unavailable
            .map((d) => DIMENSION_LABELS[d] ?? d)
            .join(" and ")}{" "}
          could not be scored because data was missing, so the overall score is based on
          the other areas.
        </p>
      )}
    </section>
  );
}
