import { formatCurrency, formatScore } from "@/lib/format";
import { DIMENSION_LABELS, type AnalysisDetail } from "@/lib/types";

const VERDICT: Record<string, string> = {
  BUY: "a buy",
  HOLD: "a hold",
  SELL: "a sell",
};

/** A plain-English summary built from the computed figures, not from the model.
 *
 *  The memo is written in an analyst's register however it is prompted. This is the
 *  version for someone with no finance training, and because it is assembled from the
 *  scorecard it can never disagree with the numbers on the page.
 */
export function inShort(analysis: AnalysisDetail): string | null {
  const card = analysis.scorecard;
  if (!card) return null;

  const name = analysis.blocks?.market?.name || analysis.ticker;
  const price = analysis.blocks?.market?.price ?? null;
  const target = card.price_target;

  const scored = Object.entries(card.dimension_scores ?? {}).filter(
    (e): e is [string, number] => typeof e[1] === "number",
  );
  const best = scored.length ? scored.reduce((a, b) => (b[1] > a[1] ? b : a)) : null;
  const worst = scored.length ? scored.reduce((a, b) => (b[1] < a[1] ? b : a)) : null;
  const label = (k: string) => (DIMENSION_LABELS[k] ?? k).toLowerCase();

  const parts = [
    `${name} scores ${formatScore(card.total)} out of 10, which makes it ${VERDICT[card.rating] ?? card.rating}.`,
  ];
  if (best && worst && best[0] !== worst[0]) {
    parts.push(
      `Its strongest area is ${label(best[0])} and its weakest is ${label(worst[0])}.`,
    );
  }
  if (target?.available && target.low !== null && target.high !== null && price !== null) {
    if (price > target.high) {
      parts.push(
        `At ${formatCurrency(price)} the shares look expensive: similar companies suggest they are worth ${formatCurrency(target.low)} to ${formatCurrency(target.high)}.`,
      );
    } else if (price < target.low) {
      parts.push(
        `At ${formatCurrency(price)} the shares look cheap: similar companies suggest they are worth ${formatCurrency(target.low)} to ${formatCurrency(target.high)}.`,
      );
    } else {
      parts.push(
        `At ${formatCurrency(price)} the shares look fairly priced compared with similar companies.`,
      );
    }
    // When the price and the rating point different ways, say why rather than leave a
    // "Sell" next to "looks cheap" for the reader to reconcile.
    const weak = scored
      .filter(([, v]) => v < 5)
      .sort((a, b) => a[1] - b[1])
      .map(([k]) => label(k));
    const strong = scored
      .filter(([, v]) => v >= 7.5)
      .sort((a, b) => b[1] - a[1])
      .map(([k]) => label(k));
    if (price < target.low && card.rating !== "BUY" && weak.length) {
      parts.push(
        `Cheap shares alone do not make a buy: weak ${joinAnd(weak)} ${weak.length === 1 ? "holds" : "hold"} the overall score down.`,
      );
    } else if (price > target.high && card.rating === "BUY" && strong.length) {
      parts.push(
        `It still rates a buy because its ${joinAnd(strong)} ${strong.length === 1 ? "is" : "are"} strong enough to outweigh the price.`,
      );
    }
  }
  return parts.join(" ");
}

function joinAnd(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
