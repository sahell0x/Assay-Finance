"use client";

import { ExternalLink } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";
import { formatDate, sourceLabel } from "@/lib/format";
import type { Evidence } from "@/lib/types";

/** The sources behind every qualitative claim.
 *
 *  Kept in the product rather than hidden, because a citation you cannot inspect is a
 *  citation you cannot check. Filings sort above newswire items, which is also how they
 *  rank in the retrieval.
 */
export function EvidenceList({
  evidence,
  highlight,
}: {
  evidence: Evidence[];
  highlight?: string | null;
}) {
  if (!evidence.length) {
    return (
      <div className="panel p-8 text-center">
        <p className="text-lead text-ink">No sources were retrieved.</p>
        <p className="mx-auto mt-2 max-w-[46ch] text-base text-muted-foreground">
          The memo for this company was written from the computed figures alone, and every
          qualitative claim was removed because none could be cited. Filings may not be
          available for this issuer.
        </p>
      </div>
    );
  }

  const bySource = evidence.reduce<Record<string, number>>((acc, e) => {
    acc[e.source_type] = (acc[e.source_type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <p className="mb-5 max-w-[62ch] text-base text-muted-foreground">
        {evidence.length} passages we read from this company&rsquo;s official reports and
        recent news{" "}
        <span className="text-ink-soft">
          ({Object.entries(bySource)
            .map(([k, v]) => `${v} ${sourceLabel(k).toLowerCase()}`)
            .join(", ")})
        </span>
        . The numbers in brackets in the memo, like [1], point to these. Any claim we
        could not back up with one of them was removed.
      </p>

      <ol className="space-y-3">
        {evidence.map((e) => (
          <li
            key={e.label}
            id={`source-${e.label}`}
            className={cn(
              "panel scroll-mt-24 p-4 transition-colors",
              highlight === e.label && "border-primary bg-brand-wash",
            )}
          >
            <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="nums text-small font-medium text-primary">
                [{e.label.slice(1)}]
              </span>
              <span className="text-small text-ink">
                {sourceLabel(e.source_type)}
              </span>
              {e.published && (
                <span className="nums text-micro text-muted-foreground">
                  {formatDate(e.published)}
                </span>
              )}
            </div>

            {e.section && (
              <p className="mb-1.5 text-small text-muted-foreground">{e.section}</p>
            )}

            <p className="memo-prose max-w-none text-base" style={{ lineHeight: 1.65 }}>
              {e.text}
            </p>

            {e.url && (
              <a
                href={e.url}
                target="_blank"
                rel="noreferrer noopener"
                className="mt-2.5 inline-flex items-center gap-1 text-micro text-primary hover:underline"
              >
                <ExternalLink size={11} aria-hidden />
                {e.title ?? "Open the source document"}
              </a>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
