"use client";

import * as React from "react";

import { DerivationStrip } from "@/components/derivation-strip";
import { PeerRail } from "@/components/peer-rail";
import { Sparkline } from "@/components/charts/sparkline";
import { Hint } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { DASH, formatMetric } from "@/lib/format";
import { METRIC_HELP } from "@/lib/metric-help";
import type { Flag, MetricValue } from "@/lib/types";

/** Flags tint the value by one step. Not traffic lights: at twelve rows a column of
 *  red and green dots is louder than the numbers, which is backwards. `unreliable`
 *  drops colour entirely, because a number you should not rely on ought not to look
 *  like one. */
const FLAG_TEXT: Record<Flag, string> = {
  strong: "text-buy",
  neutral: "text-ink",
  weak: "text-sell",
  unreliable: "text-muted-foreground line-through decoration-rule",
};

const FLAG_TITLE: Record<Flag, string> = {
  strong: "A good reading for this measure",
  neutral: "An average reading for this measure",
  weak: "A poor reading for this measure",
  unreliable: "Computable but not meaningful for this company",
};

export function MetricTable({
  metrics,
  order,
  caption,
}: {
  metrics: Record<string, MetricValue>;
  order?: string[];
  caption?: string;
}) {
  const [open, setOpen] = React.useState<string | null>(null);

  // Postgres reorders JSONB keys, so `Object.entries` comes back shuffled. The block
  // carries its intended order; anything not listed is appended rather than dropped.
  const rows = React.useMemo(() => {
    if (!order?.length) return Object.entries(metrics);
    const listed = order.filter((k) => k in metrics).map((k) => [k, metrics[k]] as const);
    const rest = Object.entries(metrics).filter(([k]) => !order.includes(k));
    return [...listed, ...rest];
  }, [metrics, order]);

  return (
    <div>
      <div className="panel thin-scroll overflow-x-auto">
        <table className="data-table min-w-[42rem]">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr>
              <th scope="col" className="w-[55%] !pl-0">
                Measure
              </th>
              <th scope="col" className="text-right">
                Value
              </th>
              <th scope="col" className="w-[7.5rem] text-left">
                <Hint label="Where this company ranks among similar companies. Further right is better.">
                  <span tabIndex={0} className="cursor-help underline decoration-dotted underline-offset-4">
                    Versus peers
                  </span>
                </Hint>
              </th>
              <th scope="col" className="w-[6.5rem] !pr-0 text-left">
                Five years
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, m]) => {
              const isOpen = open === key;
              const flag = m.flag ?? "neutral";
              const available = m.value !== null && m.value !== undefined;
              const history = (m.history ?? [])
                .map((h) => h.value)
                .filter((v): v is number => v !== null && v !== undefined);

              return (
                <React.Fragment key={key}>
                  <tr
                    className={cn(
                      "cursor-pointer transition-colors hover:bg-secondary/60",
                      isOpen && "bg-secondary/60",
                    )}
                    onClick={() => setOpen(isOpen ? null : key)}
                  >
                    <td className="!pl-0">
                      <button
                        type="button"
                        className="group text-left text-lead font-medium tracking-tight text-ink focus-visible:outline-none"
                        aria-expanded={isOpen}
                        aria-controls={`derivation-${key}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpen(isOpen ? null : key);
                        }}
                      >
                        {m.label ?? m.name}
                        <span
                          className={cn(
                            "ml-2.5 text-micro font-normal text-brand opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100",
                            isOpen && "opacity-100",
                          )}
                        >
                          {isOpen ? "Hide working" : "How it's worked out"}
                        </span>
                      </button>
                      {METRIC_HELP[key] && (
                        <p className="mt-0.5 max-w-[52ch] text-small leading-snug text-muted-foreground">
                          {METRIC_HELP[key]}
                        </p>
                      )}
                      {m.flag && m.flag !== "neutral" && (
                        <span className="sr-only"> — {FLAG_TITLE[m.flag]}</span>
                      )}
                    </td>

                    {/* The value is the subject of the row, so it is set as one. */}
                    <td className="num-cell">
                      {available ? (
                        <span
                          className={cn(
                            "nums text-section font-semibold tracking-tight",
                            FLAG_TEXT[flag],
                          )}
                        >
                          {formatMetric(m)}
                        </span>
                      ) : (
                        <Hint
                          label={
                            m.note
                              ? `${m.note}.`
                              : "This metric could not be computed from the filings."
                          }
                        >
                          <span className="absent" tabIndex={0}>
                            {DASH}
                          </span>
                        </Hint>
                      )}
                    </td>

                    <td>
                      <PeerRail percentile={m.peer_percentile} label={m.label ?? m.name} />
                    </td>

                    <td className="!pr-0">
                      {history.length >= 2 ? (
                        <Sparkline values={[...history].reverse()} />
                      ) : (
                        <span className="text-muted-foreground">{DASH}</span>
                      )}
                    </td>
                  </tr>

                  {isOpen && (
                    <tr id={`derivation-${key}`}>
                      <td colSpan={4} className="!p-0">
                        <DerivationStrip metric={m} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mono-label pt-2.5">
        Click any row to see how the number was worked out and where it came from
      </p>
    </div>
  );
}
