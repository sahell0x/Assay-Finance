import { Badge, ratingTone } from "@/components/ui/badge";
import { Hint } from "@/components/ui/tooltip";
import { DASH, formatCurrency, formatValue } from "@/lib/format";
import type { AnalysisDetail } from "@/lib/types";

/** The strip of figures an analyst checks first, the way a tear sheet opens.
 *
 *  The ticker is the page title and is set as one: large, tight and flush left, with
 *  the company name underneath at a fraction of the weight. Figures are separated by
 *  rules rather than by middle dots, and every one is tabular so the row stays aligned
 *  when the numbers change.
 *
 *  `actions` is a slot rather than a set of props because the landing page's copy of
 *  this header must not offer to follow a company or share a memo — those belong on
 *  the analysis's own page.
 */
export function TearSheet({
  analysis,
  actions,
  embedded = false,
}: {
  analysis: AnalysisDetail;
  actions?: React.ReactNode;
  /** Inside another page: the company name becomes a subheading, not the page title. */
  embedded?: boolean;
}) {
  const Title = embedded ? "h2" : "h1";
  const market = analysis.blocks?.market ?? {};
  const peers = analysis.blocks?.peers;
  const card = analysis.scorecard;

  const figures: { label: string; value: string; hint: string }[] = [
    { label: "Price", value: formatCurrency(market.price), hint: "The price of one share." },
    {
      label: "Market cap",
      value: formatCurrency(market.market_cap),
      hint: "What the whole company is worth on the stock market: share price times the number of shares.",
    },
    {
      label: "P/E",
      hint: "Price to earnings: how many dollars investors pay for each dollar of yearly profit. Higher means more expensive.",
      value: peers?.metrics?.pe ? formatValue(peers.metrics.pe.value, "x") : DASH,
    },
    {
      label: "EV/EBITDA",
      hint: "The company's total value (including debt) divided by its yearly operating profit. A common way to compare how expensive companies are. Higher means more expensive.",
      value: peers?.metrics?.ev_ebitda
        ? formatValue(peers.metrics.ev_ebitda.value, "x")
        : DASH,
    },
  ];

  const classification = [market.sector, market.industry].filter(Boolean).join(" — ");

  return (
    <div className="border-b border-rule bg-paper">
      <div className="mx-auto max-w-[78rem] px-4 pb-6 pt-9 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
          <div className="min-w-0">
            {/* The company's name is the title: "The Coca-Cola Company" means something
                to everyone, "KO" only to people who already know. The verdict below is
                the page's one loud element, so the title stays calm. */}
            <Title
              className="font-semibold leading-[1.05] text-ink"
              style={{ fontSize: "clamp(1.75rem, 4vw, 2.75rem)", letterSpacing: "-0.03em" }}
            >
              {market.name || analysis.ticker}
            </Title>
            <div className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-2 text-base text-muted-foreground">
              <Badge tone="neutral" className="nums text-ink-soft">
                {analysis.ticker}
              </Badge>
              {card && <Badge tone={ratingTone(card.rating)}>{card.rating}</Badge>}
              {analysis.cached && <Badge tone="neutral">Saved result</Badge>}
              {classification && <span>{classification}</span>}
            </div>
          </div>

          {actions && (
            <div className="flex min-w-0 flex-wrap items-center gap-2">{actions}</div>
          )}
        </div>

        {/* Rules separate the figures at desktop widths, where they sit on one row.
            On a phone the row wraps, and a left rule at the start of the second line
            reads as a stray mark rather than a separator — so below sm the columns are
            spaced instead. */}
        <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-rule pt-4 sm:flex sm:flex-wrap sm:items-stretch sm:gap-0">
          {figures.map((f, i) => (
            <div
              key={f.label}
              className={
                i === 0 ? "sm:pr-8" : "sm:border-l sm:border-rule sm:px-8 sm:last:pr-0"
              }
            >
              <dt className="mono-label">
                <Hint label={f.hint}>
                  <span tabIndex={0} className="cursor-help underline decoration-dotted underline-offset-4">
                    {f.label}
                  </span>
                </Hint>
              </dt>
              <dd className="nums mt-1 text-section font-semibold tracking-tight text-ink">
                {f.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
