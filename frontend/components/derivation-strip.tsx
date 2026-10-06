import { formatExact, formatMetric } from "@/lib/format";
import type { MetricValue } from "@/lib/types";

/** The working behind a number.
 *
 *  Every figure in this product is computed in Python from filing lines, and this is
 *  where a reader can check that. The formula is set in mono between two rules because
 *  it is code and should look like code; the inputs are a ledger, right-aligned on the
 *  decimal, in full precision rather than abbreviated — the point is to show the exact
 *  value that went in.
 *
 *  Two columns at width: the arithmetic on the left, and whatever has to be *said*
 *  about it on the right. A note about averaged balances is prose, not a footnote to a
 *  table, and stacking it underneath made the strip read as one long column of small
 *  grey text.
 */
export function DerivationStrip({ metric }: { metric: MetricValue }) {
  const inputs = Object.entries(metric.inputs ?? {});

  return (
    <div className="strip-open border-l-2 border-brand bg-secondary/50 py-5 pl-6 pr-4">
      <div className="grid gap-x-12 gap-y-4 lg:grid-cols-[minmax(0,32rem)_minmax(0,1fr)]">
        <div className="min-w-0">
          <code className="formula block">{metric.formula}</code>

          {inputs.length > 0 ? (
            <dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-8">
              {inputs.map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="truncate border-b border-rule-soft py-1.5 font-mono text-small text-muted-foreground">
                    {key}
                  </dt>
                  <dd className="nums border-b border-rule-soft py-1.5 text-right font-mono text-small text-ink">
                    {formatExact(value)}
                  </dd>
                </div>
              ))}
              <dt className="pt-2.5 text-base font-medium text-ink">
                {metric.label ?? metric.name}
                <span className="ml-2 font-normal text-muted-foreground">
                  {metric.period}
                </span>
              </dt>
              <dd className="nums pt-2.5 text-right text-base font-semibold text-ink">
                {formatMetric(metric)}
              </dd>
            </dl>
          ) : (
            <p className="mt-4 text-base text-muted-foreground">
              No statement inputs were recorded for this metric.
            </p>
          )}
        </div>

        {metric.note && (
          <p className="max-w-[38ch] text-base leading-relaxed text-muted-foreground">
            {metric.note}.
          </p>
        )}
      </div>
    </div>
  );
}
