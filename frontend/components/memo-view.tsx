"use client";

import Link from "next/link";
import * as React from "react";

import { inShort } from "@/components/in-short";
import { RatingBlock } from "@/components/rating-block";
import { ScorecardRail } from "@/components/scorecard-rail";
import { ClaimList, CitedText, MemoProse } from "@/components/memo-body";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AnalysisDetail } from "@/lib/types";

/** The memo tab, and the landing page's sample.
 *
 *  Two columns: the argument on the left in serif at a 66-character measure, the numbers
 *  behind it on the right in sans. The split is the product's epistemology made visible —
 *  read the left, check the right.
 */
export function MemoView({
  analysis,
  onCite,
  compact = false,
}: {
  analysis: AnalysisDetail;
  onCite?: (label: string) => void;
  compact?: boolean;
}) {
  const memo = analysis.memo;
  const card = analysis.scorecard;

  if (!memo || !card) {
    return (
      <div className="panel p-8">
        <p className="text-lead">This analysis has no memo.</p>
        <p className="mt-2 max-w-[52ch] text-base text-muted-foreground">
          {analysis.error ??
            "This analysis stopped before the written summary was finished. Try running it again."}
        </p>
      </div>
    );
  }

  // Analyses saved before the fallback note was rewritten still carry the provider's
  // raw error. Readers get the plain version.
  const caveats = [
    ...(memo.data_caveats ?? []),
    ...(analysis.data_quality?.warnings ?? []),
  ]
    .filter(
      (c) =>
        !/^no (data[- ]quality )?(issues|problems|caveats)( were)? recorded\.?$/i.test(
          c.trim(),
        ),
    )
    .map((c) =>
      c.startsWith("Parts of this memo were not written by a model")
        ? "Some written explanations could not be generated for this analysis, so shorter automatic text was used in places. Every number is unaffected."
        : c,
    );

  return (
    <div className="space-y-8">
      <RatingBlock
        scorecard={card}
        priceTarget={card.price_target}
        price={analysis.blocks?.market?.price ?? null}
        summary={inShort(analysis)}
        asOf={formatDate(memo.as_of)}
      />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-10">
        {/* On a phone the report card comes straight after the verdict, before the long
            read; on a wide screen it sits beside it. */}
        <div className="order-2 min-w-0 lg:order-1">
          <section>
            <h2 className="mb-3 text-section">The full picture</h2>
            <MemoProse>
              <p>
                <CitedText
                  text={memo.thesis}
                  evidence={analysis.evidence}
                  onCite={onCite}
                />
              </p>
            </MemoProse>
          </section>

          <ClaimList
            title="What is going well"
            items={memo.key_drivers}
            evidence={analysis.evidence}
            onCite={onCite}
            tone="buy"
          />
          <ClaimList
            title="What could go wrong"
            items={memo.key_risks}
            evidence={analysis.evidence}
            onCite={onCite}
            tone="sell"
          />
          <ClaimList
            title="What would change the rating"
            items={memo.what_would_change_our_mind}
            evidence={analysis.evidence}
            onCite={onCite}
          />

          {caveats.length > 0 && (
            <section className="mt-8">
              <h3 className="mb-3 text-section">Things to keep in mind</h3>
              <ul className="space-y-2">
                {caveats.map((c, i) => (
                  <li
                    key={i}
                    className="max-w-[62ch] text-base leading-relaxed text-muted-foreground"
                  >
                    {c}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* On a phone the column dissolves into the page (display: contents) so its
            parts can be ordered separately: the report card straight after the verdict,
            saving and sources after the reasoning. On a wide screen it is one sticky
            column beside the text. */}
        <aside className="contents lg:sticky lg:top-24 lg:order-2 lg:block lg:space-y-5 lg:self-start">
          <div className="order-1 lg:order-none">
            <ScorecardRail scorecard={card} />
          </div>

          {!compact && (analysis.owned || analysis.public_slug) && (
            <div className="panel order-3 p-4 lg:order-none">
              <h3 className="mb-2 text-base font-medium">Save or share</h3>
              <div className="flex flex-col gap-2">
                {(analysis.owned || analysis.public_slug) && (
                  <Button asChild variant="outline" size="sm">
                    <a href={api.pdfUrl(analysis.id)} download>
                      Download as PDF
                    </a>
                  </Button>
                )}
                {analysis.owned && (
                  <ShareButton
                    analysisId={analysis.id}
                    slug={analysis.public_slug}
                  />
                )}
              </div>
              <p className="mt-2.5 text-micro leading-relaxed text-muted-foreground">
                The PDF includes every source, so anyone you send it to can
                check the claims.
              </p>
            </div>
          )}

          {memo.cited_sources?.length > 0 && (
            <div className="panel order-3 p-4 lg:order-none">
              <h3 className="mb-2 text-base font-medium">Sources</h3>
              <p className="text-small leading-relaxed text-muted-foreground">
                This summary draws on{" "}
                <span className="nums text-ink">
                  {memo.cited_sources.length}
                </span>{" "}
                of the {analysis.evidence.length} passages we read. Any claim we
                could not back up with a source was removed.
              </p>
              {!compact && (
                <Link
                  href="#evidence"
                  className="mt-2 inline-block text-small text-primary hover:underline"
                  onClick={(e) => {
                    e.preventDefault();
                    onCite?.(memo.cited_sources[0]);
                  }}
                >
                  Read the sources
                </Link>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function ShareButton({
  analysisId,
  slug,
}: {
  analysisId: string;
  slug?: string | null;
}) {
  const [url, setUrl] = React.useState<string | null>(
    slug
      ? `${typeof window !== "undefined" ? window.location.origin : ""}/m/${slug}`
      : null,
  );
  const [busy, setBusy] = React.useState(false);

  /** One click makes the link and copies it. Copying can be refused (no HTTPS, browser
   *  permissions), so the link is always shown as well, selectable, and the message
   *  says which of the two happened. */
  const share = async () => {
    setBusy(true);
    let target = url;
    try {
      if (!target) {
        const res = await api.shareAnalysis(analysisId);
        target = `${window.location.origin}/m/${res.slug}`;
        setUrl(target);
      }
    } catch {
      toast.error(
        "The share link could not be created. Try again in a moment.",
      );
      setBusy(false);
      return;
    }
    try {
      await navigator.clipboard.writeText(target);
      toast.success("Link copied", {
        description:
          "Anyone with the link can read this analysis, without signing in.",
      });
    } catch {
      toast.success("Share link ready", {
        description: "Copy it from the box below.",
      });
    }
    setBusy(false);
  };

  return (
    <div className="flex flex-col gap-2">
      <Button variant="outline" size="sm" onClick={share} disabled={busy}>
        {url ? "Copy the share link" : "Create a share link"}
      </Button>
      {url && (
        <input
          readOnly
          value={url}
          aria-label="Share link"
          onFocus={(e) => e.currentTarget.select()}
          className="w-full rounded-md border border-rule bg-surface-sunk px-2 py-1.5 text-small text-ink-soft"
        />
      )}
    </div>
  );
}
