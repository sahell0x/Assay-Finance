import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import type { Rating } from "@/lib/types";

/** The scale the rating was decided on, drawn as three coloured zones.
 *
 *  A reader with no finance training should see in one glance which zone the company
 *  landed in and how close it is to the next one. So the zones carry the verdict
 *  colours, each is named underneath with its range, and a single marker shows where
 *  the score fell. The zone the company is in is drawn at full strength; the others
 *  recede.
 */
export function BandRule({
  total,
  thresholds,
  rating,
  size = "md",
  ghost = null,
}: {
  total: number | null;
  thresholds: { buy: number; hold: number };
  rating: Rating;
  size?: "sm" | "md";
  /** A second, hollow marker for where the score sat before. Used by the what-if panel,
   *  where the distance between the two markers is the thing being read. */
  ghost?: number | null;
}) {
  const pct = (v: number) => Math.max(0, Math.min(100, (v / 10) * 100));
  const holdAt = pct(thresholds.hold);
  const buyAt = pct(thresholds.buy);
  const markerAt = total === null ? null : pct(total);
  const ghostAt =
    ghost === null || ghost === undefined || ghost === total ? null : pct(ghost);
  const sm = size === "sm";

  const zones: { key: Rating; from: number; to: number; label: string; range: string }[] = [
    { key: "SELL", from: 0, to: holdAt, label: "Sell", range: `below ${fmt(thresholds.hold)}` },
    {
      key: "HOLD",
      from: holdAt,
      to: buyAt,
      label: "Hold",
      range: `${fmt(thresholds.hold)} to ${fmt(thresholds.buy)}`,
    },
    { key: "BUY", from: buyAt, to: 100, label: "Buy", range: `above ${fmt(thresholds.buy)}` },
  ];
  const ZONE: Record<Rating, { on: string; off: string; text: string }> = {
    SELL: { on: "bg-sell-fill", off: "bg-sell-fill/20", text: "text-sell" },
    HOLD: { on: "bg-hold-fill", off: "bg-hold-fill/20", text: "text-hold" },
    BUY: { on: "bg-buy-fill", off: "bg-buy-fill/20", text: "text-buy" },
  };

  return (
    <div className="w-full">
      {/* Headroom for the score label above the marker. */}
      <div className={cn("relative", sm ? "h-5" : "h-7")}>
        {markerAt !== null && (
          <span
            className={cn(
              "nums absolute bottom-1 -translate-x-1/2 whitespace-nowrap font-semibold text-ink",
              sm ? "text-micro" : "text-base",
            )}
            style={{ left: `${markerAt}%` }}
          >
            {ghostAt !== null ? total?.toFixed(2) : formatScore(total)}
          </span>
        )}
      </div>

      <div className={cn("relative flex w-full gap-[3px]", sm ? "h-2" : "h-3")}>
        {zones.map((z) => (
          <span
            key={z.key}
            aria-hidden
            className={cn(
              "h-full first:rounded-l-full last:rounded-r-full",
              z.key === rating ? ZONE[z.key].on : ZONE[z.key].off,
            )}
            style={{ width: `${z.to - z.from}%` }}
          />
        ))}

        {ghostAt !== null && (
          <span
            aria-hidden
            className={cn(
              "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink-muted bg-surface",
              sm ? "size-3" : "size-4",
            )}
            style={{ left: `${ghostAt}%` }}
          />
        )}
        {markerAt !== null && (
          <span
            aria-label={`Score ${formatScore(total)} out of 10`}
            role="img"
            className={cn(
              "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-surface bg-ink shadow-raise",
              sm ? "size-3.5" : "size-5",
            )}
            style={{ left: `${markerAt}%` }}
          />
        )}
      </div>

      {!sm ? (
        <div className="mt-2.5 flex w-full gap-[3px] text-small">
          {zones.map((z) => (
            <span key={z.key} className="min-w-0" style={{ width: `${z.to - z.from}%` }}>
              <span
                className={cn(
                  "block font-semibold",
                  z.key === rating ? ZONE[z.key].text : "text-muted-foreground",
                )}
              >
                {z.label}
              </span>
              <span className="nums block truncate text-micro text-muted-foreground">
                {z.range}
              </span>
            </span>
          ))}
        </div>
      ) : (
        <div className="mt-1.5 flex w-full gap-[3px] text-micro text-muted-foreground">
          {zones.map((z) => (
            <span
              key={z.key}
              className={cn(z.key === rating && `font-semibold ${ZONE[z.key].text}`)}
              style={{ width: `${z.to - z.from}%` }}
            >
              {z.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function fmt(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}
