"use client";

import { PeerScatter } from "@/components/charts/peer-scatter";
import { MetricTab } from "@/components/tabs/metric-tab";
import { Badge } from "@/components/ui/badge";
import { DASH, formatCurrency, formatPercent, formatValue } from "@/lib/format";
import type { MetricBlock } from "@/lib/types";

interface PeerRow {
  ticker: string;
  name?: string | null;
  market_cap: number | null;
  pe: number | null;
  ev_ebitda: number | null;
  ev_sales: number | null;
  price_to_book: number | null;
  fcf_yield: number | null;
  operating_margin: number | null;
  roic: number | null;
  rev_yoy: number | null;
  is_target: boolean;
}

const COLUMNS: { key: keyof PeerRow; label: string; kind: "x" | "percent" | "currency" }[] = [
  { key: "market_cap", label: "Market cap", kind: "currency" },
  { key: "pe", label: "P/E", kind: "x" },
  { key: "ev_ebitda", label: "EV/EBITDA", kind: "x" },
  { key: "ev_sales", label: "EV/sales", kind: "x" },
  { key: "price_to_book", label: "P/B", kind: "x" },
  { key: "fcf_yield", label: "FCF yield", kind: "percent" },
  { key: "operating_margin", label: "Op. margin", kind: "percent" },
  { key: "roic", label: "ROIC", kind: "percent" },
  { key: "rev_yoy", label: "Growth", kind: "percent" },
];

export function PeersTab({ block }: { block?: MetricBlock | null }) {
  const extras = (block?.extras ?? {}) as {
    peer_rows?: PeerRow[];
    scatter?: {
      points: { ticker: string; x: number; y: number; size?: number; is_target?: boolean }[];
      excluded: string[];
      cap: number;
    };
    source?: string;
    excluded_multiples?: number[];
    peer_median_ev_ebitda?: number | null;
    peer_median_ev_ebitda_untrimmed?: number | null;
  };

  const rows = extras.peer_rows ?? [];

  return (
    <MetricTab
      block={block}
      emptyReason="We could not find similar companies to compare this one with, so its valuation is shown on its own."
      charts={
        <div className="space-y-7">
          {rows.length > 1 && (
            <section>
              <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h3 className="text-section">Similar companies</h3>
                <Badge>
                  {extras.source === "user"
                    ? "you chose these"
                    : extras.source === "fallback"
                      ? "general large companies"
                      : "matched by industry"}
                </Badge>
              </header>

              <div className="panel overflow-hidden">
                <div className="thin-scroll overflow-x-auto">
                  <table className="data-table min-w-[52rem]">
                    <thead>
                      <tr>
                        <th scope="col">Company</th>
                        {COLUMNS.map((c) => (
                          <th key={String(c.key)} scope="col" className="text-right">
                            {c.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr
                          key={r.ticker}
                          className={r.is_target ? "bg-brand-wash" : undefined}
                        >
                          <td>
                            <span
                              className={
                                r.is_target
                                  ? "nums font-medium text-primary"
                                  : "nums text-ink"
                              }
                            >
                              {r.ticker}
                            </span>
                            {r.is_target && (
                              <span className="ml-2 text-micro text-muted-foreground">
                                this company
                              </span>
                            )}
                          </td>
                          {COLUMNS.map((c) => {
                            const v = r[c.key] as number | null;
                            return (
                              <td key={String(c.key)} className="num-cell">
                                {v === null || v === undefined
                                  ? DASH
                                  : c.kind === "currency"
                                    ? formatCurrency(v)
                                    : c.kind === "percent"
                                      ? formatPercent(v)
                                      : formatValue(v, "x")}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {extras.excluded_multiples && extras.excluded_multiples.length > 0 && (
                  <p className="border-t border-rule px-3 py-2 text-micro leading-relaxed text-muted-foreground">
                    The median EV/EBITDA behind the price target is{" "}
                    <span className="nums">
                      {extras.peer_median_ev_ebitda?.toFixed(1)}x
                    </span>
                    , taken after excluding {extras.excluded_multiples.length} reading
                    {extras.excluded_multiples.length === 1 ? "" : "s"} as not meaningful
                    (
                    {extras.excluded_multiples
                      .slice()
                      .sort((a, b) => a - b)
                      .map((v) => `${v.toFixed(0)}x`)
                      .join(", ")}
                    ). Including them would put the median at{" "}
                    <span className="nums">
                      {extras.peer_median_ev_ebitda_untrimmed?.toFixed(0)}x
                    </span>
                    , which describes those companies&rsquo; thin EBITDA rather than how
                    the market prices them.
                  </p>
                )}
              </div>
            </section>
          )}

          <PeerScatter
            points={extras.scatter?.points ?? []}
            excluded={extras.scatter?.excluded ?? []}
            cap={extras.scatter?.cap}
          />
        </div>
      }
    />
  );
}
