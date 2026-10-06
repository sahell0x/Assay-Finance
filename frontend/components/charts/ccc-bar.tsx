"use client";

import { CHART, ChartFrame, EmptyChart } from "@/components/charts/chart-kit";

/** The cash conversion cycle, drawn as the arithmetic that produces it.
 *
 *  Two rows against a shared day axis with a marked zero. The upper row is the cash the
 *  business ties up — receivables plus inventory, running right from zero. The lower row
 *  is the part suppliers fund, running *left* from the end of the upper row; where it
 *  reaches past zero, the company is being financed by its suppliers and the net cycle
 *  is negative.
 *
 *  Laying it out this way rather than as a single stacked bar is what makes a negative
 *  cycle representable at all: payables regularly exceed the gross cycle, and a stacked
 *  bar has nowhere to put the overhang.
 */
export function CashCycleBar({
  dso,
  dio,
  dpo,
  ccc,
}: {
  dso: number | null;
  dio: number | null;
  dpo: number | null;
  ccc: number | null;
}) {
  const available =
    dso !== null && dio !== null && dpo !== null && ccc !== null &&
    [dso, dio, dpo, ccc].every((v) => Number.isFinite(v as number));

  if (!available) {
    return (
      <ChartFrame
        title="How quickly sales turn into cash"
        note="Days waiting for customers to pay, plus days stock sits unsold, minus days taken to pay suppliers. Shorter is better."
        height={190}
      >
        <EmptyChart reason="The cycle needs receivables, inventory, payables and cost of revenue. This company does not report all four — banks and many service businesses never do." />
      </ChartFrame>
    );
  }

  const gross = dso! + dio!;
  const lo = Math.min(0, ccc!);
  const hi = Math.max(0, gross);
  const pad = Math.max(8, (hi - lo) * 0.06);
  const min = lo - pad;
  const max = hi + pad;
  const span = max - min || 1;

  /** days -> percentage across the shared axis */
  const x = (days: number) => ((days - min) / span) * 100;
  const w = (days: number) => (Math.abs(days) / span) * 100;

  const negative = ccc! < 0;

  return (
    <ChartFrame
      title="How quickly sales turn into cash"
      note={
        negative
          ? "Top: days cash is stuck waiting for customers to pay and for stock to sell. Bottom: days the company takes to pay its suppliers. Here suppliers are paid last, so the company gets its cash before it has to pay out — a good sign."
          : "Top: days cash is stuck waiting for customers to pay and for stock to sell. Bottom: days the company takes to pay its suppliers. The difference is how long the company has to fund itself in between. Shorter is better."
      }
      height={190}
    >
      <div className="relative flex h-full flex-col justify-center">
        {/* zero line, drawn behind both rows */}
        <div
          aria-hidden
          className="absolute inset-y-1 w-px bg-rule"
          style={{ left: `${x(0)}%` }}
        />

        {/* --- what ties cash up ------------------------------------------- */}
        <div className="relative mb-1.5 h-7">
          <div
            className="absolute inset-y-0 flex overflow-hidden rounded-md"
            style={{ left: `${x(0)}%`, width: `${w(gross)}%` }}
          >
            <div
              className="flex items-center justify-center"
              style={{
                width: `${gross ? (dso! / gross) * 100 : 0}%`,
                background: CHART.series[1],
                borderRight: `2px solid ${CHART.surface}`,
              }}
              title={`Receivables: ${dso!.toFixed(0)} days`}
            >
              {(dso! / span) * 100 > 9 && (
                <span className="nums text-[11px] font-medium text-white">
                  {dso!.toFixed(0)}d
                </span>
              )}
            </div>
            <div
              className="flex items-center justify-center"
              style={{
                width: `${gross ? (dio! / gross) * 100 : 0}%`,
                background: CHART.accent,
              }}
              title={`Inventory: ${dio!.toFixed(0)} days`}
            >
              {(dio! / span) * 100 > 9 && (
                <span className="nums text-[11px] font-medium text-white">
                  {dio!.toFixed(0)}d
                </span>
              )}
            </div>
          </div>
        </div>

        {/* --- what suppliers fund, running left from the end of the row above --- */}
        <div className="relative h-7">
          <div
            className="absolute inset-y-0 flex items-center justify-center rounded-md"
            style={{
              left: `${x(ccc!)}%`,
              width: `${w(dpo!)}%`,
              background: CHART.buy,
              opacity: 0.88,
            }}
            title={`Payables: ${dpo!.toFixed(0)} days of supplier financing`}
          >
            {(dpo! / span) * 100 > 9 && (
              <span className="nums text-[11px] font-medium text-white">
                {dpo!.toFixed(0)}d
              </span>
            )}
          </div>
        </div>

        {/* --- the axis ----------------------------------------------------- */}
        <div className="relative mt-1.5 h-4">
          <span
            className="nums absolute text-micro text-muted-foreground"
            style={{ left: `${x(0)}%`, transform: "translateX(-50%)" }}
          >
            0
          </span>
          <span
            className="nums absolute text-micro text-muted-foreground"
            style={{ left: `${x(gross)}%`, transform: "translateX(-50%)" }}
          >
            {gross.toFixed(0)}d
          </span>
          {Math.abs(ccc!) > 4 && (
            <span
              className="nums absolute text-micro font-medium"
              style={{
                left: `${x(ccc!)}%`,
                transform: "translateX(-50%)",
                color: negative ? CHART.buy : CHART.ink,
              }}
            >
              {ccc!.toFixed(0)}d
            </span>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-rule-soft pt-2.5 text-micro">
          {[
            { label: "Receivables", value: dso!, color: CHART.series[1] },
            { label: "Inventory", value: dio!, color: CHART.accent },
            { label: "Funded by suppliers", value: -dpo!, color: CHART.buy },
          ].map((s) => (
            <span key={s.label} className="flex items-center gap-1.5 text-muted-foreground">
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-sm"
                style={{ background: s.color }}
              />
              {s.label}
              <span className="nums text-ink-soft">
                {s.value > 0 ? "+" : ""}
                {s.value.toFixed(0)}d
              </span>
            </span>
          ))}
          <span className="ml-auto flex items-baseline gap-2">
            <span className="text-muted-foreground">Net cycle</span>
            <span
              className="nums text-lead font-medium"
              style={{ color: negative ? CHART.buy : CHART.ink }}
            >
              {ccc!.toFixed(0)} days
            </span>
          </span>
        </div>
      </div>
    </ChartFrame>
  );
}
