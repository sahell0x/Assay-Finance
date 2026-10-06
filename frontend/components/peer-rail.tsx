import { Hint } from "@/components/ui/tooltip";

/** Where a value sits among its comparables.
 *
 *  Not a progress bar: it has a fixed midpoint tick, the dot sits either side of it, and
 *  the direction that counts as good depends on the metric — left of centre on a
 *  valuation multiple means cheap. A bar filling from the left would imply "more is
 *  better", which is wrong half the time here.
 */
export function PeerRail({
  percentile,
  label,
}: {
  percentile: number | null | undefined;
  label?: string;
}) {
  if (percentile === null || percentile === undefined) {
    return (
      <span className="inline-block h-[3px] w-14 rounded-full bg-rule-soft" aria-hidden />
    );
  }

  const at = Math.max(0, Math.min(100, percentile * 100));

  return (
    <Hint
      label={
        <span>
          Better than <span className="nums">{Math.round(at)}%</span> of similar
          companies{label ? ` on ${label.toLowerCase()}` : ""}. The tick in the middle is
          the typical company.
        </span>
      }
    >
      <span
        className="relative inline-block h-3 w-14 align-middle"
        role="img"
        aria-label={`${Math.round(at)}th percentile among peers`}
      >
        <span className="absolute inset-x-0 top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-rule" />
        <span className="absolute left-1/2 top-1/2 h-[7px] w-px -translate-x-1/2 -translate-y-1/2 bg-rule" />
        <span
          className={`absolute top-1/2 h-[9px] w-[9px] -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface ${
            at >= 66.7 ? "bg-buy" : at <= 33.3 ? "bg-sell" : "bg-hold"
          }`}
          style={{ left: `${at}%` }}
        />
      </span>
    </Hint>
  );
}
